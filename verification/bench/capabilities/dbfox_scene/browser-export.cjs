async (page) => {
  const result = page.waitForResponse(r => r.url().includes('/operations/scenes.artifact') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'导出工件',exact:true}).click();
  const response = await result;
  await page.getByRole('button', {name:'下载 GLB',exact:true}).waitFor({timeout:20000});
  await page.screenshot({path:'output/playwright/scene-artifact.png'});
  return {status:response.status(),body:await response.json()};
}
