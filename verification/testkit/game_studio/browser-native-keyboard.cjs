async (page) => {
  await page.getByRole('tab', { name: 'Native Agent Fox Survival', exact: true }).last().click();
  const studio = page.locator('.game-studio');
  await studio.getByRole('button', { name: '重置', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.game-studio .game-preview-stats')?.textContent.includes('tick 0'));
  await studio.getByRole('button', { name: '播放', exact: true }).click();
  await studio.locator('.game-viewport').focus();
  await page.keyboard.down('ArrowRight');
  await page.waitForFunction(() => Number(document.querySelector('.game-studio .game-preview-stats')?.textContent.match(/tick (\d+)/)?.[1]) >= 30);
  await page.keyboard.up('ArrowRight');
  await studio.getByRole('button', { name: '暂停', exact: true }).click();
  const claim = page.waitForResponse(async (response) => response.request().method() === 'POST' && response.url().includes('/operations/playtest.next') && (await response.json()).status === 'request');
  const completion = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes('/operations/games.playtest'));
  await studio.getByRole('button', { name: '运行正式 Playtest', exact: true }).click();
  const response = await completion;
  const result = await response.json();
  // Electron transport can omit POST data from the CDP request object. Read
  // the actual immutable server claim consumed by the installed executor.
  const input = (await (await claim).json()).request.input;
  if (!response.ok() || !input.inputs.some((item) => item.actions.includes('right')) || !input.inputs.some((item) => item.actions.length === 0)) throw new Error('Native keyboard press/release must survive the official playtest input contract');
  return { request: input, result, boundary: 'real native keyboard events to product Viewport to installed executor to durable ActionRun' };
}
