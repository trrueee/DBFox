// Independent UI actions against the actual installed Electron renderer.
async (page) => {
  const studio = page.locator('.game-studio');
  const stats = studio.locator('.game-preview-stats');
  const ensure = (ok, why) => { if (!ok) throw new Error(why); };
  await studio.getByRole('button', { name: '重置', exact: true }).click();
  ensure((await stats.innerText()).includes('tick 0'), 'Reset did not return to zero');
  await studio.getByRole('button', { name: '单步', exact: true }).click();
  ensure((await stats.innerText()).includes('tick 1'), 'Single step must advance exactly once');
  await studio.getByRole('button', { name: '播放', exact: true }).click();
  await page.waitForFunction(() => Number(document.querySelector('.game-preview-stats')?.textContent.match(/tick (\d+)/)?.[1]) >= 6);
  await studio.getByRole('button', { name: '暂停', exact: true }).click();
  const paused = await stats.innerText();
  await page.waitForTimeout(200);
  ensure(await stats.innerText() === paused, 'Paused simulation kept advancing');
  await studio.getByRole('button', { name: '重置', exact: true }).click();
  ensure((await stats.innerText()).includes('tick 0'), 'Second reset failed');
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/operations/games.playtest'), { timeout: 60000 });
  await studio.getByRole('button', { name: '运行正式 Playtest', exact: true }).click();
  const completed = await response;
  const result = await completed.json();
  ensure(completed.ok(), 'Formal playtest HTTP failed');
  ensure(result.outcome.game.version === 4, 'Formal playtest used wrong version');
  ensure(result.outcome.report.outcome === 'lost', 'Uncontrolled fox should lose against spawning enemies');
  await page.screenshot({ path: 'output/playwright/game-independent-formal-playtest.png' });
  return { pauseStable: true, singleStep: 1, reset: 0, result };
}
