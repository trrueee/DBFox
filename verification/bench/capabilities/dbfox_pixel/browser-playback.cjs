async (page) => {
  const labels=new Set();
  for(let i=0;i<8;i++){labels.add(await page.locator('canvas[aria-label^="动画预览"]').getAttribute('aria-label'));await page.waitForTimeout(80);}
  await page.getByRole('button',{name:'暂停播放',exact:true}).click();
  if(labels.size<2) throw new Error('Animation never advanced');
  await page.screenshot({path:'output/playwright/pixel-real-edited.png'});
  return {previewLabels:[...labels],canvasCount:await page.locator('canvas').count(),styles:await page.locator('link[data-dbfox-dlc="dbfox.pixel"]').count()};
}
