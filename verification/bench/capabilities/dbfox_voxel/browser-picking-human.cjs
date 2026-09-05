async (page) => {
  if(await page.getByRole('button',{name:'退出工作区全屏',exact:true}).count())await page.getByRole('button',{name:'退出工作区全屏',exact:true}).click();
  await page.getByRole('treeitem',{name:'Interactive Voxel',exact:true}).click();
  await page.getByRole('button',{name:'工作区全屏',exact:true}).click();
  const heading=await page.locator('.voxel-header').innerText();
  const viewport=page.getByLabel(/^体素三维视口/);await viewport.scrollIntoViewIfNeeded();
  const values=()=>page.locator('.voxel-bounds input').evaluateAll(es=>es.map(e=>Number(e.value)));
  const before=await values();const rect=await viewport.boundingBox();let hit=null;
  const writes=[];const listener=r=>{if(/operations\/worlds\.(apply|configure)/.test(r.url()))writes.push(r.url());};page.on('request',listener);
  try {
    for(const y of [.5,.6,.7,.8]) {
      for(const x of [.5,.45,.55,.4,.6]) {
        await viewport.click({position:{x:rect.width*x,y:rect.height*y}});
        const selected=await values();
        if(JSON.stringify(selected)!==JSON.stringify(before)){hit={point:[x,y],selected};break;}
      }
      if(hit)break;
    }
    if(!hit)throw new Error('No rendered voxel could be selected by clicking the visible world');
    const slice={axis:await page.getByRole('combobox',{name:'切片轴',exact:true}).inputValue(),position:await page.getByRole('spinbutton',{name:'切片位置',exact:true}).inputValue()};
    const pickingWrites=writes.length;
    await page.getByRole('button',{name:'绘制矩形',exact:true}).click();
    await page.getByRole('button',{name:'Gold (4)',exact:true}).click();
    await page.getByRole('combobox',{name:'切片轴',exact:true}).selectOption('y');
    await page.getByRole('spinbutton',{name:'切片位置',exact:true}).fill('30');
    const canvas=page.getByRole('application',{name:/体素切片/});await canvas.focus();
    const response=page.waitForResponse(r=>r.url().includes('/operations/worlds.apply')&&r.request().method()==='POST');
    await page.keyboard.press('Space');const human=await(await response).json();
    return {heading,picking:{before,hit,slice,writes:pickingWrites},human};
  }finally{page.off('request',listener);}
}
