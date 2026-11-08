async (page) => {
  const results=[],started=[];
  const cdp=await page.context().browser().newBrowserCDPSession();
  await cdp.send('Browser.setDownloadBehavior',{behavior:'default',eventsEnabled:true});
  cdp.on('Browser.downloadWillBegin',event=>started.push(event));
  try {
    for (const [label,format] of [['下载当前帧 PNG','png'],['下载 Sprite Sheet','sheet']]) {
      const response=page.waitForResponse(r=>r.url().includes('/representations/') && r.request().method()==='POST');
      let listener;
      const download=new Promise(resolve=>{listener=event=>{if(['completed','canceled'].includes(event.state)){cdp.off('Browser.downloadProgress',listener);resolve(event);}};cdp.on('Browser.downloadProgress',listener);});
      await page.getByRole('button',{name:label,exact:true}).click();
      let item;
      try {item=await Promise.race([download,page.waitForTimeout(20000).then(()=>{throw new Error('Download did not finish');})]);}
      finally {cdp.off('Browser.downloadProgress',listener);}
      const wire=await response,start=started.find(event=>event.guid===item.guid);
      const blob=await page.evaluate(async url=>{const response=await fetch(url),bytes=await response.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',bytes);return {bytes:bytes.byteLength,sha256:[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')};},start.url);
      if(item.state!=='completed'||wire.status()!==200)throw new Error(JSON.stringify(item));
      results.push({format,filename:start.suggestedFilename,download:item,status:wire.status(),blob});
    }
    const state=await page.evaluate(async()=>{const m=await import('/src/stores/workspaceStore.ts'),s=m.useWorkspaceStore.getState();return {project:s.activeProjectId,conversation:s.activeConversationId??null,workbench:m.selectActiveWorkbench(s)};});
    return {downloads:results,state};
  } finally {await cdp.detach();}
}
