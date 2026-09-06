import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { webcrypto } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { beforeAll, describe, expect, it, vi } from 'vitest';

type Summary = { id: string; title: string; version: number; content_hash: string; deleted: boolean };
type Page = { document: Summary; studio_generation: number; section: string; items: Record<string, unknown>[];
  offset: number; next_offset: number; total: number; has_more: boolean; metadata: Record<string, unknown>;
  stage_id?: string; source?: string; document_bytes?: string };
type Packet = { parameters: Record<string, unknown>; page: Page };
type Fixture = { package_digest: string; summary: Summary; pages: Packet[] };
type Loaded = { summary: Summary; snapshot: { document: { stages: object[]; uniforms: object[] }; textures: object[] } };
type Module = { loadDocument(read: (parameters: Record<string, unknown>) => Promise<Page>, signal: AbortSignal, version?: number): Promise<Loaded> };
const fixture = JSON.parse(readFileSync(resolve(process.cwd(), '../verification/testkit/shader_adversarial/evidence/public-pages.json'), 'utf8')) as Fixture;
let owner: Module;

beforeAll(async () => {
  vi.stubGlobal('crypto', webcrypto);
  const entry = resolve(process.cwd(), '../dlcs/dbfox.shader/frontend/document-data.js');
  const bundle = execFileSync(process.execPath, ['-e', "require('esbuild').build({entryPoints:[process.argv[1]],bundle:true,format:'esm',platform:'browser',target:'es2022',write:false}).then(r=>process.stdout.write(r.outputFiles[0].text))", entry], { encoding: 'utf8', windowsHide: true });
  owner = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(bundle).toString('base64')}`) as Module;
});

function load(change?: (page: Page) => void, fixed = fixture.summary.version, sourceBytes?: Buffer) {
  return owner.loadDocument(async (parameters) => {
    expect(parameters.version ?? fixed).toBe(fixed);
    const packet = fixture.pages.find((item) => item.parameters.section === parameters.section
      && (item.parameters.stage_id ?? null) === (parameters.stage_id ?? null)
      && (item.parameters.texture_id ?? null) === (parameters.texture_id ?? null)
      && (item.parameters.offset ?? 0) === (parameters.offset ?? 0));
    expect(packet, JSON.stringify(parameters)).toBeDefined();
    const page = structuredClone(packet!.page);
    if (sourceBytes && page.section === 'document_bytes') {
      const offset = Number(parameters.offset ?? 0);
      const bytes = sourceBytes.subarray(offset, offset + 16384);
      page.document_bytes = bytes.toString('base64');
      page.total = sourceBytes.length; page.next_offset = offset + bytes.length;
      page.has_more = page.next_offset < page.total;
    }
    change?.(page);
    return page;
  }, new AbortController().signal, fixed);
}

describe('separate adversarial replay of actual signed public document pages', () => {
  it('accepts the unchanged full signed-owner pages as a positive control', async () => {
    const value = await load();
    expect(value.summary).toEqual(fixture.summary);
    expect(value.snapshot.document.stages).toHaveLength(2);
    expect(value.snapshot.document.uniforms).toHaveLength(1);
    expect(value.snapshot.textures).toHaveLength(1);
  });

  it.each(['schema', 'count', 'omission', 'duplicate-id', 'dangling-pass', 'uniform-value', 'preview-value'])('rejects %s corruption under an unchanged immutable identity', async (fault) => {
    // The owner now exposes its original canonical bytes, removing the old
    // object-page assembly. Preserve the same semantic corruption under the
    // old fingerprint; never call an unread old fake page a passing attack.
    const raw = Buffer.concat(fixture.pages.filter((item) => item.page.section === 'document_bytes')
      .map((item) => Buffer.from(item.page.document_bytes!, 'base64'))).toString('utf8');
    const parsed = JSON.parse(raw) as { document: { stages: { id: string }[] } };
    let altered = raw;
    if (fault === 'omission') altered = raw.replace(/"uniforms":\[\{[^}]+\}\]/, '"uniforms":[]');
    if (fault === 'duplicate-id') altered = raw.replaceAll(parsed.document.stages[1].id, parsed.document.stages[0].id);
    if (fault === 'dangling-pass') altered = raw.replace(`"fragment_stage_id":"${parsed.document.stages[1].id}"`, '"fragment_stage_id":"00000000-0000-0000-0000-999999999999"');
    if (fault === 'uniform-value') altered = raw.replace('"value":0.25', '"value":0.75');
    if (fault === 'preview-value') altered = raw.replace('"time_seconds":0.0', '"time_seconds":100.0');
    if (!['schema', 'count'].includes(fault)) expect(altered).not.toBe(raw);
    await expect(load((page) => {
      if (fault === 'schema' && page.section === 'summary') page.metadata.schema_version = true;
      if (fault === 'count' && page.section === 'summary') page.metadata.stage_count = 64;
    }, fixture.summary.version, Buffer.from(altered, 'utf8'))).rejects.toThrow();
  });

  it('rejects an old fixed revision substituted into the first page', async () => {
    await expect(load(undefined, fixture.summary.version + 1)).rejects.toThrow(/immutable revision/);
  });

  it.each(['offset', 'total', 'premature-end', 'base64', 'empty', 'oversize'])('rejects canonical byte page %s faults', async (fault) => {
    await expect(load((page) => {
      if (page.section !== 'document_bytes') return;
      if (fault === 'offset') page.offset++;
      if (fault === 'total') page.total = 1048609;
      if (fault === 'premature-end') page.has_more = false;
      if (fault === 'base64') page.document_bytes += '\n';
      if (fault === 'empty') page.document_bytes = '';
      if (fault === 'oversize') page.document_bytes = Buffer.alloc(16385).toString('base64');
    })).rejects.toThrow();
  });
});
