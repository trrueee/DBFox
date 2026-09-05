// WebGL2 is the compiler and renderer. This module is shared by Tool execution and draft preview.
const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function decodeBytes(base64) {
  const raw = atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}

export function encodeBytes(bytes) {
  let raw = '';
  for (let start = 0; start < bytes.length; start += 8192) {
    raw += String.fromCharCode(...bytes.subarray(start, start + 8192));
  }
  return btoa(raw);
}

export function flipRows(bytes, width, height) {
  const result = new Uint8Array(bytes.length);
  const stride = width * 4;
  for (let y = 0; y < height; y += 1) result.set(bytes.subarray(y * stride, (y + 1) * stride), (height - y - 1) * stride);
  return result;
}

export async function sha256(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (value) => value.toString(16).padStart(2, '0')).join('');
}

export class RenderFailure extends Error {
  constructor(code, message) { super(message); this.name = 'RenderFailure'; this.code = code; }
}

function pause(signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason ?? new DOMException('Cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 8);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

export function createRenderer(canvas) {
  const gl = canvas.getContext('webgl2', { alpha: true, antialias: false, depth: false, stencil: false, premultipliedAlpha: false, preserveDrawingBuffer: false });
  if (!gl) throw new RenderFailure('EXECUTOR_UNAVAILABLE', 'This renderer does not provide WebGL 2.');
  const parallel = gl.getExtension('KHR_parallel_shader_compile');
  const capabilities = {
    version: String(gl.getParameter(gl.VERSION)).slice(0, 256),
    shading_language_version: String(gl.getParameter(gl.SHADING_LANGUAGE_VERSION)).slice(0, 256),
    max_texture_size: gl.getParameter(gl.MAX_TEXTURE_SIZE),
    max_renderbuffer_size: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
    max_texture_image_units: gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS),
    max_combined_texture_image_units: gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS),
    max_fragment_uniform_vectors: gl.getParameter(gl.MAX_FRAGMENT_UNIFORM_VECTORS),
    max_vertex_uniform_vectors: gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS),
    parallel_shader_compile: Boolean(parallel),
  };
  let disposed = false;
  let running = false;
  let releaseCurrent = () => {};

  async function execute(snapshot, { kind = 'preview', signal, deadline = performance.now() + 9500 }) {
    if (running || disposed) throw new RenderFailure('EXECUTOR_UNAVAILABLE', 'Renderer is busy or closed.');
    running = true;
    const resources = [];
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      for (const [method, value] of resources.reverse()) gl[method](value);
    };
    releaseCurrent = release;
    const keep = (value, method) => {
      if (!value) throw new RenderFailure('GPU_ERROR', 'WebGL could not allocate a required object.');
      resources.push([method, value]); return value;
    };
    const check = () => {
      signal.throwIfAborted();
      if (disposed) throw new RenderFailure('EXECUTOR_UNAVAILABLE', 'Renderer was closed.');
      if (gl.isContextLost()) throw new RenderFailure('CONTEXT_LOST', 'WebGL context was lost.');
      if (performance.now() >= deadline) throw new RenderFailure('COMPUTE_TIMEOUT', 'The fixed computation deadline expired.');
    };
    const checkGl = () => {
      check();
      if (gl.getError() !== gl.NO_ERROR) throw new RenderFailure('GPU_ERROR', 'WebGL rejected a rendering operation.');
    };
    const diagnostics = [];
    const logs = [];
    let logBytes = 0;
    let truncated = 0;
    let hasError = false;
    const diagnostic = (code, message, details = {}, severity = 'error') => {
      // Driver text is untrusted display content; strip control characters intentionally.
      // eslint-disable-next-line no-control-regex
      const bounded = decoder.decode(encoder.encode(message.replace(/[\u0000-\u001f\u007f]/g, ' ')).subarray(0, 512), { stream: true });
      const item = { severity, code, message: bounded, ...details };
      if (severity === 'error') hasError = true;
      if (diagnostics.length < 128) diagnostics.push(item);
      else { truncated += 1; if (severity === 'error' && !diagnostics.some((value) => value.severity === 'error')) diagnostics[127] = item; }
    };
    const driverLog = (text, details, maxLine = 0) => {
      if (!text) return;
      // Preserve only the line/tab controls useful for driver logs.
      // eslint-disable-next-line no-control-regex
      const bytes = encoder.encode(text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' '));
      const available = Math.max(0, 65536 - logBytes);
      const bounded = decoder.decode(bytes.subarray(0, available), { stream: true });
      if (bounded && logs.length < 96) { logs.push({ text: bounded, ...details }); logBytes += encoder.encode(bounded).length; }
      truncated += Math.max(0, bytes.length - available);
      // Parse location only from actual driver output; status always comes from WebGL.
      for (const line of text.split('\n').slice(0, 128)) {
        const match = /^(ERROR|WARNING):\s*\d+:(\d+):\s*(.*)/i.exec(line);
        if (match) {
          const number = Number(match[2]);
          diagnostic('GLSL_DIAGNOSTIC', match[3], { ...details, ...(number > 0 && number <= Math.min(16384, maxLine) ? { line: number } : {}) }, match[1].toUpperCase() === 'ERROR' ? 'error' : 'warning');
        }
      }
    };
    const result = () => {
      // JSON escaping also consumes the report budget. Reserve space for backend
      // identity/capabilities and keep at least one actual error when truncated.
      while (logs.length && encoder.encode(JSON.stringify({ diagnostics, logs })).length > 196608) truncated += encoder.encode(logs.pop().text).length;
      return { compiled: !hasError, rendered: false, diagnostics, logs, log_truncated: truncated };
    };
    try {
      check();
      const document = snapshot.document;
      let sourceBytes = 0;
      for (const stage of document.stages) {
        const bytes = encoder.encode(stage.source).length;
        const lines = stage.source.split('\n');
        sourceBytes += bytes;
        if (bytes > 262144 || sourceBytes > 524288 || lines.length > 16384 || lines.some((line) => encoder.encode(line).length > 2048)) throw new RenderFailure('SOURCE_LIMIT', 'Source exceeds the fixed stage, line, or document budget.');
      }
      const shaders = new Map();
      const programs = new Map();
      for (const stage of document.stages) {
        check();
        const shader = keep(gl.createShader(stage.kind === 'vertex' ? gl.VERTEX_SHADER : gl.FRAGMENT_SHADER), 'deleteShader');
        // Let the native preprocessor enforce ESSL 3.00. The fixed suffix is not
        // canonical source and never changes the revision/source fingerprint.
        gl.shaderSource(shader, stage.source + '\n#if __VERSION__ != 300\n#error DBFOX_REQUIRES_GLSL_ES_300\n#endif\n'); gl.compileShader(shader);
        shaders.set(stage.id, shader);
      }
      for (const pass of document.passes) {
        check();
        const program = keep(gl.createProgram(), 'deleteProgram');
        const vertex = shaders.get(pass.vertex_stage_id); const fragment = shaders.get(pass.fragment_stage_id);
        if (!vertex || !fragment) throw new RenderFailure('GPU_ERROR', 'Pass refers to an absent shader stage.');
        gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
        programs.set(pass.id, program);
      }
      if (parallel) {
        while ([...programs.values()].some((program) => !gl.getProgramParameter(program, parallel.COMPLETION_STATUS_KHR))) {
          check(); await pause(signal);
        }
      }
      check(); // KHR reports completion on context loss too; completion is not success.
      for (const stage of document.stages) {
        const shader = shaders.get(stage.id);
        const success = gl.getShaderParameter(shader, gl.COMPILE_STATUS);
        driverLog(gl.getShaderInfoLog(shader), { stage_id: stage.id }, stage.source.split('\n').length);
        if (!success) diagnostic('STAGE_COMPILE_FAILED', `${stage.title}: shader compilation failed.`, { stage_id: stage.id });
      }
      for (const pass of document.passes) {
        const program = programs.get(pass.id);
        const success = gl.getProgramParameter(program, gl.LINK_STATUS);
        driverLog(gl.getProgramInfoLog(program), { pass_id: pass.id });
        if (!success) diagnostic('PROGRAM_LINK_FAILED', `${pass.title}: program linking failed.`, { pass_id: pass.id });
      }
      checkGl();
      if (!result().compiled) return result();
      const types = { float: gl.FLOAT, int: gl.INT, bool: gl.BOOL, vec2: gl.FLOAT_VEC2, vec3: gl.FLOAT_VEC3, vec4: gl.FLOAT_VEC4, mat2: gl.FLOAT_MAT2, mat3: gl.FLOAT_MAT3, mat4: gl.FLOAT_MAT4 };
      const uniformsByPass = new Map();
      for (const pass of document.passes) {
        const program = programs.get(pass.id);
        const configured = new Map(document.uniforms.filter((item) => item.pass_id === pass.id).map((item) => [item.name, item]));
        const bindings = new Map(pass.bindings.map((item) => [item.name, item]));
        const active = new Map();
        const attributes = [];
        for (let index = 0; index < gl.getProgramParameter(program, gl.ACTIVE_ATTRIBUTES); index += 1) {
          const attribute = gl.getActiveAttrib(program, index);
          if (attribute && !['gl_VertexID', 'gl_InstanceID'].includes(attribute.name)) attributes.push(attribute.name);
        }
        if (attributes.length || gl.getProgramParameter(program, gl.ACTIVE_UNIFORM_BLOCKS) > 0) diagnostic('UNSUPPORTED_INTERFACE', 'User vertex attributes and uniform blocks are outside the fullscreen contract.', { pass_id: pass.id });
        for (let index = 0; index < gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS); index += 1) {
          const item = gl.getActiveUniform(program, index);
          if (!item) throw new RenderFailure('GPU_ERROR', 'WebGL uniform reflection failed.');
          active.set(item.name, item);
          const expected = item.name === 'u_resolution' ? gl.FLOAT_VEC2 : item.name === 'u_time' ? gl.FLOAT : configured.has(item.name) ? types[configured.get(item.name).type] : bindings.has(item.name) ? gl.SAMPLER_2D : undefined;
          if (item.size !== 1 || /[.[\]]/.test(item.name)) diagnostic('UNSUPPORTED_UNIFORM', `${item.name}: arrays and structs are unsupported.`, { pass_id: pass.id });
          else if (expected === undefined) diagnostic('UNIFORM_MISSING', `${item.name}: configure this active uniform or sampler.`, { pass_id: pass.id });
          else if (expected !== item.type) diagnostic('UNIFORM_TYPE_MISMATCH', `${item.name}: configured type does not match the linked program.`, { pass_id: pass.id });
        }
        for (const name of [...configured.keys(), ...bindings.keys()]) if (!active.has(name)) diagnostic('UNIFORM_INACTIVE', `${name}: optimized out or not used by this pass.`, { pass_id: pass.id }, 'info');
        if (pass.bindings.length > capabilities.max_texture_image_units || pass.bindings.length > capabilities.max_combined_texture_image_units) diagnostic('DEVICE_LIMIT', 'Pass bindings exceed this device texture-unit limit.', { pass_id: pass.id });
        uniformsByPass.set(pass.id, active);
      }
      if (!result().compiled) return result();
      const targets = new Map();
      const textureObjects = new Map();
      function texture(width, height, bytes = null) {
        if (width > capabilities.max_texture_size || height > capabilities.max_texture_size) throw new RenderFailure('GPU_ERROR', 'Texture size exceeds this device limit.');
        const value = keep(gl.createTexture(), 'deleteTexture');
        gl.bindTexture(gl.TEXTURE_2D, value);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, bytes);
        return value;
      }
      function target(width, height) {
        const image = texture(width, height);
        const framebuffer = keep(gl.createFramebuffer(), 'deleteFramebuffer');
        gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, image, 0);
        if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new RenderFailure('FBO_INCOMPLETE', 'The RGBA8 framebuffer is incomplete.');
        return { image, framebuffer, width, height };
      }
      const rawTextures = new Map(snapshot.textures.map((item) => [item.content_hash, item.rgba_base64]));
      for (const item of document.textures) {
        check();
        const raw = rawTextures.get(item.content_hash);
        if (raw === undefined) throw new RenderFailure('GPU_ERROR', 'Immutable texture bytes are missing.');
        const bytes = decodeBytes(raw);
        if (bytes.length !== item.width * item.height * 4 || await sha256(bytes) !== item.content_hash) throw new RenderFailure('GPU_ERROR', 'Immutable texture layout or hash does not match.');
        check();
        textureObjects.set(item.id, texture(item.width, item.height, flipRows(bytes, item.width, item.height)));
      }
      for (const pass of document.passes) { check(); targets.set(pass.id, target(pass.width, pass.height)); }
      checkGl();
      if (kind === 'compile') return result();
      const vao = keep(gl.createVertexArray(), 'deleteVertexArray');
      gl.bindVertexArray(vao); gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND); gl.disable(gl.CULL_FACE); gl.disable(gl.SCISSOR_TEST); gl.disable(gl.DITHER);
      const setters = { float: 'uniform1f', int: 'uniform1i', bool: 'uniform1i', vec2: 'uniform2fv', vec3: 'uniform3fv', vec4: 'uniform4fv', mat2: 'uniformMatrix2fv', mat3: 'uniformMatrix3fv', mat4: 'uniformMatrix4fv' };
      const renderedPasses = new Set();
      for (const pass of document.passes) {
        check();
        const program = programs.get(pass.id); const output = targets.get(pass.id);
        gl.bindFramebuffer(gl.FRAMEBUFFER, output.framebuffer); gl.viewport(0, 0, pass.width, pass.height);
        gl.clearColor(...pass.clear_color); gl.clear(gl.COLOR_BUFFER_BIT); gl.useProgram(program);
        const active = uniformsByPass.get(pass.id);
        if (active.has('u_resolution')) gl.uniform2f(gl.getUniformLocation(program, 'u_resolution'), pass.width, pass.height);
        if (active.has('u_time')) gl.uniform1f(gl.getUniformLocation(program, 'u_time'), document.preview.time_seconds);
        for (const item of document.uniforms.filter((uniform) => uniform.pass_id === pass.id)) {
          if (!active.has(item.name)) continue;
          const location = gl.getUniformLocation(program, item.name);
          if (item.type.startsWith('mat')) gl[setters[item.type]](location, false, item.value);
          else gl[setters[item.type]](location, item.type === 'bool' ? Number(item.value) : item.value);
        }
        for (const [unit, binding] of pass.bindings.entries()) {
          const source = binding.source;
          if (source.kind === 'pass' && !renderedPasses.has(source.pass_id)) throw new RenderFailure('GPU_ERROR', 'A pass may only sample an earlier completed pass.');
          const image = source.kind === 'texture' ? textureObjects.get(source.texture_id) : targets.get(source.pass_id)?.image;
          if (!image) throw new RenderFailure('GPU_ERROR', 'Sampler source is missing.');
          gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, image);
          // A sampler object keeps distinct bindings of the same image independent.
          const sampler = keep(gl.createSampler(), 'deleteSampler');
          gl.samplerParameteri(sampler, gl.TEXTURE_MIN_FILTER, binding.filter === 'linear' ? gl.LINEAR : gl.NEAREST);
          gl.samplerParameteri(sampler, gl.TEXTURE_MAG_FILTER, binding.filter === 'linear' ? gl.LINEAR : gl.NEAREST);
          gl.samplerParameteri(sampler, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.samplerParameteri(sampler, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.bindSampler(unit, sampler);
          if (active.has(binding.name)) gl.uniform1i(gl.getUniformLocation(program, binding.name), unit);
        }
        gl.drawArrays(gl.TRIANGLES, 0, 3); checkGl(); renderedPasses.add(pass.id);
      }
      const { width, height, pass_id: passId } = document.preview;
      const source = targets.get(passId);
      if (!source) throw new RenderFailure('GPU_ERROR', 'The preview pass is missing.');
      const preview = target(width, height);
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, source.framebuffer); gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, preview.framebuffer);
      gl.blitFramebuffer(0, 0, source.width, source.height, 0, 0, width, height, gl.COLOR_BUFFER_BIT, gl.NEAREST);
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, preview.framebuffer); gl.readBuffer(gl.COLOR_ATTACHMENT0); gl.pixelStorei(gl.PACK_ALIGNMENT, 1);
      const rgba = new Uint8Array(width * height * 4);
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, rgba); checkGl();
      return { ...result(), rendered: true, rgba_base64: encodeBytes(rgba), width, height, row_order: 'bottom-left' };
    } finally { release(); releaseCurrent = () => {}; running = false; }
  }
  return {
    capabilities, execute,
    dispose() { if (disposed) return; disposed = true; releaseCurrent(); gl.getExtension('WEBGL_lose_context')?.loseContext(); },
  };
}
