async (page) => {
  const canvas = page.locator('.dbfox-scene canvas');
  const box = await canvas.boundingBox();
  const mutations = [];
  const onRequest = request => { if (request.url().includes('/operations/scenes.apply') && request.method() === 'POST') mutations.push(request.postDataJSON()); };
  page.on('request', onRequest);
  try {
    const before = await canvas.screenshot();
    await page.mouse.move(box.x + 70, box.y + 100);
    await page.mouse.down();
    await page.mouse.move(box.x + 155, box.y + 132, {steps:12});
    await page.mouse.up();
    const after = await canvas.screenshot();
    if (before.equals(after) || mutations.length) throw new Error('Orbit did not change rendered pixels independently of durable state');
    await page.getByRole('treeitem', {name:'Controls Cube', exact:true}).click();
    await page.getByRole('spinbutton', {name:'位置 Y', exact:true}).waitFor();
    await page.getByRole('button', {name:'聚焦 F', exact:true}).click();
    await page.mouse.click(box.x + 15, box.y + 15);
    await page.getByRole('textbox', {name:'场景名称', exact:true}).waitFor();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.getByRole('textbox', {name:'对象名称', exact:true}).waitFor();
    const picked = await page.getByRole('textbox', {name:'对象名称', exact:true}).inputValue();
    if (picked !== 'Controls Cube') throw new Error('Native canvas raycast did not select the cube');
    await page.getByRole('spinbutton', {name:'位置 Y', exact:true}).fill('1.5');
    const saved = page.waitForResponse(response => response.url().includes('/operations/scenes.apply') && response.request().method() === 'POST');
    await page.getByRole('button', {name:'保存局部变换', exact:true}).click();
    const response = await saved;
    const result = await response.json();
    await page.getByRole('button', {name:'刷新', exact:true}).click();
    await page.getByRole('spinbutton', {name:'位置 Y', exact:true}).waitFor();
    if (response.status() !== 200 || result.scene.version !== 3 || await page.getByRole('spinbutton', {name:'位置 Y', exact:true}).inputValue() !== '1.5') throw new Error('Inspector did not persist and reload the local transform');
    await page.getByRole('button', {name:'聚焦 F', exact:true}).click();
    await page.screenshot({path:'output/playwright/scene-controls-interact.png'});
    return {orbitPixelsChanged:true, orbitMutationCount:0, picked, inspector:{status:response.status(), result, requests:mutations}, probe:await page.evaluate(() => sceneControlsProbe.read())};
  } finally { page.off('request', onRequest); }
}
