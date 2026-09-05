async (page) => {
  const canvas = page.locator('.dbfox-scene canvas');
  const box = await canvas.boundingBox();
  const x = box.x + box.width / 2 + 72;
  const y = box.y + box.height / 2 + 24;
  const saved = page.waitForResponse(response => response.url().includes('/operations/scenes.apply') && response.request().method() === 'POST', {timeout:8000});
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 42, y + 14, {steps:12});
  await page.mouse.up();
  const response = await saved;
  const result = await response.json();
  await page.getByRole('button', {name:'刷新', exact:true}).click();
  await page.getByRole('spinbutton', {name:'位置 X', exact:true}).waitFor();
  const position = await Promise.all(['X','Y','Z'].map(axis => page.getByRole('spinbutton', {name:`位置 ${axis}`, exact:true}).inputValue()));
  if (response.status() !== 200 || result.scene.version !== 4 || result.changed_ids.join() !== 'controls-cube' || Number(position[0]) === 0 || Number(position[1]) !== 1.5 || Number(position[2]) !== 0) throw new Error('Real Gizmo local X drag did not persist exactly the selected object');
  await page.screenshot({path:'output/playwright/scene-controls-gizmo.png'});
  return {status:response.status(), result, position, gesture:{start:[x,y],end:[x+42,y+14]}};
}
