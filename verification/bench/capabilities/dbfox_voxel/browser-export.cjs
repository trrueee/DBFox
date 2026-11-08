async (page) => {
  const studio=page.getByRole('region',{name:'Voxel Studio',exact:true});
  const writes=[];const listener=r=>{if(r.url().includes('/operations/worlds.'))writes.push({operation:r.url().split('/operations/')[1],status:r.status()});};
  page.on('response',listener);
  try {
    const beforeSelection=await studio.locator('.voxel-bounds input').evaluateAll(es=>es.map(e=>e.value));
    const viewport=page.getByLabel(/^体素三维视口/);
    await viewport.scrollIntoViewIfNeeded();await viewport.click({position:{x:650,y:180}});
    const afterSelection=await studio.locator('.voxel-bounds input').evaluateAll(es=>es.map(e=>e.value));
    for(const [name,value] of [['起点 X','4'],['起点 Y','4'],['起点 Z','4'],['终点 X','7'],['终点 Y','7'],['终点 Z','7']])
      await page.getByRole('spinbutton',{name,exact:true}).fill(value);
    await page.getByRole('combobox',{name:'选区操作',exact:true}).selectOption('box');
    const bulk=page.waitForResponse(r=>r.url().includes('/operations/worlds.apply')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'应用到选区',exact:true}).click();const bulkResult=await(await bulk).json();
    const undo=page.waitForResponse(r=>r.url().includes('/operations/worlds.undo')&&r.request().method()==='POST');
    await page.getByRole('button',{name:/^撤销到 v/}).click();const undoResult=await(await undo).json();
    const exported=page.waitForResponse(r=>r.url().includes('/operations/worlds.snapshot')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'保存快照',exact:true}).click();const response=await exported;const snapshot=await response.json();
    await page.getByText(/不可变快照 · v/).first().waitFor();
    await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-artifact.png'});
    return {picking:{beforeSelection,afterSelection},bulk:bulkResult,undo:undoResult,snapshot:{status:response.status(),...snapshot},
      tabs:await page.getByRole('tab').allTextContents(),artifactText:await page.locator('.voxel-artifact, .voxel-snapshot').allTextContents(),
      downloadButtons:await page.getByRole('button',{name:/下载|导出/}).allTextContents(),writes};
  } finally {page.off('response',listener);}
}
