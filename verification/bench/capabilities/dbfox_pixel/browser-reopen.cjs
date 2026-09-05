async(page)=>{
  await page.getByRole('button',{name:'关闭 Pixel Studio',exact:true}).click();
  await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).last().click();
  await page.getByText('此项目还没有像素作品。创建作品后即可绘制，也可交给 Agent 继续修改。',{exact:true}).waitFor();
  const tabs=await page.getByRole('tab',{name:'Pixel Studio',exact:true}).count();
  const styles=await page.locator('link[data-dbfox-dlc="dbfox.pixel"]').count();
  if(tabs!==1||styles!==1)throw new Error('Reopening created duplicate views or styles');
  return {tabs,styles,reopened:true,entrypoint:'Pixel resource button; this DLC has no Tree leaf'};
}
