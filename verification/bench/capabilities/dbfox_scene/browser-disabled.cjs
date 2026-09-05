async (page) => {
  await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.scene"]').length===0,{timeout:20000});
  return {stylesheetCount:await page.locator('link[data-dbfox-dlc="dbfox.scene"]').count(),canvasCount:await page.locator('canvas').count(),sceneWorkbenchCount:await page.getByRole('region',{name:'Scene Studio 工作台',exact:true}).count()};
}
