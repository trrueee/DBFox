async (page) => {
  await page.getByRole('button',{name:'交给 Agent',exact:true}).click();
  return page.evaluate(async()=>{
    const {fetchEnginePath,getRuntimeSession}=await import('/src/lib/api/client.ts');
    const m=await import('/src/stores/workspaceStore.ts'),state=m.useWorkspaceStore.getState();
    const ref=m.selectActiveWorkbench(state).references.find(ref=>ref.authority?.kind==='dbfox.pixel.document');
    if(!ref)throw new Error('No real user-selected Pixel reference');
    const generation=getRuntimeSession().generation,started=performance.now();let head;
    for(let index=0;index<1100;index++){
      const response=await fetchEnginePath(`/dlcs/dbfox.pixel/operations/documents.head?project_id=${encodeURIComponent(state.activeProjectId)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document_id:ref.authority.id}),signal:AbortSignal.timeout(5000)});
      if(!response.ok)throw new Error(`Read ${index} returned ${response.status}`);
      head=await response.json();
    }
    if(getRuntimeSession().generation!==generation)throw new Error('A hidden Engine restart masked the stream failure');
    return {requests:1100,status:200,generation,milliseconds:performance.now()-started,head};
  });
}
