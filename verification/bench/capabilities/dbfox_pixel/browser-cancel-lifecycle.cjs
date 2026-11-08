async(page)=>{
  let release,arrived;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/api/v1/conversations/*';let sessionStatus;
  const handler=async route=>{if(route.request().method()!=='GET'||!/\/conversations\/[^/?]+$/.test(route.request().url()))return route.continue();const response=await route.fetch();sessionStatus=response.status();arrived();await held;try{await route.fulfill({response});}catch{/* Captured generation was canceled. */}};
  const probe=()=>page.evaluate(async()=>{const {getRuntimeSession}=await import('/src/lib/api/client.ts');return {generation:getRuntimeSession().generation,styles:document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length};});
  await page.route(pattern,handler);
  try{
    const before=await probe(),pending=page.waitForResponse(r=>r.url().includes('/operations/documents.export'));
    await page.getByRole('button',{name:'导出成果',exact:true}).click();const artifact=await(await pending).json();await entered;
    await page.getByRole('button',{name:'扩展',exact:true}).click();await page.getByRole('button',{name:'停用',exact:true}).click();await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
    await page.getByText('未激活',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===0);const disabled=await probe();
    await page.getByRole('button',{name:'启用',exact:true}).click();await page.getByRole('button',{name:'立即重启',exact:true}).first().click();await page.getByText('当前已激活',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===1);const active=await probe();
    release();await page.getByRole('button',{name:'返回工作区',exact:true}).click();await page.waitForTimeout(200);
    const lateTab=await page.evaluate(async id=>{const m=await import('/src/stores/workspaceStore.ts');return m.selectActiveDockTabs(m.useWorkspaceStore.getState()).some(tab=>tab.target?.id===id);},artifact.artifact_ids[0]);
    if(lateTab||disabled.styles||active.generation<=before.generation)throw new Error('Old export survived lifecycle cancellation');
    return {artifact,sessionStatus,before,disabled,active,lateTab};
  }finally{release();await page.unroute(pattern,handler);}
}
