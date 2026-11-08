async(page)=>{
  const read=()=>page.evaluate(async()=>{const {getRuntimeSession}=await import('/src/lib/api/client.ts');return {generation:getRuntimeSession().generation,styles:document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length,canvases:document.querySelectorAll('.dbfox-pixel canvas').length,state:document.querySelector('[aria-label="DLC 期望状态与运行状态"]')?.textContent};});
  if(await page.getByRole('button',{name:'停用',exact:true}).count()){
    await page.getByRole('button',{name:'停用',exact:true}).click();
    await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
  }
  await page.getByText('未激活',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===0);
  const disabled=await read();if(disabled.styles||disabled.canvases)throw new Error('Inactive Pixel retained frontend resources');
  await page.getByRole('button',{name:'启用',exact:true}).click();
  await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
  await page.getByText('当前已激活',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===1);
  const active=await read();if(active.styles!==1||active.generation<=disabled.generation)throw new Error('Reactivation failed');
  await page.getByRole('button',{name:'返回工作区',exact:true}).click();
  await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).click();
  await page.getByRole('button',{name:'打开作品',exact:true}).nth(2).click();
  await page.getByRole('application',{name:'像素画布 16 × 16',exact:true}).waitFor();
  const heading=await page.locator('.dbfox-pixel__heading').innerText();
  if(!heading.includes('200 帧')||!heading.endsWith('r11'))throw new Error(`Durable revision changed: ${heading}`);
  return {disabled,active,heading};
}
