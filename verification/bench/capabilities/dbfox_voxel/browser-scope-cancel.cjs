async (page) => {
  const pattern='**/operations/worlds.snapshot*';let release;let captured;let requests=0;let entered;
  const waiting=new Promise(resolve=>{entered=resolve;});const gate=new Promise(resolve=>{release=resolve;});
  const routeHandler=async route=>{
    requests++;
    const response=await route.fetch();captured={status:response.status(),payload:await response.json()};entered();
    await gate;
    await route.fulfill({response}).catch(()=>{});
  };
  await page.route(pattern,routeHandler);
  try {
    const beforeTabs=await page.getByRole('tab').allTextContents();
    await page.getByRole('button',{name:'保存快照',exact:true}).click();
    await Promise.race([waiting,page.waitForTimeout(10000).then(()=>{throw new Error('Route did not observe the real export');})]);
    if(await page.getByRole('button',{name:'退出工作区全屏',exact:true}).count())await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
    await page.getByRole('button',{name:'Voxel Empty QA',exact:true}).click();
    const empty={studio:await page.getByRole('region',{name:'Voxel Studio',exact:true}).count(),historical:await page.getByRole('article',{name:'不可变体素快照',exact:true}).count()};
    await page.getByRole('button',{name:'Voxel Independent QA',exact:true}).click();
    release();
    await page.waitForTimeout(500);
    return {beforeTabs,afterTabs:await page.getByRole('tab').allTextContents(),empty,captured,requests,
      historicalViews:await page.getByRole('article',{name:'不可变体素快照',exact:true}).count(),boundary:'real response held only after ActionRun commit; scope switch before browser delivery'};
  }finally{release?.();await page.unroute(pattern,routeHandler);}
}
