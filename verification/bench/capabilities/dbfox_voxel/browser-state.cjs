async (page) => ({heading:await page.locator('.voxel-header').innerText(),axis:await page.getByRole('combobox',{name:'切片轴',exact:true}).inputValue(),
  alerts:await page.getByRole('alert').allTextContents(),bounds:await page.getByRole('application',{name:/体素切片/}).boundingBox(),
  viewport:await page.evaluate(()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})),text:await page.locator('.voxel-caption').allTextContents(),version:await page.locator('.voxel-version').innerText()})
