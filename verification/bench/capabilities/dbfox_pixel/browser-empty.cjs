async(page)=>{
  if(await page.getByRole('button',{name:'退出工作区全屏',exact:true}).count())await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
  await page.getByRole('button',{name:'Pixel Other Scope',exact:true}).click();
  let release,arrived;const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/operations/documents.list?project_id=pixel-browser-other';
  const handler=async route=>{const response=await route.fetch();if(response.status()!==200)throw new Error('Actual empty list failed');arrived();await held;try{await route.fulfill({response});}catch{/* Scope cancellation is allowed. */}};
  await page.route(pattern,handler);
  try{
    await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).last().click();await entered;
    const loading=await page.getByText('正在读取作品目录…',{exact:true}).isVisible();release();
    await page.getByText('此项目还没有像素作品。创建作品后即可绘制，也可交给 Agent 继续修改。',{exact:true}).waitFor();
    let creates=0;const listener=request=>{if(request.url().includes('/operations/documents.create'))creates++;};page.on('request',listener);
    let invalid;
    try{
      await page.getByRole('spinbutton',{name:'宽度',exact:true}).fill('129');
      await page.getByRole('group',{name:'创建作品',exact:true}).getByRole('button',{name:'创建像素作品',exact:true}).click();
      invalid=await page.getByRole('spinbutton',{name:'宽度',exact:true}).evaluate(input=>!input.validity.valid);
      await page.waitForTimeout(100);
    }finally{page.off('request',listener);}
    if(!loading||!invalid||creates)throw new Error('Empty/loading/invalid form gate failed');
    await page.getByRole('spinbutton',{name:'宽度',exact:true}).fill('32');
    return {loading,empty:true,invalidWidthBlocked:invalid,createRequests:creates};
  }finally{release();await page.unroute(pattern,handler);}
}
