async (page) => {
  await page.locator('.dbfox-pixel__heading small').waitFor();
  const canvas=page.getByRole('application',{name:'像素画布 16 × 16',exact:true}),writes=[];
  const agentPixel=await canvas.evaluate(c=>{const x=Math.floor(c.width/32),y=Math.floor(c.height*15.5/16);return [...c.getContext('2d').getImageData(x,y,1,1).data];});
  if(JSON.stringify(agentPixel)!==JSON.stringify([24,24,37,255]))throw new Error(`Agent pixel not painted: ${agentPixel}`);
  const write=async(name,action)=>{const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/operations/documents.apply'));await action();const r=await pending,b=await r.json();if(r.status()!==200)throw new Error(JSON.stringify(b));await page.waitForFunction(v=>document.querySelector('.dbfox-pixel__heading small')?.textContent?.endsWith(`r${v}`),b.revision);writes.push({name,result:b});};
  await write('hide-layer',()=>page.getByRole('button',{name:'隐藏图层 Layer 1',exact:true}).click());
  await write('show-layer',()=>page.getByRole('button',{name:'显示图层 Layer 1',exact:true}).click());
  await page.getByText('添加图层',{exact:true}).click();await page.getByRole('textbox',{name:'新图层名称',exact:true}).fill('Browser Overlay');
  await write('create-layer',()=>page.getByRole('button',{name:'创建图层',exact:true}).click());
  await page.getByRole('button',{name:'Browser Overlay',exact:true}).click();
  await page.getByRole('button',{name:'填充 F',exact:true}).click();
  await write('fill-layer',()=>canvas.click({position:{x:20,y:20}}));
  await write('layer-down',()=>page.getByRole('button',{name:'下移图层',exact:true}).click());
  await write('delete-overlay',()=>page.getByRole('button',{name:'删除当前图层',exact:true}).click());
  const select=async()=>{await page.getByRole('spinbutton',{name:'选区 X',exact:true}).fill('1');await page.getByRole('spinbutton',{name:'选区 Y',exact:true}).fill('1');await page.getByRole('spinbutton',{name:'选区宽度',exact:true}).fill('6');await page.getByRole('spinbutton',{name:'选区高度',exact:true}).fill('4');await page.getByRole('button',{name:'设置选区',exact:true}).click();};
  await select();
  await write('region-mirror',()=>page.getByRole('button',{name:'水平镜像',exact:true}).click());
  await select();
  await write('region-rotate',()=>page.getByRole('button',{name:'顺时针旋转',exact:true}).click());
  await select();
  await page.getByRole('spinbutton',{name:'目标 X',exact:true}).fill('6');await page.getByRole('spinbutton',{name:'目标 Y',exact:true}).fill('10');
  await write('region-move',()=>page.getByRole('button',{name:'应用区域变换',exact:true}).click());
  await page.getByText('动画标签 (0/16)',{exact:true}).click();await page.getByRole('checkbox',{name:'帧 2',exact:true}).check();
  await write('tag-create',()=>page.getByRole('button',{name:'创建动画标签',exact:true}).click());
  await page.getByRole('combobox',{name:'播放动画标签',exact:true}).selectOption({label:'Idle'});
  await page.getByRole('button',{name:'播放动画',exact:true}).click();await page.waitForTimeout(350);await page.getByRole('button',{name:'暂停播放',exact:true}).click();
  await write('frame-reorder',()=>page.getByRole('button',{name:'后移帧',exact:true}).click());
  await write('new-frame',()=>page.getByRole('button',{name:'新建帧',exact:true}).click());
  await page.getByRole('button',{name:'选择第 2 帧',exact:true}).click();
  // New blank frame sits after the previous current frame, which moved to position two.
  await page.getByRole('button',{name:'选择第 3 帧',exact:true}).click();
  await write('delete-frame',()=>page.getByRole('button',{name:'删除当前帧',exact:true}).click());
  await page.screenshot({path:'output/playwright/pixel-more-edited.png'});
  return {agentPixel,writes,finalHeading:await page.locator('.dbfox-pixel__heading').innerText()};
}
