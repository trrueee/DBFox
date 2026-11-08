async (page) => {
  // Start without retained tree selection or an already-mounted Voxel view.
  await page.reload();
  await page.getByRole('treeitem',{name:'Interactive Voxel',exact:true}).waitFor();
  if(await page.getByRole('button',{name:'退出工作区全屏',exact:true}).count())await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
  const cdp=await page.context().newCDPSession(page);
  const group='voxel-verifier-held-control';
  const documentObject=(await cdp.send('Runtime.evaluate',{expression:'document',objectGroup:group})).result.objectId;
  const native=async id=>(await cdp.send('DOMDebugger.getEventListeners',{objectId:id})).listeners.map(e=>({type:e.type,useCapture:e.useCapture,scriptId:e.scriptId,lineNumber:e.lineNumber,columnNumber:e.columnNumber}));
  const baseline=await native(documentObject);
  const requests=[];
  const onRequest=request=>{if(request.url().includes('/operations/worlds.'))requests.push(request.url().split('/operations/')[1].split('?')[0]);};
  let handle;
  try {
    await page.getByRole('treeitem',{name:'Interactive Voxel',exact:true}).click();
    const viewport=page.getByLabel(/^体素三维视口/);
    await page.locator('.voxel-viewport-status').filter({hasText:'表面方块'}).waitFor();
    handle=await viewport.elementHandle();
    const canvasObject=(await cdp.send('Runtime.evaluate',{expression:'document.querySelector("canvas[aria-label^=体素三维视口]")',objectGroup:group})).result.objectId;
    await viewport.focus();
    await page.keyboard.down('Control');
    const heldDocument=await native(documentObject);
    const before={canvas:await native(canvasObject),documentAdded:heldDocument.filter(e=>!baseline.some(b=>JSON.stringify(b)===JSON.stringify(e))),
      connected:await handle.evaluate(e=>e.isConnected)};
    // A title-bar close click while Control is still held tests real unmount ordering.
    await page.getByRole('button',{name:'关闭 Interactive Voxel',exact:true}).click();
    const afterDocument=await native(documentObject);
    const after={canvas:await native(canvasObject),documentAdded:afterDocument.filter(e=>!baseline.some(b=>JSON.stringify(b)===JSON.stringify(e))),
      ownerDocumentRemaining:afterDocument.filter(e=>before.documentAdded.some(b=>JSON.stringify(b)===JSON.stringify(e))),
      connected:await handle.evaluate(e=>e.isConnected),lost:await handle.evaluate(e=>e.getContext('webgl2').isContextLost())};
    await page.keyboard.up('Control');
    page.on('request',onRequest);
    await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
    await page.waitForTimeout(3500);
    // Host close-button tooltips may add their own listeners after the baseline.
    // Every document listener installed while this Voxel view opened must leave.
    if(after.canvas.length||after.ownerDocumentRemaining.length||after.connected||!after.lost||requests.length)throw new Error(JSON.stringify({before,after,requests}));
    return {before,after,requestsAfterClose:requests,canvases:await page.locator('canvas').count(),boundary:'real signed Electron; native Control held across React unmount; CDP event listener inspection'};
  }finally{
    page.off('request',onRequest);await page.keyboard.up('Control');await page.unrouteAll({behavior:'wait'});
    await cdp.send('Runtime.releaseObjectGroup',{objectGroup:group});await cdp.detach();await handle?.dispose();
  }
}
