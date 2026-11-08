async (page) => {
  await page.getByRole('button', {name:'关闭 Scene Studio', exact:true}).click();
  return page.evaluate(() => { const result = sceneControlsProbe.read(); sceneControlsProbe.restore(); return {closed:result.domCanvases === 0, restored:!globalThis.sceneControlsProbe}; });
}
