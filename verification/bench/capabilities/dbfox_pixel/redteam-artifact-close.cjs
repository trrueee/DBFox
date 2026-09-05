async(page)=>{
  await page.getByRole('button',{name:'交给 Agent',exact:true}).click();
  const state=()=>page.evaluate(async()=>{const m=await import('/src/stores/workspaceStore.ts'),s=m.useWorkspaceStore.getState();return {project:s.activeProjectId,workbench:m.selectActiveWorkbench(s)};});
  const before=await state();
  let release,arrived;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/api/v1/conversations/*';let sessionStatus,posts=0;
  const onRequest=request=>{if(request.method()==='POST'&&request.url().includes('/operations/documents.export'))posts++;};
  const handler=async route=>{if(route.request().method()!=='GET'||!/\/conversations\/[^/?]+$/.test(route.request().url()))return route.continue();
    const original=await route.fetch();sessionStatus=original.status();arrived();await held;
    try{await route.fulfill({response:original});}catch{/* Closed editor's AbortSignal may have cancelled it. */}};
  await page.route(pattern,handler);page.on('request',onRequest);
  let cancelled;
  try{
    const pending=page.waitForResponse(r=>r.url().includes('/operations/documents.export')&&r.status()===200);
    await page.getByRole('button',{name:'导出成果',exact:true}).click();cancelled=await(await pending).json();
    await Promise.race([entered,page.waitForTimeout(15000).then(()=>{throw new Error('No formal Session GET to delay');})]);
    const close=page.getByRole('button',{name:'关闭 Pixel Studio',exact:true});await close.focus();await close.press('Space');
    await page.getByRole('application',{name:'像素画布 16 × 16',exact:true}).waitFor({state:'detached'});
    await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).click();await page.getByRole('button',{name:'打开作品',exact:true}).click();
    await page.getByRole('application',{name:'像素画布 16 × 16',exact:true}).waitFor();
    release();await page.waitForTimeout(400);
    const reopened=await state();
    if(posts!==1||reopened.workbench.tabs.some(tab=>tab.target?.id===cancelled.artifact_ids[0]))throw new Error('Old closed editor navigated or replayed export');
  }finally{release();await page.unroute(pattern,handler);page.off('request',onRequest);}
  const next=page.waitForResponse(r=>r.url().includes('/operations/documents.export')&&r.status()===200);
  await page.getByRole('button',{name:'导出成果',exact:true}).click();const current=await(await next).json();
  const preview=page.locator('.dbfox-pixel__artifact-image');await preview.waitFor();
  await page.waitForFunction(()=>document.querySelector('.dbfox-pixel__artifact-image')?.naturalWidth===16);
  const bytes=await preview.evaluate(async image=>{const data=await(await fetch(image.src)).arrayBuffer();const hash=await crypto.subtle.digest('SHA-256',data);return {width:image.naturalWidth,height:image.naturalHeight,bytes:data.byteLength,sha256:[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')};});
  await page.getByRole('button',{name:'加入对话上下文',exact:true}).click();
  const after=await state();
  const reference=after.workbench.references.find(ref=>ref.artifactId===current.artifact_ids[0]);
  if(!reference||reference.object||reference.authority)throw new Error('Host Artifact reference forged authority or object kind');
  await page.screenshot({path:'output/playwright/pixel-redteam-artifact.png'});
  return {before,cancelled,sessionStatus,closedEditorExportPosts:posts,current,preview:bytes,after};
}
