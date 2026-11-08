async (page) => {
  await page.getByRole('button', { name: 'Shader Independent QA', exact: true }).click();
  await page.getByRole('treeitem', { name: /Closed Dock Driver Proof/ }).click();
  await page.getByRole('tab', { name: 'FS · Gradient', exact: true }).click();
  const measure = () => page.evaluate(() => {
    const selectors = ['.shader-studio', '.shader-work-area', '.shader-main-panel', '.shader-preview-panel'];
    return Object.fromEntries(selectors.map(selector => {
      const element = document.querySelector(selector); const rect = element.getBoundingClientRect();
      return [selector, { x: rect.x, y: rect.y, width: rect.width, client: element.clientWidth, scroll: element.scrollWidth,
        columns: getComputedStyle(element).gridTemplateColumns }];
    }));
  });
  const narrow = await measure();
  if (narrow['.shader-studio'].width > 400 || narrow['.shader-work-area'].scroll > narrow['.shader-work-area'].client + 1) throw new Error(JSON.stringify(narrow));
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/narrow-fixed.png' });
  await page.getByRole('button', { name: 'Preview locally', exact: true }).click();
  await page.getByText('Revision v4 · actual WebGL pixels', { exact: true }).waitFor();
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/narrow-preview-fixed.png' });
  await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
  const wide = await measure();
  if (wide['.shader-work-area'].scroll > wide['.shader-work-area'].client + 1) throw new Error(JSON.stringify(wide));
  await page.screenshot({ path: 'docs/quality/evidence/shader-independent/wide-fixed.png' });
  return { narrow, wide, viewport: page.viewportSize(), alerts: await page.getByRole('alert').allTextContents() };
}
