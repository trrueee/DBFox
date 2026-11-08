async (page) => {
  const result = await page.locator('canvas').evaluateAll(cs => cs.map(c => {
    const gl = c.getContext('webgl2');
    return { width: c.width, height: c.height, box: c.getBoundingClientRect().toJSON(),
      webgl: !!gl, renderer: gl?.getParameter(gl.RENDERER), version: gl?.getParameter(gl.VERSION) };
  }));
  await page.screenshot({path: 'output/playwright/scene-initial.png'});
  return result;
}
