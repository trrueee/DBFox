async (page) => {
  // Attached only to this suite's explicitly named Electron endpoint.
  await page.evaluate(()=>{void window.dbfoxDesktop.window.close();});
  return {requested:'graceful close of suite-owned Electron'};
}
