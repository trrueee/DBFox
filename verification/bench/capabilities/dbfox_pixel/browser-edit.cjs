async (page) => {
  const canvas=page.getByRole('application',{name:'像素画布 16 × 16',exact:true});
  const evidence=[];
  const waitRevision=async revision=>page.waitForFunction(v=>document.querySelector('.dbfox-pixel__heading small')?.textContent?.endsWith(`r${v}`),revision);
  const gesture=async(from,to)=>{
    const box=await canvas.boundingBox();
    if(!box) throw new Error('Canvas not visible');
    const xy=p=>({x:box.x+(p[0]+0.5)*box.width/16,y:box.y+(p[1]+0.5)*box.height/16});
    const a=xy(from),b=xy(to);
    await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:4});await page.mouse.up();
  };
  const write=async(name,act)=>{
    const pending=page.waitForResponse(r=>r.url().includes('/operations/documents.apply')&&r.request().method()==='POST');
    await act();const response=await pending;const body=await response.json();
    if(response.status()!==200 || !Number.isInteger(body.revision)) throw new Error(JSON.stringify(body));
    await waitRevision(body.revision);
    evidence.push({name,status:response.status(),request:response.request().postDataJSON(),response:body});
  };
  await page.getByRole('button',{name:'颜色 1 Ink',exact:true}).click();
  await page.getByRole('button',{name:'画笔 B',exact:true}).click();
  await write('brush',()=>gesture([2,2],[5,2]));
  await page.getByRole('button',{name:'橡皮 E',exact:true}).click();
  await write('erase',()=>gesture([3,2],[3,2]));
  await page.getByRole('button',{name:'颜色 2 White',exact:true}).click();
  await page.getByRole('button',{name:'矩形 R',exact:true}).click();
  await write('rectangle',()=>gesture([8,8],[10,9]));
  await page.getByRole('button',{name:'选区 V',exact:true}).click();
  await gesture([8,8],[10,9]);
  await page.getByRole('button',{name:'应用区域变换',exact:true}).waitFor();
  const selection={x:await page.getByRole('spinbutton',{name:'选区 X',exact:true}).inputValue(),y:await page.getByRole('spinbutton',{name:'选区 Y',exact:true}).inputValue(),width:await page.getByRole('spinbutton',{name:'选区宽度',exact:true}).inputValue(),height:await page.getByRole('spinbutton',{name:'选区高度',exact:true}).inputValue()};
  await page.getByRole('spinbutton',{name:'目标 X',exact:true}).fill('0');
  await page.getByRole('spinbutton',{name:'目标 Y',exact:true}).fill('10');
  await page.getByRole('combobox',{name:'变换模式',exact:true}).selectOption('copy');
  await write('region-copy',()=>page.getByRole('button',{name:'应用区域变换',exact:true}).click());
  await write('lock',()=>page.getByRole('button',{name:'锁定图层 Layer 1',exact:true}).click());
  await page.getByRole('button',{name:'画笔 B',exact:true}).click();
  if(await canvas.getAttribute('aria-disabled')!=='true') throw new Error('Locked canvas still accepts drawing');
  await write('unlock',()=>page.getByRole('button',{name:'解锁图层 Layer 1',exact:true}).click());
  await page.getByRole('textbox',{name:'颜色名称',exact:true}).fill('Snow');
  await write('palette-name',()=>page.getByRole('button',{name:'保存颜色',exact:true}).click());
  await write('duplicate-frame',()=>page.getByRole('button',{name:'复制当前帧',exact:true}).click());
  await page.getByRole('button',{name:'选择第 2 帧',exact:true}).click();
  await page.getByRole('spinbutton',{name:'帧时长 ms',exact:true}).fill('180');
  await write('duration',()=>page.getByRole('button',{name:'设置帧时长',exact:true}).click());
  await canvas.focus();await canvas.press('ArrowRight');
  await write('keyboard-pixel',()=>canvas.press('Enter'));
  await page.getByRole('button',{name:'播放动画',exact:true}).click();
  await page.getByRole('button',{name:'暂停播放',exact:true}).waitFor();
  const previewLabels=new Set();
  for(let i=0;i<6;i++){previewLabels.add(await page.locator('canvas[aria-label^="动画预览"]').getAttribute('aria-label'));await page.waitForTimeout(80);}
  await page.getByRole('button',{name:'暂停播放',exact:true}).click();
  if(previewLabels.size<2) throw new Error('Animation never advanced frames');
  await page.screenshot({path:'output/playwright/pixel-real-edited.png'});
  return {selection,previewLabels:[...previewLabels],writes:evidence,canvasCount:await page.locator('canvas').count(),styles:await page.locator('link[data-dbfox-dlc="dbfox.pixel"]').count()};
}
