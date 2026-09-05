async (page) => {
  if(await page.getByRole('button',{name:'退出工作区全屏',exact:true}).count())await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
  await page.getByRole('button',{name:/^保存体素快照 \d/}).first().click();
  const reads=[];const pending=[];
  const listener=r=>{if(r.url().includes('/representations/'))pending.push(r.json().then(data=>reads.push({status:r.status(),operation:data.operation,
    source_version:data.source_version,source_fingerprint:data.source_fingerprint,world_version:data.payload?.version,chunks:data.payload?.chunks?.length})));};
  page.on('response',listener);
  const cdp=await page.context().browser().newBrowserCDPSession();
  try {
    await page.getByRole('button',{name:'查看导出快照',exact:true}).click();
    await page.getByRole('button',{name:'工作区全屏',exact:true}).click();
    const download=page.getByRole('button',{name:'下载世界快照 JSON',exact:true});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(e=>e.textContent==='下载世界快照 JSON'&&!e.disabled));
    await page.locator('.voxel-snapshot .voxel-viewport-status').filter({hasText:'表面方块'}).waitFor();
    await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-historical.png'});
    const before={title:await page.locator('.voxel-snapshot header').innerText(),status:await page.locator('.voxel-snapshot .voxel-viewport-status').innerText(),
      editableCanvases:await page.getByRole('application',{name:/体素切片/}).count()};
    await page.getByRole('group',{name:'快照图层显示',exact:true}).getByRole('checkbox').first().uncheck();
    await page.getByText('0 个表面方块',{exact:true}).waitFor();
    await cdp.send('Browser.setDownloadBehavior',{behavior:'default',eventsEnabled:true});
    const starts=[];cdp.on('Browser.downloadWillBegin', event=>starts.push({guid:event.guid,filename:event.suggestedFilename}));
    const finished=new Promise(resolve=>{cdp.on('Browser.downloadProgress',event=>{if(event.state==='completed'||event.state==='canceled')resolve(event);});});
    await download.click();
    const result=await Promise.race([finished,page.waitForTimeout(20000).then(()=>{throw new Error('Native DownloadItem did not finish');})]);
    await Promise.all(pending);
    return {before,reads,starts,download:result,hiddenLayersExcludedFromDownload:false,boundary:'real Electron DownloadItem; verification-only setSavePath; no renderer filesystem writes'};
  } finally {page.off('response',listener);await cdp.detach();}
}
