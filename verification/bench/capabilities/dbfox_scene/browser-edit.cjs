async (page) => {
  const response = page.waitForResponse(r => r.url().includes('/operations/scenes.apply') && r.request().method() === 'POST');
  await page.mouse.move(767, 600);
  await page.mouse.down();
  await page.mouse.move(820, 619, {steps: 12});
  await page.mouse.up();
  const drag = await response;
  await page.getByRole('button', {name:'刷新', exact:true}).click();
  await page.getByRole('spinbutton', {name:'位置 Y', exact:true}).fill('1.5');
  const saved = page.waitForResponse(r => r.url().includes('/operations/scenes.apply') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'保存局部变换', exact:true}).click();
  const save = await saved;
  await page.getByRole('button', {name:'刷新', exact:true}).click();
  await page.screenshot({path:'output/playwright/scene-edited.png'});
  return {drag:{status:drag.status(), request:drag.request().postDataJSON(), response:await drag.json()},
    inspector:{status:save.status(),request:save.request().postDataJSON(),response:await save.json()}};
}
