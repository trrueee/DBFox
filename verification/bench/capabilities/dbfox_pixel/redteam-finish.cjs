async(page)=>{
  const oldUrl=await page.locator('.dbfox-pixel__artifact-image').getAttribute('src');
  for(let count=0;count<4;count++){
    const close=page.getByRole('button',{name:/^关闭 /});
    if(!await close.count())break;
    await close.first().click();
  }
  let calls=0;const listener=request=>{if(request.method()==='POST'&&request.url().includes('/dlcs/dbfox.pixel/operations/'))calls++;};
  page.on('request',listener);await page.waitForTimeout(1400);page.off('request',listener);
  const result=await page.evaluate(async url=>{let revoked=false;try{await fetch(url);}catch{revoked=true;}
    const m=await import('/src/stores/workspaceStore.ts'),s=m.useWorkspaceStore.getState();return {tabs:m.selectActiveDockTabs(s).length,canvases:document.querySelectorAll('.dbfox-pixel canvas').length,artifactImages:document.querySelectorAll('.dbfox-pixel__artifact-image').length,previewRevoked:revoked,hookRemoved:!window.__pixelRedDownload};},oldUrl);
  if(result.tabs||result.canvases||result.artifactImages||calls||!result.previewRevoked||!result.hookRemoved)throw new Error(JSON.stringify({...result,calls}));
  return {...result,lateOwnerCalls:calls};
}
