async(page)=>{
  const oldUrl=await page.locator('.dbfox-pixel__artifact-image').getAttribute('src');
  await page.evaluate(()=>{const original=HTMLAnchorElement.prototype.click;window.__pixelRedDownload={original,count:0};HTMLAnchorElement.prototype.click=function(...args){if(this.download?.endsWith('-sheet.png'))window.__pixelRedDownload.count++;return original.apply(this,args);};});
  const probe=()=>page.evaluate(async()=>{const {getRuntimeSession}=await import('/src/lib/api/client.ts');return {generation:getRuntimeSession().generation,styles:document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length,downloadClicks:window.__pixelRedDownload.count};});
  let release,arrived,first=true,status;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{arrived=resolve;});
  const pattern='**/representations/**';
  const handler=async route=>{if(!first||route.request().method()!=='POST')return route.continue();first=false;
    const response=await route.fetch();status=response.status();arrived();await held;
    try{await route.fulfill({response});}catch{/* The old stream was cancelled by deactivation. */}};
  await page.route(pattern,handler);
  try{
    const before=await probe();await page.getByRole('button',{name:'下载 Sprite Sheet',exact:true}).click();
    await Promise.race([entered,page.waitForTimeout(15000).then(()=>{throw new Error('No real representation response');})]);
    if(status!==200)throw new Error(`Representation failed before cancellation: ${status}`);
    await page.getByRole('button',{name:'扩展',exact:true}).click();
    await page.getByRole('button',{name:'停用',exact:true}).click();await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
    await page.getByText('未激活',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===0);
    const disabled=await probe();
    const oldRevoked=await page.evaluate(async url=>{try{await fetch(url);return false;}catch{return true;}},oldUrl);
    await page.getByRole('button',{name:'启用',exact:true}).click();await page.getByRole('button',{name:'立即重启',exact:true}).first().click();
    await page.getByText('当前已激活',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('link[data-dbfox-dlc="dbfox.pixel"]').length===1);
    const activated=await probe();release();await page.getByRole('button',{name:'返回工作区',exact:true}).click();
    await page.locator('.dbfox-pixel__artifact-image').waitFor();await page.waitForTimeout(400);
    const after=await probe(),newUrl=await page.locator('.dbfox-pixel__artifact-image').getAttribute('src');
    if(!oldRevoked||disabled.styles||after.styles!==1||after.downloadClicks||after.generation<=before.generation||oldUrl===newUrl)throw new Error(JSON.stringify({before,disabled,activated,after,oldRevoked,sameUrl:oldUrl===newUrl}));
    return {status,before,disabled,activated,after,oldRevoked,replacedPreviewUrl:oldUrl!==newUrl};
  }finally{release();await page.unroute(pattern,handler);await page.evaluate(()=>{HTMLAnchorElement.prototype.click=window.__pixelRedDownload.original;delete window.__pixelRedDownload;});}
}
