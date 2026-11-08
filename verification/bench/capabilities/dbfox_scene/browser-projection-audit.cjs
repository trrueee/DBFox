async (page) => {
  return page.evaluate(async()=>{
    const {useWorkspaceStore,selectActiveConversationId,selectActiveDockTabs,selectActiveDockViewKey,selectActiveWorkbenchScopeId}=await import('/src/stores/workspaceStore.ts');
    const {useConversationStore}=await import('/src/stores/conversationStore.ts');
    const workspace=useWorkspaceStore.getState();
    return {activeProjectId:workspace.activeProjectId,activeConversationId:selectActiveConversationId(workspace),
      tabs:selectActiveDockTabs(workspace),activeDockKey:selectActiveDockViewKey(workspace),scope:selectActiveWorkbenchScopeId(workspace),
      artifactIds:Object.keys(useConversationStore.getState().artifactsById),
      stylesheetCount:document.querySelectorAll('link[data-dbfox-dlc="dbfox.scene"]').length};
  });
}
