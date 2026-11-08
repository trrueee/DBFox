async (page) => {
  const before=await page.locator('.voxel-header').innerText();
  const pattern='**/operations/worlds.get*';let release;let entered;
  const waiting=new Promise(resolve=>{entered=resolve;});const gate=new Promise(resolve=>{release=resolve;});
  await page.route(pattern,async route=>{entered();await gate;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Independent read outage'})});});
  try {
    await page.getByRole('button',{name:'刷新',exact:true}).click();
    await Promise.race([waiting,page.waitForTimeout(10000).then(()=>{throw new Error('Read route not reached');})]);
    const loading=await page.locator('.voxel-version').innerText();release();
    await page.getByRole('alert').waitFor();
    const failure={alert:await page.getByRole('alert').innerText(),editingDisabled:await page.getByRole('button',{name:'应用到选区',exact:true}).isDisabled(),
      preservedHeader:await page.locator('.voxel-header').innerText(),canvases:await page.locator('.voxel-studio canvas').count()};
    await page.unroute(pattern);
    await page.getByRole('button',{name:'刷新',exact:true}).click();
    await page.getByRole('alert').waitFor({state:'detached'});
    return {before,loading,failure,recovered:await page.locator('.voxel-header').innerText()};
  }finally{release?.();await page.unroute(pattern);}
}
