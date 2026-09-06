async (page) => {
  // Observe native object creation/deletion without replacing driver results.
  await page.addInitScript(() => {
    const nativeGetContext = HTMLCanvasElement.prototype.getContext;
    const contexts = [];
    const live = Object.fromEntries(['Shader', 'Program', 'Texture', 'Framebuffer', 'Buffer', 'VertexArray'].map(name => [name, new Set()]));
    const created = Object.fromEntries(Object.keys(live).map(name => [name, 0]));
    const deleted = Object.fromEntries(Object.keys(live).map(name => [name, 0]));
    for (const kind of Object.keys(live)) {
      const make = WebGL2RenderingContext.prototype['create' + kind];
      const remove = WebGL2RenderingContext.prototype['delete' + kind];
      WebGL2RenderingContext.prototype['create' + kind] = function (...args) { const result = make.apply(this, args); if (result) { live[kind].add(result); created[kind]++; } return result; };
      WebGL2RenderingContext.prototype['delete' + kind] = function (value) { if (live[kind].delete(value)) deleted[kind]++; return remove.call(this, value); };
    }
    HTMLCanvasElement.prototype.getContext = function (...args) {
      const result = nativeGetContext.apply(this, args);
      if (result instanceof WebGL2RenderingContext && !contexts.includes(result)) contexts.push(result);
      return result;
    };
    globalThis.__shaderNativeGpuAudit = { contexts, live, created, deleted };
  });
  await page.reload();
  await page.getByRole('button', { name: 'Shader Independent QA', exact: true }).click();
  await page.getByRole('treeitem', { name: /Closed Dock Driver Proof/ }).click();
  const studio = page.locator('.shader-studio');
  await studio.getByRole('tab', { name: 'FS · Gradient', exact: true }).click();
  await studio.getByRole('button', { name: 'Preview locally', exact: true }).click();
  await studio.getByText('Revision v4 · actual WebGL pixels', { exact: true }).waitFor();
  const metrics = () => page.evaluate(() => {
    const data = globalThis.__shaderNativeGpuAudit;
    return { contexts: data.contexts.length, liveContexts: data.contexts.filter(gl => !gl.isContextLost()).length,
      live: Object.fromEntries(Object.entries(data.live).map(([key, value]) => [key, value.size])), created: data.created, deleted: data.deleted };
  });
  const rendered = await metrics();
  if (Object.values(rendered.live).some(value => value !== 0) || rendered.created.Program < 1) throw new Error(JSON.stringify(rendered));
  const lost = await page.evaluate(() => {
    const contexts = globalThis.__shaderNativeGpuAudit.contexts.filter(gl => !gl.isContextLost());
    if (contexts.length !== 1) throw new Error('Expected only the activation-owned executor context');
    const extension = contexts[0].getExtension('WEBGL_lose_context'); if (!extension) throw new Error('The actual driver lacks WEBGL_lose_context');
    extension.loseContext(); return true;
  });
  await studio.getByRole('button', { name: 'Reconnect GPU', exact: true }).waitFor();
  await page.waitForTimeout(800);
  const retired = await metrics();
  if (retired.liveContexts !== 0 || Object.values(retired.live).some(value => value !== 0)) throw new Error('Lost executor retained live resources');
  const attaching = page.waitForResponse(value => value.url().includes('/operations/compute.attach'));
  await studio.getByRole('button', { name: 'Reconnect GPU', exact: true }).click();
  const attached = await attaching;
  if (attached.status() !== 200 || (await attached.json()).server_status !== 'ready') throw new Error('Explicit reconnect did not attach');
  await studio.getByText('WebGL 2 ready · available while this app is visible', { exact: true }).waitFor();
  await studio.locator('.shader-code').evaluate(parent => { globalThis.__shaderRetiredEditor = parent.shadowRoot; });
  await page.getByRole('button', { name: '关闭 Closed Dock Driver Proof', exact: true }).click();
  const removedEditorChildren = await page.evaluate(() => globalThis.__shaderRetiredEditor.childElementCount);
  if (removedEditorChildren !== 0) throw new Error('CodeMirror shadow DOM was retained after close');
  await page.getByRole('treeitem', { name: /Closed Dock Driver Proof/ }).click();
  await page.locator('.shader-studio').getByRole('tablist', { name: 'Shader stages', exact: true }).waitFor();
  const reopened = await metrics();
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/context-loss-reconnected.png' });
  return { realContextLoss: lost, rendered, retired, reopened, removedEditorChildren, selectedTreeReopened: true };
}
