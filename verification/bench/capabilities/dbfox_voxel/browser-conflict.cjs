async (page) => {
  const pattern='**/operations/worlds.apply*';let requests=0;let observed;
  const read=page.waitForResponse(r=>r.url().includes('/operations/worlds.get')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'刷新',exact:true}).click();
  const initial=await(await read).json();
  const before=await page.locator('.voxel-header').innerText();
  const version=initial.version;
  const handler=async route=>{
    requests++;
    for(let i=0;i<75;i++) {
      const response=await route.fetch({url:route.request().url().replace('worlds.apply','worlds.get'),postData:JSON.stringify({world_id:initial.world_id})});
      const current=await response.json();observed=current.version;
      if(current.version>version)break;
      await page.waitForTimeout(200);
    }
    await route.continue();
  };
  await page.route(pattern,handler);
  try {
    const response=page.waitForResponse(r=>r.url().includes('/operations/worlds.apply')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'应用到选区',exact:true}).click();
    const result=await response;
    await page.getByRole('alert').waitFor();
    const alert=await page.getByRole('alert').innerText();
    await page.waitForFunction(()=>!document.querySelector('.voxel-inspector button:last-of-type')?.disabled);
    return {before,observed,status:result.status(),response:await result.json(),requests,alert,after:await page.locator('.voxel-header').innerText()};
  }finally{await page.unroute(pattern,handler);}
}
