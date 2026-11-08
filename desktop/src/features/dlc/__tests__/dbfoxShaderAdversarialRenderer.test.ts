import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { expect, it, vi } from 'vitest';

type Result = { compiled: boolean; rendered: boolean; logs: { text: string }[]; diagnostics: { severity: string }[] };
type Owner = { createRenderer(canvas: { getContext(): object }): { execute(snapshot: object, options: object): Promise<Result>; dispose(): void } };

it('bounds independent driver log strings without carrying partial UTF-8 between records', async () => {
  // Deliberate driver-boundary fault injection. No actual GPU success is claimed.
  const entry = resolve(process.cwd(), '../dlcs/dbfox.shader/frontend/renderer.js');
  const bundle = execFileSync(process.execPath, ['-e', "require('esbuild').build({entryPoints:[process.argv[1]],bundle:true,format:'esm',platform:'browser',target:'es2022',write:false}).then(r=>process.stdout.write(r.outputFiles[0].text))", entry], { encoding: 'utf8', windowsHide: true });
  const owner = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(bundle).toString('base64')}`) as Owner;
  let number = 0;
  const deletedShaders = vi.fn(); const deletedPrograms = vi.fn();
  const gl = {
    VERSION: 1, SHADING_LANGUAGE_VERSION: 2, NO_ERROR: 0, VERTEX_SHADER: 3, FRAGMENT_SHADER: 4,
    getExtension: () => null, getParameter: () => 1024, isContextLost: () => false, getError: () => 0,
    createShader: () => ({ number: number++ }), createProgram: () => ({}),
    shaderSource: () => {}, compileShader: () => {}, attachShader: () => {}, linkProgram: () => {},
    getShaderParameter: (shader: { number: number }) => shader.number === 0,
    getShaderInfoLog: (shader: { number: number }) => shader.number === 0 ? 'x'.repeat(65535) + '界' : 'A',
    getProgramParameter: () => false, getProgramInfoLog: () => '',
    deleteShader: deletedShaders, deleteProgram: deletedPrograms,
  };
  const renderer = owner.createRenderer({ getContext: () => gl });
  const snapshot = { document: {
    stages: [{ id: 'v', kind: 'vertex', title: 'Vertex', source: '#version 300 es\n' },
      { id: 'f', kind: 'fragment', title: 'Fragment', source: '#version 300 es\n' }],
    passes: [{ id: 'p', title: 'Pass', vertex_stage_id: 'v', fragment_stage_id: 'f' }],
  } };
  const result = await renderer.execute(snapshot, { kind: 'compile', signal: new AbortController().signal });
  renderer.dispose();
  expect(result.compiled).toBe(false);
  expect(result.rendered).toBe(false);
  expect(result.diagnostics.some((item) => item.severity === 'error')).toBe(true);
  expect(deletedShaders).toHaveBeenCalledTimes(2);
  expect(deletedPrograms).toHaveBeenCalledTimes(1);
  const size = result.logs.reduce((total, item) => total + Buffer.byteLength(item.text), 0);
  expect(size).toBeLessThanOrEqual(65536);
  expect(result.logs[1].text).toBe('A');
});
