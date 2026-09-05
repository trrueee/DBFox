async (page) => {
  let release,arrived,first=true;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/operations/documents.apply?*',responses=[];
  const handler=async route=>{if(first){first=false;arrived();await held;}await route.continue();};
  const listener=response=>{if(response.url().includes('/operations/documents.apply'))responses.push(response.status());};
  await page.getByRole('button',{name:'交给 Agent',exact:true}).click();
  await page.route(pattern,handler);page.on('response',listener);
  try {
    const rejected=page.waitForResponse(response=>response.url().includes('/operations/documents.apply')&&response.status()===409);
    await page.getByRole('button',{name:'画笔 B',exact:true}).click();
    const canvas=page.getByRole('application',{name:'像素画布 16 × 16',exact:true}),box=await canvas.boundingBox();
    await canvas.click({position:{x:box.width*14.5/16,y:box.height*14.5/16}});
    await entered;
    const human=await page.evaluate(async()=>{
      const {fetchEnginePath}=await import('/src/lib/api/client.ts');const m=await import('/src/stores/workspaceStore.ts'),s=m.useWorkspaceStore.getState();
      const ref=m.selectActiveWorkbench(s).references.find(ref=>ref.authority?.kind==='dbfox.pixel.document');
      const invoke=async(name,payload)=>{const r=await fetchEnginePath(`/dlcs/dbfox.pixel/operations/${name}?project_id=${encodeURIComponent(s.activeProjectId)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok)throw new Error(`Human ${r.status}`);return r.json();};
      const before=await invoke('documents.head',{document_id:ref.authority.id});
      const result=await invoke('documents.apply',{document_id:ref.authority.id,expected_version:before.revision,mutation_id:crypto.randomUUID(),operations:[{kind:'rename',title:'Interactive Pixel human'}]});
      return {before,result,frame:ref.object.id};
    });
    release();const failure=await(await rejected).json();
    await page.waitForFunction(v=>document.querySelector('.dbfox-pixel__heading small')?.textContent?.endsWith(`r${v}`),human.result.revision);
    await page.waitForTimeout(250);
    const alert=await page.locator('[role=alert]').allTextContents();
    if(responses.filter(status=>status===409).length!==1 || responses.length!==2)throw new Error(`Unexpected automatic replay: ${responses}`);
    return {human,failure,responses,alert,heading:await page.locator('.dbfox-pixel__heading').innerText()};
  } finally {release();await page.unroute(pattern,handler);page.off('response',listener);}
}
