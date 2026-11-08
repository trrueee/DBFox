import { resolve } from 'node:path';
import { webcrypto, createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStagedExtensionHost, initExtensionHostGlobalSdk } from '../extensionHost';
import type { DlcModule, FrontendExtensionHost, DlcOperationInvokeOptions } from '../types';
import type { DockRenderContext } from '../../dock/types';
import type { ArtifactViewContext } from '../../../../../sdk/frontend/index';

const root = resolve(process.cwd(), '../dlcs/dbfox.shader/frontend');
const digest = 'a'.repeat(64);
const installedUrl = `dlc-asset://localhost/${digest}/frontend/index.js`;
const uuid = (value: number) => `00000000-0000-0000-0000-${String(value).padStart(12, '0')}`;
const hash = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
const source = '#version 300 es\nvoid main() {}\n';
const canonical = () => ({
  id: uuid(1), title: 'Shader test', schema_version: 1, language: 'glsl-es-300',
  stages: [{ id: uuid(2), title: 'Vertex', kind: 'vertex', source }, { id: uuid(3), title: 'Fragment', kind: 'fragment', source }],
  passes: [{ id: uuid(4), title: 'Main', vertex_stage_id: uuid(2), fragment_stage_id: uuid(3), width: 2, height: 2, clear_color: [0, 0, 0, 1], bindings: [] }],
  uniforms: [] as { id: string; pass_id: string; name: string; type: string; value: number | boolean | number[] }[],
  textures: [] as { id: string; title: string; width: number; height: number; format: string; content_hash: string }[],
  preview: { pass_id: uuid(4), width: 2, height: 2, time_seconds: 0 },
});
type Canonical = ReturnType<typeof canonical>;
type Snapshot = { document: Canonical; textures: { content_hash: string; rgba_base64: string }[] };
type Page = { document: { id: string; title: string; version: number; content_hash: string; deleted: boolean }; studio_generation: number; section: string; items: object[]; offset: number; next_offset: number; total: number; has_more: boolean; metadata: Record<string, unknown>; document_bytes?: string; source?: string; stage_id?: string; texture_bytes?: { texture_id: string; content_hash: string; total_bytes: number; rgba_base64: string } };
type Read = (parameters: Record<string, unknown>, signal: AbortSignal) => Promise<Page>;
type Loaded = { summary: Page['document']; generation: number; snapshot: Snapshot };
type ComputeResult = { compiled: boolean; rendered: boolean; diagnostics: object[]; logs: object[]; log_truncated: number };
type Renderer = { capabilities: Record<string, string | number | boolean>; execute(snapshot: Snapshot, options: { kind: string; signal: AbortSignal; deadline: number }): Promise<ComputeResult>; dispose(): void };
type Executor = { dispose(): void; reconnect(): void; getSnapshot(): { state: string; message: string }; subscribe(listener: () => void): () => void };
type ExecutorModule = { createExecutor(host: FrontendExtensionHost, identity: { clientId: string; packageDigest: string; nextCounter(): number }, options: { rendererFactory(canvas: HTMLCanvasElement): Renderer; visibility: EventTarget & { visibilityState: string } }): Executor; packageDigestFromUrl(url: string): string };
type DataModule = { loadDocument(read: Read, signal: AbortSignal, version?: number): Promise<Loaded>; rebaseDrafts(previous: Canonical, latest: Canonical, drafts: Record<string, string>): { drafts: Record<string, string>; conflicts: string[] } };

let serial = 0;
const modules: DlcModule[] = [];
const executors: Executor[] = [];
let bundled: string;
function bundleOwner(name: string): string {
  // esbuild runs in Node: jsdom's typed-array realm is not a valid build runtime.
  return execFileSync(process.execPath, ['-e', "require('esbuild').build({entryPoints:[process.argv[1]],bundle:true,format:'esm',platform:'browser',target:'es2022',write:false,define:{'import.meta.url':JSON.stringify(process.argv[2])}}).then(r=>process.stdout.write(r.outputFiles[0].text))", resolve(root, name), installedUrl], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, windowsHide: true });
}
async function importOwner<T>(name: string): Promise<T> {
  return import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(bundleOwner(name)).toString('base64')}#${++serial}`) as Promise<T>;
}
async function mainModule(): Promise<DlcModule> {
  if (!bundled) bundled = bundleOwner('index.js');
  const module = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(bundled).toString('base64')}#${++serial}`) as DlcModule;
  modules.push(module); return module;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
// A transport fixture: hash the same envelope bytes that the reader serves.
// Actual Python canonical bytes are covered by the independent captured fixture.
const documentBytes = (document: Canonical) => Buffer.from(JSON.stringify({ document, deleted: false }), 'utf8');
const summary = (document: Canonical, version = 1) => ({ id: document.id, title: document.title, version, content_hash: hash(documentBytes(document)), deleted: false });
function reader(document: Canonical, version = 1, bytes = new Uint8Array()): Read {
  return async (parameters) => {
    const section = String(parameters.section);
    const offset = Number(parameters.offset ?? 0);
    const page: Page = { document: summary(document, version), studio_generation: version, section, offset, next_offset: offset, total: 0, has_more: false, items: [], metadata: {} };
    if (section === 'summary') page.metadata = { schema_version: 1, language: 'glsl-es-300', preview: document.preview, stage_count: document.stages.length, pass_count: document.passes.length, uniform_count: document.uniforms.length, texture_count: document.textures.length, source_bytes: document.stages.reduce((sum, stage) => sum + Buffer.byteLength(stage.source), 0) };
    else if (section === 'document_bytes') {
      const canonical = documentBytes(document);
      const selected = canonical.subarray(offset, offset + Math.min(Number(parameters.limit), 16384));
      page.document_bytes = selected.toString('base64'); page.total = canonical.length;
      page.next_offset = offset + selected.length; page.has_more = page.next_offset < page.total;
    } else if (section === 'source') {
      const stage = document.stages.find((stage) => stage.id === parameters.stage_id)!;
      const lines = stage.source.match(/[^\n]*\n|[^\n]+$/g) ?? [];
      page.source = lines.slice(offset, offset + 1).join(''); page.stage_id = stage.id; page.total = lines.length; page.next_offset = Math.min(offset + 1, lines.length); page.has_more = page.next_offset < lines.length;
    } else if (section === 'texture_bytes') {
      const texture = document.textures[0]; const limit = Math.min(Number(parameters.limit), 16384);
      const selected = bytes.subarray(offset, offset + limit);
      page.texture_bytes = { texture_id: texture.id, content_hash: texture.content_hash, total_bytes: bytes.length, rgba_base64: Buffer.from(selected).toString('base64') };
      page.total = bytes.length; page.next_offset = offset + selected.length; page.has_more = page.next_offset < bytes.length;
    } else {
      const items = section === 'stages' ? document.stages.map(({ source, ...stage }) => ({ ...stage, source_hash: hash(source), source_bytes: Buffer.byteLength(source), line_count: source.split('\n').length - 1 })) : document[section as 'passes' | 'uniforms' | 'textures'];
      page.items = items.slice(offset, offset + 50); page.total = items.length; page.next_offset = offset + page.items.length; page.has_more = page.next_offset < page.total;
    }
    return page;
  };
}

function hostWith(invoke: (name: string, input: Record<string, unknown>, options?: DlcOperationInvokeOptions) => Promise<unknown>, navigate = vi.fn()) {
  const staged = createStagedExtensionHost('dbfox.shader', {
    invokeOperation: async <T,>(_owner: string, name: string, input: unknown, options?: DlcOperationInvokeOptions): Promise<T> => await invoke(name, input as Record<string, unknown>, options) as T,
    openDockTab: vi.fn(), pickFolder: vi.fn(), pickFile: vi.fn(), readPickedFile: vi.fn(),
  });
  const host = { ...staged.host, workbench: { currentScopeId: () => 'scope-1', openArtifact: navigate } };
  return { staged, host, navigate };
}
const context: DockRenderContext = { activeProjectId: 'project-1', activeConversationId: null, workbenchScopeId: 'scope-1', showToast: vi.fn(), onAsk: vi.fn() };
const caps = { version: 'fixture-device', shading_language_version: 'fixture-ESSL', max_texture_size: 512, max_renderbuffer_size: 512, max_texture_image_units: 8, max_combined_texture_image_units: 8, max_fragment_uniform_vectors: 128, max_vertex_uniform_vectors: 128, parallel_shader_compile: true };
const lease = { epoch: uuid(20), lease: 'b'.repeat(64), lease_ms: 5000, server_status: 'ready' };
const good: ComputeResult = { compiled: true, rendered: false, diagnostics: [], logs: [], log_truncated: 0 };
const request = () => ({ request_id: uuid(21), claim: 'c'.repeat(64), invocation_id: 'invocation-1', document_id: uuid(1), version: 1, content_hash: 'd'.repeat(64), request_hash: 'e'.repeat(64), remaining_ms: 10000, kind: 'compile', snapshot: { document: canonical(), textures: [] } });

beforeEach(() => {
  initExtensionHostGlobalSdk();
  vi.stubGlobal('crypto', webcrypto);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});
afterEach(async () => {
  cleanup();
  for (const executor of executors.splice(0)) executor.dispose();
  for (const module of modules.splice(0)) await module.deactivate?.();
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
});

describe('Shader owner frontend: public contracts and immutable reads', () => {
  it('registers its complete Studio and three immutable Artifact views, then disposes owner styles', async () => {
    const module = await mainModule(); const { staged, host } = hostWith(async () => ({}));
    await module.register?.(host);
    const contributions = staged.getContributions();
    expect(contributions.connectors.map((item) => item.id)).toEqual(['dbfox.shader']);
    expect(contributions.dockViews.map((item) => item.viewType)).toEqual(['dbfox.shader.studio']);
    expect(contributions.artifactViews.map((item) => item.id)).toEqual(['dbfox.shader.document', 'dbfox.shader.report', 'dbfox.shader.preview']);
    expect(document.querySelectorAll(`link[href="dlc-asset://localhost/${digest}/frontend/studio.css"]`)).toHaveLength(1);
    await module.deactivate?.();
    expect(document.querySelectorAll(`link[href="dlc-asset://localhost/${digest}/frontend/studio.css"]`)).toHaveLength(0);
    expect(() => contributions.artifactViews[0].parsePayload({ title: 'forged', version: true })).toThrow();
  });

  it('accepts only the documented installed package asset identity', async () => {
    const module = await importOwner<ExecutorModule>('executor.js');
    expect(module.packageDigestFromUrl(installedUrl)).toBe(digest);
    for (const url of [installedUrl + '?override=1', 'http://localhost/' + digest + '/frontend/index.js', installedUrl.replace('localhost', 'foreign'), installedUrl.replace(digest, 'z'.repeat(64))]) expect(() => module.packageDigestFromUrl(url)).toThrow();
  });

  it('pins every canonical/texture byte page and hashes reassembled bytes across multiple pages', async () => {
    const module = await importOwner<DataModule>('document-data.js');
    const document = canonical(); const bytes = new Uint8Array(128 * 64 * 4).map((_, index) => index % 251);
    document.textures.push({ id: uuid(5), title: 'Texture', width: 128, height: 64, format: 'rgba8', content_hash: hash(bytes) });
    const read = vi.fn(reader(document, 7, bytes));
    const result = await module.loadDocument(read, new AbortController().signal);
    expect(result.snapshot.document).toEqual(document);
    expect(Buffer.from(result.snapshot.textures[0].rgba_base64, 'base64')).toEqual(Buffer.from(bytes));
    expect(read.mock.calls.slice(1).every(([parameters]) => parameters.version === 7)).toBe(true);
    expect(read.mock.calls.filter(([parameters]) => parameters.section === 'texture_bytes').map(([parameters]) => parameters.offset)).toEqual([0, 16384]);
  });

  it('rejects mixed revisions, corrupted source, and cancellation without continuing reads', async () => {
    const module = await importOwner<DataModule>('document-data.js'); const document = canonical();
    const read = reader(document);
    await expect(module.loadDocument(read, new AbortController().signal, 7)).rejects.toThrow('requested immutable revision');
    await expect(module.loadDocument(async (parameters, signal) => {
      const page = await read(parameters, signal); if (parameters.section === 'document_bytes') page.document.version = 2; return page;
    }, new AbortController().signal)).rejects.toThrow('same immutable revision');
    await expect(module.loadDocument(async (parameters, signal) => {
      const page = await read(parameters, signal);
      if (parameters.section === 'document_bytes') {
        const bytes = Buffer.from(page.document_bytes!, 'base64'); bytes[0] ^= 1;
        page.document_bytes = bytes.toString('base64');
      }
      return page;
    }, new AbortController().signal)).rejects.toThrow('hash');
    const controller = new AbortController(); const stopped = vi.fn(async (parameters: Record<string, unknown>, signal: AbortSignal) => { controller.abort(); return read(parameters, signal); });
    await expect(module.loadDocument(stopped, controller.signal)).rejects.toThrow(); expect(stopped).toHaveBeenCalledTimes(1);
  });

  it('rebases an untouched stage across other edits, but retains changed/deleted target conflicts', async () => {
    const module = await importOwner<DataModule>('document-data.js'); const before = canonical(); const after = canonical();
    after.passes[0].width = 16;
    expect(module.rebaseDrafts(before, after, { [uuid(3)]: 'my draft' })).toEqual({ drafts: { [uuid(3)]: 'my draft' }, conflicts: [] });
    after.stages[1].source = 'external source';
    expect(module.rebaseDrafts(before, after, { [uuid(3)]: 'my draft' }).conflicts).toEqual([uuid(3)]);
    after.stages.pop(); expect(module.rebaseDrafts(before, after, { [uuid(3)]: 'my draft' }).conflicts).toEqual([uuid(3)]);
  });
});

describe('Shader activation executor protocol (device stub; not GPU evidence)', () => {
  async function setup(invoke: Parameters<typeof hostWith>[0], execute = vi.fn(async () => good)) {
    const module = await importOwner<ExecutorModule>('executor.js');
    const { host } = hostWith(invoke); const dispose = vi.fn();
    const visibility = Object.assign(new EventTarget(), { visibilityState: 'visible' });
    let counter = 0;
    const executor = module.createExecutor(host, { clientId: uuid(10), packageDigest: digest, nextCounter: () => ++counter }, { visibility, rendererFactory: () => ({ capabilities: caps, execute, dispose }) });
    executors.push(executor); return { executor, visibility, execute, dispose };
  }

  it('detaches a late attach after disposal and never starts polling', async () => {
    const attach = deferred<typeof lease>(); const invoke = vi.fn(async (name: string) => name === 'compute.attach' ? attach.promise : { accepted: true });
    const { executor, dispose } = await setup(invoke);
    executor.dispose(); attach.resolve(lease); await Promise.resolve(); await Promise.resolve();
    await waitFor(() => expect(invoke.mock.calls.filter(([name]) => name === 'compute.detach')).toHaveLength(1));
    expect(invoke.mock.calls.some(([name]) => name === 'compute.next')).toBe(false); expect(dispose).toHaveBeenCalledTimes(1);
  });

  it('renews its lease while compilation waits, completes exact frozen proof once, and never replays failed handoff', async () => {
    vi.useFakeTimers(); const work = deferred<ComputeResult>(); let claimed = false;
    const invoke = vi.fn(async (name: string, input: Record<string, unknown>) => {
      if (name === 'compute.attach') return lease;
      if (name === 'compute.next') { if (!claimed) { claimed = true; return { status: 'request', request: request() }; } return { status: 'busy' }; }
      if (name === 'compute.complete') { expect(input).toMatchObject({ epoch: lease.epoch, lease: lease.lease, registration_counter: 1, package_digest: digest, ...Object.fromEntries(Object.entries(request()).filter(([key]) => !['snapshot', 'remaining_ms', 'kind'].includes(key))) }); throw new Error('network unknown'); }
      return { accepted: true };
    });
    const { executor, execute } = await setup(invoke, vi.fn(() => work.promise));
    await vi.advanceTimersByTimeAsync(1600);
    expect(execute).toHaveBeenCalledTimes(1); expect(invoke.mock.calls.filter(([name]) => name === 'compute.next').length).toBeGreaterThanOrEqual(3);
    work.resolve(good); await vi.advanceTimersByTimeAsync(5000);
    expect(invoke.mock.calls.filter(([name]) => name === 'compute.complete')).toHaveLength(1);
    expect(executor.getSnapshot().state).toBe('unavailable');
  });

  it('aborts work on hidden, rejects its late pixels, and visible recovery claims only a new epoch', async () => {
    vi.useFakeTimers(); const work = deferred<ComputeResult>(); let counter = 0;
    const invoke = vi.fn(async (name: string) => {
      if (name === 'compute.attach') { counter += 1; return { ...lease, epoch: uuid(20 + counter) }; }
      if (name === 'compute.next') return counter === 1 ? { status: 'request', request: request() } : { status: 'idle' };
      return { accepted: true };
    });
    const { visibility, execute, dispose } = await setup(invoke, vi.fn(() => work.promise));
    await vi.advanceTimersByTimeAsync(1);
    visibility.visibilityState = 'hidden'; visibility.dispatchEvent(new Event('visibilitychange'));
    work.resolve(good); await vi.advanceTimersByTimeAsync(20);
    expect(invoke.mock.calls.some(([name]) => name === 'compute.complete')).toBe(false); expect(dispose).toHaveBeenCalledTimes(1);
    visibility.visibilityState = 'visible'; visibility.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(20);
    expect(counter).toBe(2); expect(execute).toHaveBeenCalledTimes(1);
  });
});

describe('Shader Studio direct editing through owner operations', () => {
  function memoryOperation() {
    const document = canonical(); let version = 1;
    const call = vi.fn(async (name: string, input: Record<string, unknown>) => {
      if (name === 'documents.list') return { items: [summary(document, version)], studio_generation: version, has_more: false, next_offset: 1 };
      if (name === 'documents.get') return reader(document, version)(input, new AbortController().signal);
      if (name === 'documents.head') return summary(document, version);
      if (name === 'documents.apply') {
        if (input.expected_version !== version) throw new Error('STALE_VERSION');
        for (const operation of input.operations as Record<string, unknown>[]) {
          if (operation.kind === 'uniform_create') document.uniforms.push({ id: uuid(8), pass_id: (operation.pass_id as { id: string }).id, name: String(operation.name), type: String(operation.type), value: operation.value as number });
          if (operation.kind === 'stage_replace') document.stages.find((stage) => stage.id === (operation.stage_id as { id: string }).id)!.source = String(operation.source);
        }
        version += 1; return { document: summary(document, version), changed: true, studio_generation: version, changed_ids: [], truncated: false, created_refs: {} };
      }
      throw new Error(`Unexpected test operation ${name}`);
    });
    return { call, document, changeExternally() { version += 1; document.stages[1].source += '// external\n'; } };
  }
  async function mount(invoke: Parameters<typeof hostWith>[0], navigate = vi.fn(), version?: number) {
    const module = await mainModule(); const { host, staged } = hostWith(invoke, navigate); await module.register?.(host);
    const view = staged.getContributions().dockViews[0];
    const rendered = render(view.render({ viewKey: 'shader-test', viewType: 'dbfox.shader.studio', title: 'Shader', closeable: true, projectId: 'project-1', target: { type: 'object', object: { kind: 'dbfox.shader.document', id: uuid(1), ...(version === undefined ? {} : { version }) } } }, context));
    await screen.findByRole('button', { name: 'Save source' });
    return { ...rendered, module, host, navigate };
  }

  it('renders a real CodeMirror editor and saves typed uniform input with the observed version fence', async () => {
    const memory = memoryOperation(); const { container } = await mount(memory.call);
    expect(container.querySelector('.shader-code')?.shadowRoot?.querySelector('.cm-editor')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Uniforms' }));
    fireEvent.change(screen.getByLabelText('Uniform name'), { target: { value: 'gain' } });
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: '0.75' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add uniform' }));
    await screen.findByText('Saved revision v2.');
    const input = memory.call.mock.calls.find(([name]) => name === 'documents.apply')?.[1];
    expect(input).toMatchObject({ expected_version: 1, operations: [{ kind: 'uniform_create', type: 'float', value: 0.75, pass_id: { id: uuid(4) } }] });
    expect(input?.request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('does not start export without Artifact navigation and rejects late navigation after unmount', async () => {
    const memory = memoryOperation(); const response = deferred<unknown>();
    const invoke = vi.fn(async (name: string, input: Record<string, unknown>, options?: DlcOperationInvokeOptions) => {
      if (name === 'documents.export') { expect(options?.signal).toBeInstanceOf(AbortSignal); return response.promise; }
      return memory.call(name, input);
    });
    const mounted = await mount(invoke);
    Object.defineProperty(mounted.host.workbench, 'openArtifact', { value: undefined, configurable: true });
    fireEvent.click(screen.getByRole('button', { name: 'Export revision' }));
    expect(invoke.mock.calls.some(([name]) => name === 'documents.export')).toBe(false);
    Object.defineProperty(mounted.host.workbench, 'openArtifact', { value: mounted.navigate, configurable: true });
    fireEvent.click(screen.getByRole('button', { name: 'Export revision' }));
    await waitFor(() => expect(invoke.mock.calls.filter(([name]) => name === 'documents.export')).toHaveLength(1));
    const operation = invoke.mock.calls.find(([name]) => name === 'documents.export')!;
    mounted.unmount();
    expect(operation[2]?.signal?.aborted).toBe(true);
    await act(async () => response.resolve({ session_id: 's', run_id: 'r', artifact_ids: ['a'], outcome: {} }));
    expect(mounted.navigate).not.toHaveBeenCalled();
  });

  it('passes explicit document and stage selection references through onAsk', async () => {
    const memory = memoryOperation(); await mount(memory.call);
    fireEvent.click(screen.getByRole('button', { name: 'Ask about selected lines' }));
    expect(context.onAsk).toHaveBeenLastCalledWith(expect.objectContaining({ authority: { kind: 'dbfox.shader.studio', id: 'project-1' }, object: { kind: 'dbfox.shader.stage', id: uuid(2), version: 1 }, locator: `document/${uuid(1)}/stage/${uuid(2)}/lines/1-1` }));
  });

  it('opens a historical diagnostic target as a pinned read-only editor without polling or publishing', async () => {
    const memory = memoryOperation(); const { container } = await mount(memory.call, vi.fn(), 1);
    expect(screen.getByText('Historical revision · read-only')).toBeTruthy();
    expect(container.querySelector('.shader-code')?.shadowRoot?.querySelector('.cm-content')?.getAttribute('contenteditable')).toBe('false');
    expect((screen.getByRole('button', { name: 'Export revision' }) as HTMLButtonElement).disabled).toBe(true);
    expect(memory.call.mock.calls.filter(([name]) => name === 'documents.get').every(([, input]) => input.version === 1)).toBe(true);
    vi.useFakeTimers(); await vi.advanceTimersByTimeAsync(1500);
    expect(memory.call.mock.calls.some(([name]) => name === 'documents.head')).toBe(false);
  });

  it('rejects a mismatched immutable Artifact fingerprint before displaying source and cancels a pending read on unmount', async () => {
    const module = await mainModule(); const { host, staged } = hostWith(async () => ({})); await module.register?.(host);
    const view = staged.getContributions().artifactViews[0]; const document = canonical();
    const payload = { ...summary(document), project_id: 'project-1', document_id: document.id };
    const artifact = { id: 'artifact-1', type: 'dbfox.shader.document-revision', title: document.title };
    const pending = deferred<Awaited<ReturnType<ArtifactViewContext['representations']['read']>>>();
    const read = vi.fn<ArtifactViewContext['representations']['read']>().mockResolvedValueOnce({ representation_type: 'dbfox.shader.document.v1', representation_version: 1, operation: 'page', consistency: 'durable_snapshot', source_version: '1', source_fingerprint: '0'.repeat(64), payload: {}, read_id: 'read-1', read_at: '2026-09-05T00:00:00Z' }).mockImplementationOnce(() => pending.promise);
    const artifactContext: ArtifactViewContext = { surface: 'workspace', onToast: vi.fn(), representations: { available: [], list: vi.fn(), read, stream: vi.fn() } };
    const first = render(view.render(artifact, payload, artifactContext));
    await screen.findByText('Artifact representation does not match its frozen revision.');
    expect(screen.queryByRole('button', { name: 'Inspect immutable source' })).toBeNull();
    first.unmount();
    const second = render(view.render({ ...artifact, id: 'artifact-2' }, payload, artifactContext));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    const signal = read.mock.calls[1][3]; second.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
