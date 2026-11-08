async(page)=>{
  if(!await page.getByRole('application',{name:'像素画布 32 × 32',exact:true}).count()){
    await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).first().click();
    await page.getByRole('button',{name:'打开作品',exact:true}).first().click();
  }
  const canvas=page.getByRole('application',{name:'像素画布 32 × 32',exact:true});await canvas.waitFor();
  if(await page.getByRole('button',{name:'工作区全屏',exact:true}).count())await page.getByRole('button',{name:'工作区全屏',exact:true}).click();
  await page.getByRole('combobox',{name:'播放动画标签',exact:true}).selectOption({label:'Attack'});
  await page.getByRole('button',{name:'播放动画',exact:true}).click();
  const labels=new Set();for(let i=0;i<10;i++){labels.add(await page.locator('canvas[aria-label^="动画预览"]').getAttribute('aria-label'));await page.waitForTimeout(80);}
  const finishedNaturally=await page.getByRole('button',{name:'暂停播放',exact:true}).count()===0;
  if(!finishedNaturally)await page.getByRole('button',{name:'暂停播放',exact:true}).click();
  if(labels.size<3)throw new Error('Attack animation did not advance');
  await page.screenshot({path:'output/playwright/pixel-fox-knight.png'});
  await page.setViewportSize({width:375,height:812});
  await page.getByRole('button',{name:'适应画布',exact:true}).click();
  await canvas.focus();await canvas.press('ArrowRight');
  const measurements=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
    canvas:document.querySelector('[role=application]').getBoundingClientRect().toJSON(),activeElement:document.activeElement?.getAttribute('role'),status:document.querySelector('.dbfox-pixel__canvas-status')?.textContent??null,styles:document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length}));
  await page.screenshot({path:'output/playwright/pixel-mobile-layout.png'});
  await canvas.press('Tab');const nextFocus=await page.evaluate(()=>({tag:document.activeElement.tagName,label:document.activeElement.getAttribute('aria-label')}));
  await page.setViewportSize({width:1280,height:900});
  return {attackPreview:[...labels],finishedNaturally,measurements,nextFocus};
}
