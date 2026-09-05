async(page)=>{
  await page.getByRole('button',{name:'编辑当前作品',exact:true}).click();
  await page.getByRole('combobox',{name:'跳转帧页',exact:true}).selectOption('6');
  await page.getByRole('button',{name:'选择第 200 帧',exact:true}).click();
  const before=await page.locator('.dbfox-pixel__heading').innerText();
  await page.getByRole('button',{name:'画笔 B',exact:true}).click();
  const response=page.waitForResponse(r=>r.url().includes('/operations/documents.apply'));
  const canvas=page.getByRole('application',{name:'像素画布 16 × 16',exact:true}),box=await canvas.boundingBox();
  await canvas.click({position:{x:box.width*1.5/16,y:box.height*1.5/16}});
  const wire=await response,result=await wire.json();
  if(wire.status()!==200||result.changed_pixel_count!==1||result.changed_frame_ids[0]!=='scale_199')throw new Error(JSON.stringify(result));
  await page.waitForFunction(v=>document.querySelector('.dbfox-pixel__heading small')?.textContent.endsWith(`r${v}`),result.revision);
  return {before,result};
}
