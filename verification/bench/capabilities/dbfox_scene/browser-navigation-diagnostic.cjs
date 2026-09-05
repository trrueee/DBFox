async (page) => {
  await page.getByRole('combobox',{name:'打开场景',exact:true}).selectOption({label:'Interactive Scene'});
  await page.getByRole('treeitem',{name:'QA Cube',exact:true}).waitFor();
  const debuggerSession=await page.context().newCDPSession(page);
  const failures=[];
  await debuggerSession.send('Debugger.enable');
  debuggerSession.on('Debugger.paused',async event=>{
    try {
      for (const frame of event.callFrames) {
        if (frame.functionName==='assertCurrent' || frame.functionName==='write') {
          const value=await debuggerSession.send('Debugger.evaluateOnCallFrame',{
            callFrameId:frame.callFrameId,
            expression:frame.functionName==='write'?'({consumerAborted:controller.signal.aborted})':'({leaseAborted:navigationLease.signal.aborted,combinedAborted:signal.aborted,navigationActive,scopeMatches:matchesScope()})',returnByValue:true});
          failures.push({frame:frame.functionName,reason:event.reason,value:value.result.value,error:value.exceptionDetails?.exception?.description});
        }
      }
    } finally { await debuggerSession.send('Debugger.resume'); }
  });
  try {
    await debuggerSession.send('Debugger.setPauseOnExceptions',{state:'all'});
    const response=page.waitForResponse(r=>r.url().includes('/operations/scenes.artifact'));
    await page.getByRole('button',{name:'导出工件',exact:true}).click();
    const exported=await (await response).json();
    await page.getByRole('alert').waitFor();
    return {exported,failures,alert:await page.getByRole('alert').textContent(),stylesheetCount:await page.locator('link[data-dbfox-dlc="dbfox.scene"]').count()};
  } finally {
    await debuggerSession.send('Debugger.setPauseOnExceptions',{state:'none'});
    await debuggerSession.detach();
  }
}
