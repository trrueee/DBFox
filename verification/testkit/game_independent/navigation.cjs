// Replay only layout and existing-document navigation; export uses original ActionRun.
async (page) => {
  const ensure = (ok, message) => { if (!ok) throw new Error(message); };
  const separator = page.getByRole('separator', { name: '调整工作区宽度', exact: true });
  await separator.press('End');
  const minimum = await page.locator('.app-dock-panel').boundingBox();
  ensure(minimum.width >= 319 && minimum.width <= 321, 'Keyboard resize did not clamp to 320px');
  const handle = await separator.boundingBox();
  const stage = await page.locator('.app-v3-stage').boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 30);
  await page.mouse.down();
  await page.mouse.move(stage.x + stage.width - 10, handle.y + 30, { steps: 8 });
  await page.mouse.up();
  const pointerMinimum = await page.locator('.app-dock-panel').boundingBox();
  ensure(pointerMinimum.width >= 319, 'Pointer resize produced false collapsed Dock');
  await page.getByRole('treeitem', { name: '狐狸', exact: true }).click();
  await page.getByRole('heading', { name: '狐狸', exact: true }).waitFor({ timeout: 10000 });
  const tabsBefore = await page.getByRole('tab', { name: 'Independent Fox Review', exact: true }).count();
  ensure(tabsBefore === 1, 'Unexpected initial specific Studio tabs');
  await page.getByRole('button', { name: '导出工件', exact: true }).click();
  await page.getByRole('button', { name: '下载 Game 包', exact: true }).waitFor({ timeout: 10000 });
  // At 320px the prior Studio is in the Host's real overflow menu.
  await page.getByRole('button', { name: '更多标签（1 个）', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Independent Fox Review', exact: true }).click();
  await page.getByRole('heading', { name: '狐狸', exact: true }).waitFor({ timeout: 10000 });
  const game = await page.getByRole('combobox', { name: '选择游戏', exact: true }).inputValue();
  ensure(game === '0f0d8d85-b780-4973-8b57-5034b1dd69e4', 'Artifact return lost specific game');
  await page.screenshot({ path: 'output/playwright/game-independent-navigation-fixed.png' });
  return { keyboardMinimum: minimum.width, pointerMinimum: pointerMinimum.width,
    restoredGame: game, restoredEntity: '狐狸', underlyingVersion: 5 };
}
