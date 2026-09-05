async (page) => {
  // Run after browser-open.cjs in the isolated real Electron fixture.
  await page.locator('canvas').waitFor({state:'visible'});
  await page.getByRole('button',{name:'引用到 Agent',exact:true}).click();
  const documentReferences=await page.evaluate(async()=>{
    const module=await import('/src/stores/workspaceStore.ts');
    return module.selectActiveWorkbench(module.useWorkspaceStore.getState()).references;
  });
  const pending=page.waitForResponse(response=>response.url().includes('/operations/scenes.artifact') && response.request().method()==='POST');
  await page.getByRole('button',{name:'导出工件',exact:true}).click();
  const exported=await (await pending).json();
  await page.getByRole('button',{name:'下载 GLB',exact:true}).waitFor();
  const action=page.locator('.workspace-artifact-context-action button');
  const actualButtonLabel=await action.innerText();
  await action.click();
  const after=await page.evaluate(async()=>{
    const module=await import('/src/stores/workspaceStore.ts');
    const state=module.useWorkspaceStore.getState();
    return {project:state.activeProjectId,conversation:state.activeConversationId??null,
      references:module.selectActiveWorkbench(state).references};
  });
  const generic=after.references.find(reference=>reference.artifactId===exported.artifact_id);
  if(!generic || generic.authority || generic.object.kind!=='artifact') throw new Error('Actual generic Artifact handoff shape changed');
  await page.screenshot({path:'output/playwright/scene-artifact-reference.png'});
  return {documentReferences,exported,actualButtonLabel,after};
}
