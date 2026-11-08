async (page) => {
  let release,arrived;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/api/v1/conversations/*';
  let originalStatus;
  const handler=async route=>{
    if(route.request().method()!=='GET'||!/\/conversations\/[^/?]+$/.test(route.request().url()))return route.continue();
    const original=await route.fetch();originalStatus=original.status();arrived();await held;
    try {await route.fulfill({response:original});}catch{/* Scope cancellation may already have aborted this request. */}
  };
  await page.route(pattern,handler);
  try {
    const response=page.waitForResponse(r=>r.url().includes('/operations/documents.export'));
    await page.getByRole('button',{name:'导出成果',exact:true}).click();
    const artifact=await(await response).json();
    await Promise.race([entered,page.waitForTimeout(15000).then(()=>{throw new Error('Formal session response never arrived');})]);
    await page.getByRole('button',{name:'Pixel Other Scope',exact:true}).click();release();await page.waitForTimeout(350);
    const check=()=>page.evaluate(async id=>{const m=await import('/src/stores/workspaceStore.ts'),s=m.useWorkspaceStore.getState();return {project:s.activeProjectId,hasArtifact:m.selectActiveDockTabs(s).some(tab=>tab.target?.id===id)};},artifact.artifact_ids[0]);
    const switched=await check();
    await page.getByRole('button',{name:'Pixel Browser QA',exact:true}).click();await page.waitForTimeout(200);
    const returned=await check();
    if(switched.hasArtifact||returned.hasArtifact)throw new Error('A canceled scope opened the late Artifact');
    return {artifact,originalStatus,switched,returned};
  } finally {release();await page.unroute(pattern,handler);}
}
