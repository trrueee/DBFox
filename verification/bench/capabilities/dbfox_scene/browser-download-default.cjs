async (page) => {
  const cdp=await page.context().browser().newBrowserCDPSession();
  try {
    await cdp.send('Browser.setDownloadBehavior',{behavior:'default',eventsEnabled:true});
    const response=page.waitForResponse(r=>r.url().includes('/representations/') && r.request().method()==='POST');
    await page.getByRole('button',{name:'下载 GLB',exact:true}).click();
    const streamed=await response;
    await page.waitForTimeout(1000);
    return {status:streamed.status(),mode:'Electron default download behavior; inspect passive Main event record'};
  } finally { await cdp.detach(); }
}
