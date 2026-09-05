async (page) => {
  const results=[];
  const cdp=await page.context().browser().newBrowserCDPSession();
  await cdp.send('Browser.setDownloadBehavior',{behavior:'default',eventsEnabled:true});
  const started=[];
  cdp.on('Browser.downloadWillBegin', event=>started.push({guid:event.guid,filename:event.suggestedFilename,url:event.url}));
  try {
  for (const [label,suffix] of [['下载 GLB','glb'],['下载 glTF','gltf']]) {
    const response=page.waitForResponse(r=>r.url().includes('/representations/') && r.request().method()==='POST');
    const download=new Promise(resolve=>{
      const listener=event=>{if(event.state==='completed'||event.state==='canceled'){cdp.off('Browser.downloadProgress',listener);resolve(event);}};
      cdp.on('Browser.downloadProgress',listener);
    });
    await page.getByRole('button',{name:label,exact:true}).click();
    const item=await Promise.race([download,page.waitForTimeout(20000).then(()=>{throw new Error('Download did not complete within 20s');})]);
    const streamed=await response;
    const start=started.find(event=>event.guid===item.guid);
    const blob=await page.evaluate(async url=>{const response=await fetch(url);const bytes=await response.arrayBuffer();const digest=await crypto.subtle.digest('SHA-256',bytes);return {status:response.status,bytes:bytes.byteLength,sha256:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('')};},start.url);
    results.push({format:suffix,filename:start.filename,download:item,status:streamed.status(),blob});
  }
  return results;
  } finally { await cdp.detach(); }
}
