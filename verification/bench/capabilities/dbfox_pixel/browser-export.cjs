async (page) => {
  await page.getByRole('button',{name:'交给 Agent',exact:true}).click();
  const documentReferences=await page.evaluate(async()=>{
    const m=await import('/src/stores/workspaceStore.ts');return m.selectActiveWorkbench(m.useWorkspaceStore.getState()).references;
  });
  const response=page.waitForResponse(r=>r.url().includes('/operations/documents.export')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'导出成果',exact:true}).click();
  const wire=await response;const exported=await wire.json();
  if(wire.status()!==200 || !exported.artifact_ids?.length) throw new Error(JSON.stringify(exported));
  await page.getByRole('button',{name:'下载当前帧 PNG',exact:true}).waitFor();
  const preview=page.locator('img.dbfox-pixel__artifact-image');
  await preview.waitFor();
  const dimensions=await preview.evaluate(img=>({width:img.naturalWidth,height:img.naturalHeight,complete:img.complete}));
  const action=page.getByRole('button',{name:'加入对话上下文',exact:true});await action.click();
  const after=await page.evaluate(async()=>{
    const m=await import('/src/stores/workspaceStore.ts'),state=m.useWorkspaceStore.getState();
    return {project:state.activeProjectId,conversation:state.activeConversationId??null,references:m.selectActiveWorkbench(state).references};
  });
  const generic=after.references.find(r=>r.artifactId===exported.artifact_ids[0]);
  if(!generic || generic.object || generic.authority) throw new Error('Artifact reference unexpectedly grants authority');
  await page.screenshot({path:'output/playwright/pixel-artifact-open.png'});
  return {documentReferences,exported,dimensions,after};
}
