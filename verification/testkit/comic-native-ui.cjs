// Run with playwright-cli run-code --filename against a fresh browser_fixture native window. Screenshots go to the command cwd.
async (page) => {
  await page.getByRole('button', {name:'打开 Comic Studio',exact:true}).click();
  await page.getByRole('button', {name:'工作区全屏',exact:true}).click();
  await page.getByRole('button', {name:'灯塔归途 · 2 页 · v3',exact:true}).click();
  await page.getByRole('button', {name:'对白 · 我们终于到家了。',exact:true}).click();
  await page.getByRole('button', {name:'编辑对象',exact:true}).click();
  await page.getByRole('textbox', {name:'文字内容',exact:true}).fill('灯塔亮了。\n我们终于回到家了！');
  await page.getByRole('button', {name:'保存修改',exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.comic-version')?.textContent.includes('v4'));
  await page.getByRole('button', {name:'导出工件',exact:true}).click();
  await page.locator('.comic-artifact svg').first().waitFor();
  await page.getByRole('tab', {name:'灯塔归途',exact:true}).click();
  await page.getByRole('button', {name:'角色位置 · 归来的旅行者',exact:true}).click();
  const canvas = page.locator('.comic-studio .comic-canvas');
  await canvas.focus(); await canvas.press('ArrowRight');
  await page.waitForFunction(() => document.querySelector('.comic-version')?.textContent.includes('v5'));
  const object = page.locator('.comic-studio [data-object-id="traveler"]');
  const box = await object.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.mouse.down(); await page.mouse.move(box.x+box.width/2+24,box.y+box.height/2+12,{steps:6}); await page.mouse.up();
  await page.waitForFunction(() => document.querySelector('.comic-version')?.textContent.includes('v6'));
  await page.getByRole('button', {name:'分镜',exact:true}).click();
  await page.getByRole('button', {name:'角色位置 · 归来的旅行者',exact:true}).click();
  await page.locator('.comic-shot-card .comic-canvas').first().focus();
  await page.locator('.comic-shot-card .comic-canvas').first().press('ArrowLeft');
  await page.waitForFunction(() => document.querySelector('.comic-version')?.textContent.includes('v7'));
  await page.screenshot({path:'comic-native-storyboard.png'});
  await page.getByRole('button', {name:'页面',exact:true}).click();
  await page.getByRole('button', {name:'页面属性',exact:true}).click();
  await page.getByRole('textbox', {name:'标题',exact:true}).fill('归途 · 黄昏');
  await page.getByRole('button', {name:'保存修改',exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.comic-version')?.textContent.includes('v8'));
  await page.getByRole('tab', {name:'灯塔归途 · v4',exact:true}).click();
  await page.locator('.comic-artifact select').selectOption('page2');
  await page.waitForFunction(() => document.querySelector('.comic-artifact svg')?.getAttribute('aria-label') === '留下的光');
  await page.screenshot({path:'comic-native-artifact-v4.png'});
  return {historicalVersion:await page.locator('.comic-artifact h3').innerText(),historicalPages:await page.locator('.comic-artifact option').allTextContents(),alerts:await page.getByRole('alert').allTextContents()};
}
