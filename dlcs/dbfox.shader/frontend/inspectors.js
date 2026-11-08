import { decodeBytes, encodeBytes } from './renderer.js';

export function inspectorComponents(React) {
  const h = React.createElement;
  const field = (label, control) => h('label', { className: 'shader-field' }, h('span', null, label), control);
  const input = (name, value, options = {}) => h('input', { name, defaultValue: value, required: true, ...options });
  const select = (name, value, items, options = {}) => h('select', { name, defaultValue: value, ...options }, items.map(([id, title]) => h('option', { key: id, value: id }, title)));
  const submit = (label) => h('button', { type: 'submit', className: 'shader-primary' }, label);
  const smallButton = (label, action) => h('button', { type: 'button', onClick: action }, label);
  const dataFrom = (event) => { event.preventDefault(); return new FormData(event.currentTarget); };
  const number = (form, name) => {
    const raw = String(form.get(name) ?? '').trim();
    if (!raw || !Number.isFinite(Number(raw))) throw new Error(`${name} requires a finite number.`);
    return Number(raw);
  };
  const selectors = (items) => items.map((item) => [item.id, item.title]);

  function Passes({ document, selectedId, onSelect, onApply, disabled, onAsk }) {
    const pass = document.passes.find((item) => item.id === selectedId) ?? document.passes[0];
    const index = document.passes.indexOf(pass);
    const vertices = selectors(document.stages.filter((stage) => stage.kind === 'vertex'));
    const fragments = selectors(document.stages.filter((stage) => stage.kind === 'fragment'));
    const reorder = (offset) => {
      const ids = document.passes.map((item) => ({ id: item.id }));
      [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
      onApply([{ kind: 'pass_reorder', pass_ids: ids }]);
    };
    return h('div', { className: 'shader-inspector' },
      h('h2', null, 'Pass graph'),
      h('p', { className: 'shader-muted' }, 'Passes execute top to bottom. Inputs can sample an earlier pass or an immutable texture.'),
      h('ol', { className: 'shader-pass-list' }, document.passes.map((item, order) => h('li', { key: item.id },
        h('button', { type: 'button', onClick: () => onSelect(item.id), 'aria-pressed': item.id === pass.id }, `${order + 1}. ${item.title}`, h('small', null, `${item.width} × ${item.height}${document.preview.pass_id === item.id ? ' · final output' : ''}`)),
        h('span', { className: 'shader-muted' }, item.bindings.map((binding) => `${binding.name} ← ${binding.source.kind === 'pass' ? document.passes.find((value) => value.id === binding.source.pass_id)?.title : document.textures.find((value) => value.id === binding.source.texture_id)?.title}`).join(' · ') || 'No sampled inputs'),
      ))),
      h('div', { className: 'shader-actions' }, smallButton('Ask about this pass', () => onAsk(pass)),
        h('button', { type: 'button', disabled: disabled || index === 0, onClick: () => reorder(-1) }, 'Move up'),
        h('button', { type: 'button', disabled: disabled || index === document.passes.length - 1, onClick: () => reorder(1) }, 'Move down')),
      h('fieldset', { disabled, className: 'shader-fieldset' }, h('legend', null, 'Pass settings'),
        h('form', { key: pass.id + JSON.stringify(pass), className: 'shader-form', onSubmit: (event) => {
          const form = dataFrom(event);
          onApply([{ kind: 'pass_update', pass_id: { id: pass.id }, title: String(form.get('title')), vertex_stage_id: { id: String(form.get('vertex')) }, fragment_stage_id: { id: String(form.get('fragment')) }, width: number(form, 'width'), height: number(form, 'height'), clear_color: ['r', 'g', 'b', 'a'].map((name) => number(form, name)) }]);
        } },
        field('Title', input('title', pass.title, { maxLength: 120 })),
        field('Vertex stage', select('vertex', pass.vertex_stage_id, vertices)), field('Fragment stage', select('fragment', pass.fragment_stage_id, fragments)),
        h('div', { className: 'shader-grid-two' }, field('Width', input('width', pass.width, { type: 'number', min: 1, max: 512, step: 1 })), field('Height', input('height', pass.height, { type: 'number', min: 1, max: 512, step: 1 }))),
        h('div', { className: 'shader-grid-four' }, ['r', 'g', 'b', 'a'].map((name, order) => h(React.Fragment, { key: name }, field(`Clear ${name.toUpperCase()}`, input(name, pass.clear_color[order], { type: 'number', min: 0, max: 1, step: 'any' }))))),
        submit('Save pass settings')),
        h('button', { type: 'button', className: 'shader-danger', onClick: () => onApply([{ kind: 'pass_remove', pass_id: { id: pass.id } }]) }, 'Remove this pass'),
        h('p', { className: 'shader-muted' }, 'Move the final output and remove dependent bindings before deleting a pass.'),
      ),
      h('fieldset', { disabled, className: 'shader-fieldset' }, h('legend', null, 'Sampler bindings'),
        pass.bindings.length === 0 ? h('p', { className: 'shader-muted' }, 'No sampled inputs.') : pass.bindings.map((binding) => h('div', { key: binding.name, className: 'shader-binding' }, h('strong', null, binding.name), h('span', null, `${binding.source.kind} · ${binding.filter}`), smallButton(`Remove ${binding.name}`, () => onApply([{ kind: 'binding_remove', pass_id: { id: pass.id }, name: binding.name }])))),
        h('form', { className: 'shader-form', onSubmit: (event) => {
          const form = dataFrom(event); const [kind, id] = String(form.get('source')).split(':');
          onApply([{ kind: 'binding_set', pass_id: { id: pass.id }, name: String(form.get('name')), source: kind === 'pass' ? { kind, pass_id: { id } } : { kind, texture_id: { id } }, filter: String(form.get('filter')), wrap: 'clamp' }]);
        } }, field('GLSL sampler2D name', input('name', 'image', { maxLength: 64, pattern: '[A-Za-z_][A-Za-z0-9_]*' })),
        field('Input source', select('source', undefined, [...document.textures.map((item) => [`texture:${item.id}`, `Texture · ${item.title}`]), ...document.passes.slice(0, index).map((item) => [`pass:${item.id}`, `Pass · ${item.title}`])], { required: true })),
        field('Sampling', select('filter', 'nearest', [['nearest', 'Nearest'], ['linear', 'Linear']])), submit('Set binding'))),
      h('fieldset', { disabled, className: 'shader-fieldset' }, h('legend', null, 'Add a pass'),
        h('form', { className: 'shader-form', onSubmit: (event) => {
          const form = dataFrom(event);
          onApply([{ kind: 'pass_create', title: String(form.get('title')), vertex_stage_id: { id: String(form.get('vertex')) }, fragment_stage_id: { id: String(form.get('fragment')) }, width: 256, height: 256, clear_color: [0, 0, 0, 1], bindings: [] }]);
        } }, field('New pass title', input('title', 'New pass', { maxLength: 120 })), field('Vertex', select('vertex', vertices[0]?.[0], vertices)), field('Fragment', select('fragment', fragments[0]?.[0], fragments)), submit('Add pass'))),
    );
  }

  const uniformTypes = ['float', 'int', 'bool', 'vec2', 'vec3', 'vec4', 'mat2', 'mat3', 'mat4'];
  function defaultValue(type) {
    if (type === 'bool') return false;
    if (type === 'float' || type === 'int') return 0;
    const size = Number(type.slice(-1));
    return type.startsWith('mat') ? Array.from({ length: size * size }, (_, index) => index % (size + 1) === 0 ? 1 : 0) : Array(size).fill(0);
  }
  function UniformForm({ item, document, onApply }) {
    const [type, setType] = React.useState(item?.type ?? 'float');
    const [value, setValue] = React.useState(item?.value ?? 0);
    const changeType = (event) => { setType(event.target.value); setValue(defaultValue(event.target.value)); };
    const numeric = (value, onChange, label, extra = {}) => field(label, h('input', { type: 'number', value, step: type === 'int' ? 1 : 'any', min: type === 'int' ? -2147483648 : -1e6, max: type === 'int' ? 2147483647 : 1e6, required: true, onChange: (event) => onChange(event.target.value), ...extra }));
    const asValue = () => type === 'bool' ? value : Array.isArray(value) ? value.map(Number) : Number(value);
    return h('form', { className: 'shader-form shader-uniform', onSubmit: (event) => {
      const form = dataFrom(event);
      const operation = { kind: item ? 'uniform_update' : 'uniform_create', ...(item ? { uniform_id: { id: item.id } } : {}), name: String(form.get('name')), pass_id: { id: String(form.get('pass')) }, type, value: asValue() };
      onApply([operation]);
    } },
    h('div', { className: 'shader-grid-two' }, field('Uniform name', input('name', item?.name ?? 'gain', { maxLength: 64, pattern: '[A-Za-z_][A-Za-z0-9_]*' })), field('Type', h('select', { value: type, onChange: changeType }, uniformTypes.map((kind) => h('option', { key: kind }, kind))))),
    field('Pass', select('pass', item?.pass_id ?? document.passes[0].id, selectors(document.passes))),
    type === 'bool' ? field('Value', h('input', { type: 'checkbox', checked: value, onChange: (event) => setValue(event.target.checked) })) : Array.isArray(value)
      ? h('div', { className: type.startsWith('mat') ? 'shader-matrix' : 'shader-grid-four', 'data-columns': type.slice(-1) }, value.map((component, index) => h(React.Fragment, { key: index }, numeric(component, (next) => setValue(value.map((old, position) => position === index ? next : old)), type.startsWith('mat') ? `Column ${Math.floor(index / Number(type.slice(-1))) + 1}, row ${index % Number(type.slice(-1)) + 1}` : ['X / R', 'Y / G', 'Z / B', 'W / A'][index]))))
      : numeric(value, setValue, 'Value'),
    (type === 'vec3' || type === 'vec4') && field('RGB color shortcut', h('input', { type: 'color', value: '#' + value.slice(0, 3).map((component) => Math.round(Math.max(0, Math.min(1, Number(component))) * 255).toString(16).padStart(2, '0')).join(''), onChange: (event) => setValue([1, 3, 5].map((offset) => parseInt(event.target.value.slice(offset, offset + 2), 16) / 255).concat(type === 'vec4' ? [value[3]] : [])) })),
    h('div', { className: 'shader-actions' }, submit(item ? 'Save uniform' : 'Add uniform'), item && smallButton('Remove uniform', () => onApply([{ kind: 'uniform_remove', uniform_id: { id: item.id } }]))));
  }

  function Uniforms({ document, onApply, disabled, version }) {
    return h('div', { className: 'shader-inspector' }, h('h2', null, 'Typed uniforms'),
      h('p', { className: 'shader-muted' }, 'u_resolution (vec2) and u_time (float) are supplied by the renderer. Matrices are column-major. Unused configured uniforms are reported as inactive.'),
      h('fieldset', { className: 'shader-fieldset', disabled }, h('legend', null, 'Configured uniforms'), document.uniforms.length === 0 && h('p', null, 'No custom uniforms yet.'), document.uniforms.map((item) => h(UniformForm, { key: `${item.id}:${version}`, item, document, onApply }))),
      h('fieldset', { className: 'shader-fieldset', disabled }, h('legend', null, 'Add a typed value'), h(UniformForm, { key: `new:${version}`, document, onApply })));
  }

  function TextureImage({ texture, bytes }) {
    const canvas = React.useRef(null);
    React.useEffect(() => {
      if (!canvas.current || !bytes) return;
      canvas.current.width = texture.width; canvas.current.height = texture.height;
      canvas.current.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(decodeBytes(bytes)), texture.width, texture.height), 0, 0);
    }, [texture, bytes]);
    return h('canvas', { ref: canvas, className: 'shader-texture-image', role: 'img', 'aria-label': `${texture.title}, ${texture.width} by ${texture.height} pixels` });
  }

  function Textures({ document, blobs, onApply, disabled, onImport }) {
    return h('div', { className: 'shader-inspector' }, h('h2', null, 'Immutable textures'), h('p', { className: 'shader-muted' }, 'RGBA8 · top-left rows · up to 512 × 512 per texture, 4 MiB total. Bind textures to named sampler2D inputs in Passes.'),
      h('div', { className: 'shader-textures' }, document.textures.map((texture) => h('article', { key: texture.id, className: 'shader-texture-card' }, h(TextureImage, { texture, bytes: blobs.find((blob) => blob.content_hash === texture.content_hash)?.rgba_base64 }), h('strong', null, texture.title), h('small', null, `${texture.width} × ${texture.height} · ${texture.content_hash.slice(0, 12)}`), h('button', { type: 'button', disabled, onClick: () => onApply([{ kind: 'texture_remove', texture_id: { id: texture.id } }]) }, 'Remove texture')))),
      h('fieldset', { disabled, className: 'shader-fieldset' }, h('legend', null, 'Import PNG'), h('p', null, 'Choose a local PNG. The browser decodes it once into immutable RGBA; paths are never saved in the document.'), smallButton('Choose PNG…', onImport)),
      h('fieldset', { disabled, className: 'shader-fieldset' }, h('legend', null, 'Create a solid texture'), h('form', { className: 'shader-form', onSubmit: (event) => {
        const form = dataFrom(event); const color = String(form.get('color')); const width = number(form, 'width'); const height = number(form, 'height');
        const pixel = [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16)).concat(Math.round(number(form, 'alpha') * 255));
        const bytes = new Uint8Array(width * height * 4);
        for (let index = 0; index < bytes.length; index += 4) bytes.set(pixel, index);
        onApply([{ kind: 'texture_create', title: String(form.get('title')), width, height, rgba_base64: encodeBytes(bytes) }]);
      } }, field('Texture title', input('title', 'Solid color', { maxLength: 120 })), h('div', { className: 'shader-grid-two' }, field('Width', input('width', 16, { type: 'number', min: 1, max: 512, step: 1 })), field('Height', input('height', 16, { type: 'number', min: 1, max: 512, step: 1 }))), field('RGB', input('color', '#479ef5', { type: 'color' })), field('Alpha', input('alpha', 1, { type: 'number', min: 0, max: 1, step: 'any' })), submit('Create texture'))));
  }
  return { Passes, Uniforms, Textures };
}

export async function decodePickedPng(host, signal) {
  const selected = await host.nativeDialogs.pickFile({ title: 'Import immutable Shader texture', accept: ['png'], maxBytes: 2097152 });
  signal.throwIfAborted();
  if (!selected) return null;
  const bytes = await host.nativeFiles.readPickedFile(selected.path);
  signal.throwIfAborted();
  // Inspect only the fixed PNG signature/IHDR dimension fields before invoking the
  // browser codec. This is a dimension guard, not a private image decoder.
  if (bytes.length < 33 || bytes.length > 2097152 || ![137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value) || String.fromCharCode(...bytes.subarray(12, 16)) !== 'IHDR') throw new Error('Choose a valid PNG texture.');
  const header = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const width = header.getUint32(16); const height = header.getUint32(20);
  if (width < 1 || width > 512 || height < 1 || height > 512) throw new Error('Texture dimensions must be between 1 and 512 pixels.');
  const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
  try {
    signal.throwIfAborted();
    if (bitmap.width !== width || bitmap.height !== height) throw new Error('Decoded PNG dimensions changed.');
    const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(bitmap, 0, 0);
    const rgba = context.getImageData(0, 0, width, height).data;
    return { kind: 'texture_create', title: selected.name.replace(/\.png$/i, '').slice(0, 120) || 'Imported texture', width, height, rgba_base64: encodeBytes(rgba) };
  } finally { bitmap.close(); }
}
