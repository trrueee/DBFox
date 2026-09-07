async (page) => {
  const writes = [];
  const observe = request => {
    if (request.method() === 'POST' && /\/operations\/documents\.(preview|compile|apply|create|delete|undo)(\?|$)/.test(request.url())) writes.push(request.url().split('/operations/')[1]);
  };
  page.on('request', observe);
  const dock = page.getByRole('complementary', { name: '工作区', exact: true });
  const artifact = dock.locator('.shader-artifact');
  const measure = async (name) => {
    await artifact.getByRole('button', { name: 'Open current document', exact: true }).scrollIntoViewIfNeeded();
    const result = await artifact.evaluate(element => {
      const rect = element.getBoundingClientRect();
      const controls = [...element.querySelectorAll('h2, p, button, canvas, select, .cm-editor, dt, dd')].map(child => {
        const bounds = child.getBoundingClientRect();
        return { element: child.tagName, text: child.tagName === 'CANVAS' ? child.getAttribute('aria-label') : child.textContent,
          left: bounds.left - rect.left, right: bounds.right - rect.left, width: bounds.width, disabled: child.disabled ?? null };
      });
      return { width: rect.width, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, columns: getComputedStyle(element).gridTemplateColumns, controls };
    });
    if (result.scrollWidth > result.clientWidth + 1 || result.controls.some(item => item.width && (item.left < -1 || item.right > result.width + 1))) throw new Error(name + ': ' + JSON.stringify(result));
    await artifact.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `docs/quality/evidence/shader-independent/artifact-${name}.png` });
    return result;
  };
  try {
    const group = page.locator('.project-group').filter({ has: page.getByRole('button', { name: 'Shader Independent Large QA', exact: true }) });
    const conversation = group.getByRole('button', { name: /^Shader render_preview / }).first();
    if (!await conversation.isVisible()) await group.getByRole('button', { name: 'Shader Independent Large QA', exact: true }).click();
    await conversation.click();
    const preview = page.locator('.artifact-view-host__inline').filter({ hasText: 'Rendered preview' }).filter({ hasText: 'IMMUTABLE · v24' });
    await preview.getByRole('button', { name: '在工作区查看', exact: true }).click();
    await artifact.getByRole('img', { name: 'Immutable preview at revision 24, 256 by 256', exact: true }).waitFor();
    // Canvas presence precedes immutable pixel loading; capture the completed state.
    await artifact.locator('button:enabled').filter({ hasText: /^Download PNG$/ }).waitFor({ timeout: 30000 });
    const previewNarrow = await measure('preview-narrow');
    if (previewNarrow.width > 400) throw new Error('Narrow Dock was not actually narrow');
    await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
    const previewWide = await measure('preview-wide');
    if (previewWide.width < 1000) throw new Error('Wide workspace was not actually wide');
    await page.getByRole('button', { name: '退出工作区全屏', exact: true }).click();
    const report = page.locator('.artifact-view-host__inline').filter({ hasText: 'Compile report' }).filter({ hasText: 'IMMUTABLE · v24' });
    await report.getByRole('button', { name: '在工作区查看', exact: true }).click();
    await artifact.getByText('Actual compile and link succeeded for this revision.', { exact: true }).waitFor();
    const reportNarrow = await measure('report-narrow');
    const nativeGroup = page.locator('.project-group').filter({ has: page.getByRole('button', { name: 'Shader Native Agent Fixed QA', exact: true }) });
    const nativeConversation = nativeGroup.getByRole('button', { name: /Native Responses GPU repair/ });
    if (!await nativeConversation.isVisible()) await nativeGroup.getByRole('button', { name: 'Shader Native Agent Fixed QA', exact: true }).click();
    await nativeConversation.click();
    const document = page.locator('.artifact-view-host__inline').filter({ hasText: 'IMMUTABLE · v1' });
    await document.getByRole('button', { name: '在工作区查看', exact: true }).click();
    await artifact.getByRole('button', { name: 'Download revision JSON', exact: true }).waitFor();
    const documentNarrow = await measure('document-narrow');
    if (!await artifact.getByRole('button', { name: 'Download revision JSON', exact: true }).isEnabled()) throw new Error('Historical document controls unavailable');
    await artifact.getByRole('button', { name: 'Inspect immutable source', exact: true }).click();
    const stages = artifact.getByRole('combobox', { name: 'Immutable shader stage', exact: true });
    await stages.selectOption('6a40f6ef-4c1d-42a8-81e6-11003a22fee6');
    const editor = artifact.getByRole('textbox', { name: 'GLSL source editor', exact: true });
    const source = await editor.innerText();
    const editable = await editor.getAttribute('contenteditable');
    if (editable !== 'false' || source.includes('BROKEN_TOKEN')) throw new Error('Historical v1 source is writable or rebound');
    const sourceNarrow = await measure('source-narrow');
    const downloadRequestedAt = new Date().toISOString();
    await artifact.getByRole('button', { name: 'Download revision JSON', exact: true }).click();
    const assetStyle = await page.evaluate(async () => {
      const styles = [...document.querySelectorAll('link[rel="stylesheet"]')].filter(node => node.href.startsWith('dlc-asset:') && node.href.endsWith('/frontend/studio.css'));
      if (styles.length !== 1) throw new Error('Expected one signed Shader stylesheet');
      const response = await fetch(styles[0].href);
      if (!response.ok) throw new Error('Cannot read actual signed stylesheet');
      const bytes = await response.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      return { href: styles[0].href, bytes: bytes.byteLength, sha256: [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('') };
    });
    if (assetStyle.sha256 !== '3c76ec7d7b122f8b2fbc1be37d6f04c5626695a719136b0761d14775db2717b6') throw new Error('Rendered CSS differs from cd8c94a7 signed provenance');
    if (writes.length) throw new Error('Layout-only verification unexpectedly wrote or requested GPU work');
    return { candidate: 'cd8c94a7', verifiedAt: new Date().toISOString(), previewNarrow, previewWide, reportNarrow, documentNarrow, sourceNarrow,
      historicalSource: { version: 1, editable, source }, download: { filename: 'shader-9a4b43a7-ba94-43be-83f4-753912e2c120-v1.json', requestedAt: downloadRequestedAt,
        completionBoundary: 'Audit native DownloadItem record, file modification time and exact JSON separately; Electron does not forward this download as a Playwright event.' }, writes, assetStyle };
  } finally { page.off('request', observe); }
}
