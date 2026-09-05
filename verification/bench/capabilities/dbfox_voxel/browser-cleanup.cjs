async (page) => {
  const canvas=await page.getByLabel(/^体素三维视口/).elementHandle();
  const cdp=await page.context().newCDPSession(page);
  const object=await cdp.send('Runtime.evaluate',{expression:'document.querySelector("canvas[aria-label^=体素三维视口]")',objectGroup:'voxel-verifier-cleanup'});
  try {
    const before=await canvas.evaluate(e=>({connected:e.isConnected,lost:e.getContext('webgl2').isContextLost()}));
    const listenersBefore=(await cdp.send('DOMDebugger.getEventListeners',{objectId:object.result.objectId})).listeners.map(item=>item.type);
    await page.getByRole('button',{name:'关闭 Interactive Voxel',exact:true}).click();
    const after=await canvas.evaluate(e=>({connected:e.isConnected,lost:e.getContext('webgl2').isContextLost()}));
    const listenersAfter=(await cdp.send('DOMDebugger.getEventListeners',{objectId:object.result.objectId})).listeners.map(item=>item.type);
    const requests=[];const onRequest=request=>{if(request.url().includes('/operations/worlds.'))requests.push(request.url().split('/operations/')[1].split('?')[0]);};
    page.on('request',onRequest);
    await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
    await page.waitForTimeout(3500);
    page.off('request',onRequest);
    await page.unrouteAll({behavior:'wait'});
    return {before,after,listenersBefore,listenersAfter,requestsAfterClose:requests,canvases:await page.locator('canvas').count(),
      generation:await page.evaluate(async()=>{const state=await window.dbfoxDesktop.engine.getStatus();return {generation:state.generation,state:state.state};}),
      routesRemoved:true,debuggerObjectReleased:true};
  }finally{await cdp.send('Runtime.releaseObjectGroup',{objectGroup:'voxel-verifier-cleanup'});await cdp.detach();await canvas.dispose();}
}
