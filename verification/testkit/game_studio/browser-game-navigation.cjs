async page => {
  // Requires the UI-created Host Fix Fox preset at v2 in the isolated profile.
  // This invokes a new 60-tick ActionRun, never a direct backend report write.
  const assert = (value, message) => { if (!value) throw new Error(message); };
  await page.getByRole('button', {name:'+ 创建游戏',exact:true}).click();
  const selector=page.getByRole('combobox',{name:'选择游戏',exact:true});
  await selector.selectOption({label:'Host Fix Fox'});
  await page.getByRole('heading',{name:'Host Fix Fox',exact:true}).waitFor();
  const gameId=await selector.inputValue();
  await page.getByRole('treeitem',{name:'狐狸',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Playtest tick 数',exact:true}).fill('60');
  const response=page.waitForResponse(item=>item.request().method()==='POST'&&item.url().includes('/operations/games.playtest'));
  await page.getByRole('button',{name:'运行正式 Playtest',exact:true}).click();
  const completed=await response;
  const result=await completed.json();
  assert(completed.ok() && result.outcome.report.ticks_completed === 60, 'Actual Phaser ActionRun must complete 60 ticks');
  await page.locator('.game-artifact').first().waitFor();
  const tab=page.getByRole('tab',{name:'Host Fix Fox',exact:true});
  if(await tab.count()) await tab.click();
  else {await page.getByRole('button',{name:/更多标签/}).click(); await page.getByRole('menuitem',{name:'Host Fix Fox',exact:true}).click();}
  await page.getByRole('heading',{name:'狐狸',exact:true}).waitFor();
  assert(await selector.inputValue() === gameId, 'Game identity changed after Artifact switch');
  return {gameId,version:result.outcome.game.version,executedTicks:result.outcome.report.ticks_completed,runId:result.run_id,artifactIds:result.artifact_ids,selectedEntity:'狐狸',specificTabTitle:'Host Fix Fox'};
}
