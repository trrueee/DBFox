async (page) => {
  const results = [];
  for (const name of ['Cyberpunk Fox Shrine', '128 Cubed Boundary World']) {
    await page.reload();
    await page.getByRole('treeitem', { name, exact: true }).waitFor();
    const pages = [], pending = [];
    const listener = response => { if (response.url().includes('/operations/worlds.chunks')) pending.push(response.json().then(value => pages.push({ version: value.version, chunks: value.chunks.length, bytes: JSON.stringify(value).length }))); };
    page.on('response', listener);
    const started = Date.now();
    try {
      if (await page.getByRole('tab', { name, exact: true }).count()) await page.getByRole('tab', { name, exact: true }).click();
      else await page.getByRole('treeitem', { name, exact: true }).click();
      await page.getByRole('heading', { name, exact: true }).waitFor();
      await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
      await page.waitForFunction(() => [...document.querySelectorAll('.voxel-viewport-status')].some(node => /表面方块|预览已截断/.test(node.textContent)));
      const elapsedMs = Date.now() - started;
      await Promise.all(pending);
      const row = { name, elapsedMs, pages, heading: await page.locator('.voxel-header').innerText(), status: await page.locator('.voxel-viewport-status').innerText(),
        metrics: await page.evaluate(() => ({ elements: document.querySelectorAll('*').length, heapBytes: performance.memory?.usedJSHeapSize, canvases: document.querySelectorAll('canvas').length })) };
      await page.screenshot({ path: `verification/bench/capabilities/dbfox_voxel/evidence/adversarial-${name.startsWith('128') ? '128' : '64'}-world.png` });
      if (name.startsWith('128')) {
        await page.getByRole('checkbox', { name: '仅预览选区', exact: true }).check();
        await page.getByText('64 个表面方块', { exact: true }).waitFor();
        row.crop = await page.locator('.voxel-viewport-status').innerText();
        await page.setViewportSize({ width: 560, height: 1000 });
        row.narrow = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, studioWidth: document.querySelector('.voxel-studio').getBoundingClientRect().width }));
        await page.screenshot({ path: 'verification/bench/capabilities/dbfox_voxel/evidence/adversarial-narrow.png' });
        if (row.narrow.width !== row.narrow.scrollWidth) throw new Error('Horizontal page overflow');
        await page.setViewportSize({ width: 1440, height: 902 });
      }
      results.push(row);
    } finally { page.off('response', listener); }
  }
  return results;
}
