// After the operator changes only the player's initial/maximum health to 100 in UI.
async (page) => {
  const pending = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/operations/games.playtest'), { timeout: 60000 });
  await page.getByRole('button', { name: '运行正式 Playtest', exact: true }).click();
  const response = await pending;
  const result = await response.json();
  if (!response.ok() || result.outcome.game.version !== 5 || result.outcome.report.outcome !== 'won' || result.outcome.report.ticks_completed !== 3600) throw new Error('Actual Phaser did not complete the modified game');
  await page.locator('.game-report-summary').getByText('won', { exact: true }).waitFor();
  await page.screenshot({ path: 'output/playwright/game-independent-winning-report.png' });
  return result;
}
