async (page) => {
  await page.reload();
  await page.getByRole('button',{name:'打开 Scene Studio',exact:true}).click();
  await page.getByRole('button',{name:'工作区全屏',exact:true}).click();
  await page.getByRole('combobox',{name:'打开场景',exact:true}).selectOption({label:'Interactive Scene'});
  await page.getByRole('treeitem',{name:'QA Cube',exact:true}).waitFor();
  return {stylesheetCount:await page.locator('link[data-dbfox-dlc="dbfox.scene"]').count(),canvasCount:await page.locator('canvas').count()};
}
