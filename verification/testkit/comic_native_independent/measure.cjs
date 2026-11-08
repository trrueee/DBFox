async (page) => {
  const result = await page.evaluate(() => {
    const metrics = selector => { const el=document.querySelector(selector); if(!el)return null;const r=el.getBoundingClientRect();return {width:r.width,x:r.x,client:el.clientWidth,scroll:el.scrollWidth}; };
    return {viewport:innerWidth,document:document.documentElement.scrollWidth,studio:metrics('.comic-studio'),dock:metrics('.workspace-dock'),version:document.querySelector('.comic-version')?.textContent};
  });
  if(result.studio && (result.studio.width<320 || result.studio.scroll>result.studio.client+1)) throw Error(JSON.stringify(result));
  if(result.document>result.viewport) throw Error('Document overflow');
  return result;
}
