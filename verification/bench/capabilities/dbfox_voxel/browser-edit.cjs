async (page) => {
  if(await page.getByRole('button', {name:'工作区全屏',exact:true}).count()) await page.getByRole('button', {name:'工作区全屏',exact:true}).click();
  const studio=page.getByRole('region',{name:'Voxel Studio',exact:true});
  const viewport=page.getByLabel(/^体素三维视口/);
  const initial={heading:await studio.locator('header').innerText(),canvases:await studio.locator('canvas').count(),
    viewport:await viewport.boundingBox(),styles:await page.locator('link[data-dbfox-dlc="dbfox.voxel"]').count()};
  await viewport.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-initial.png'});
  const box=await viewport.boundingBox();
  await page.mouse.move(box.x+box.width*0.5,box.y+box.height*0.5);await page.mouse.down();
  await page.mouse.move(box.x+box.width*0.7,box.y+box.height*0.6,{steps:12});await page.mouse.up();
  await viewport.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-orbit.png'});
  const operations=[];
  await page.getByRole('button',{name:'Neon pink (2)',exact:true}).click();
  for(const axis of ['x','y','z']) {
    await page.getByRole('combobox',{name:'切片轴',exact:true}).selectOption(axis);
    await page.getByRole('spinbutton',{name:'切片位置',exact:true}).fill('2');
    const slice=page.getByRole('application',{name:/体素切片/});await slice.scrollIntoViewIfNeeded();
    const bounds=await slice.boundingBox();
    const response=page.waitForResponse(r=>r.url().includes('/operations/worlds.apply')&&r.request().method()==='POST');
    await page.mouse.move(bounds.x+bounds.width*8.5/32,bounds.y+bounds.height*(1-8.5/32));await page.mouse.down();
    await page.mouse.move(bounds.x+bounds.width*10.5/32,bounds.y+bounds.height*(1-10.5/32),{steps:5});await page.mouse.up();
    const result=await response;operations.push({axis,status:result.status(),request:result.request().postDataJSON(),response:await result.json()});
    await page.getByRole('button',{name:'应用到选区',exact:true}).waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('.voxel-inspector button:last-of-type')?.disabled);
    await page.getByRole('button',{name:'刷新',exact:true}).click();
  }
  await page.getByRole('checkbox',{name:'显示 Base',exact:true}).uncheck();
  await page.getByText('0 个表面方块',{exact:true}).waitFor();
  const hiddenHeading=await studio.locator('header').innerText();
  await page.getByRole('checkbox',{name:'显示 Base',exact:true}).check();
  const slice=page.getByRole('application',{name:/体素切片/});await slice.focus();
  await page.keyboard.press('ArrowRight');
  const keyboardResponse=page.waitForResponse(r=>r.url().includes('/operations/worlds.apply')&&r.request().method()==='POST');
  await page.keyboard.press('Space');
  const keyboard=await keyboardResponse;
  await page.getByRole('button',{name:'刷新',exact:true}).click();
  await viewport.scrollIntoViewIfNeeded();
  await page.screenshot({path:'verification/bench/capabilities/dbfox_voxel/evidence/electron-edited.png'});
  return {initial,operations,hiddenHeading,keyboard:{status:keyboard.status(),request:keyboard.request().postDataJSON(),response:await keyboard.json()},
    finalHeading:await studio.locator('header').innerText()};
}
