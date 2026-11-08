async(page) => {
  await page.getByRole('button',{name:'灯塔归途 · 2 页 · v6',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.comic-version')?.textContent==='v6 · 2 页');
  await page.getByRole('button',{name:'页面属性',exact:true}).click();
  await page.getByRole('textbox',{name:'标题',exact:true}).fill('CSP 实际编辑');
  await page.getByRole('button',{name:'保存修改',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.comic-version')?.textContent==='v7 · 2 页');
  await page.getByText('历史与恢复',{exact:true}).click();
  await page.getByRole('spinbutton',{name:'目标版本',exact:true}).fill('6');
  await page.getByRole('button',{name:'恢复为新版本',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.comic-version')?.textContent==='v8 · 2 页');
  await page.getByRole('button',{name:'导出工件',exact:true}).click();
  await page.locator('.comic-artifact svg').first().waitFor();
  if(!(await page.locator('.comic-artifact').innerText()).includes('独立验收：灯光仍在。第二行保留对白。'))throw Error('Production content missing');
  await page.getByRole('button',{name:'下载 JSON',exact:true}).click();
  await page.getByRole('button',{name:'下载 HTML',exact:true}).click();
  await page.getByRole('combobox',{name:'页面',exact:true}).selectOption({label:'留下的光'});
  await page.waitForFunction(()=>document.querySelector('.comic-artifact svg')?.getAttribute('aria-label')==='留下的光');
  await page.screenshot({path:'output/playwright/comic-independent/production-csp-artifact.png'});
  await page.getByRole('tab',{name:'灯塔归途',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.comic-version')?.textContent==='v8 · 2 页');
  if(await page.locator('.comic-studio h2').innerText()!=='灯塔归途')throw Error('Returned to wrong work');
  await page.getByRole('button',{name:'02 留下的光',exact:true}).click();
  await page.getByRole('button',{name:'分镜',exact:true}).click();
  await page.screenshot({path:'output/playwright/comic-independent/production-csp-studio.png'});
  return {version:await page.locator('.comic-version').innerText(),alerts:await page.getByRole('alert').allTextContents(),viewport:await page.evaluate(()=>innerWidth)};
}
