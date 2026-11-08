async (page) => {
  let release;
  const held=new Promise(resolve=>{release=resolve;});
  let arrived;
  const entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/api/v1/conversations/*';
  let originalStatus;
  const handler=async route=>{
    if(route.request().method()!=='GET' || !/\/conversations\/[^/?]+$/.test(route.request().url())) return route.continue();
    const original=await route.fetch();
    originalStatus=original.status();
    arrived();
    await held;
    try { await route.fulfill({response:original}); } catch { /* The consumer may already have aborted. */ }
  };
  await page.route(pattern,handler);
  try {
    const response=page.waitForResponse(r=>r.url().includes('/operations/scenes.artifact'));
    await page.getByRole('button',{name:'导出工件',exact:true}).click();
    const artifact=await (await response).json();
    await Promise.race([entered,page.waitForTimeout(15000).then(()=>{throw new Error('No real session response was intercepted');})]);
    await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
    await page.getByRole('button',{name:'Default Workspace',exact:true}).click();
    release();
    await page.waitForTimeout(350);
    const afterSwitch=await page.evaluate(async id=>{
      const {useWorkspaceStore,selectActiveDockTabs}=await import('/src/stores/workspaceStore.ts');
      const state=useWorkspaceStore.getState();
      return {project:state.activeProjectId,hasArtifact:selectActiveDockTabs(state).some(tab=>tab.target?.id===id)};
    },artifact.artifact_id);
    await page.getByRole('button',{name:'Scene Browser QA',exact:true}).click();
    await page.waitForTimeout(150);
    const afterReturn=await page.evaluate(async id=>{
      const {useWorkspaceStore,selectActiveDockTabs}=await import('/src/stores/workspaceStore.ts');
      const state=useWorkspaceStore.getState();
      return {project:state.activeProjectId,hasArtifact:selectActiveDockTabs(state).some(tab=>tab.target?.id===id)};
    },artifact.artifact_id);
    if(afterSwitch.hasArtifact || afterReturn.hasArtifact) throw new Error('Late artifact navigation crossed the captured scope');
    return {artifact,originalSessionStatus:originalStatus,afterSwitch,afterReturn};
  } finally { release();await page.unroute(pattern,handler); }
}
