async (page) => {
  const root=page.getByRole('treeitem',{name:'Large Root',exact:true});
  const start=Date.now();
  if(await root.getAttribute('aria-expanded')!=='true') await page.getByRole('button',{name:'Large Root',exact:true}).click();
  await page.getByRole('treeitem',{name:'Node 1',exact:true}).waitFor();
  const expandedMs=Date.now()-start;
  const expanded=await page.locator('[role="treeitem"]').count();
  await page.locator('.dbfox-tree').evaluate(el=>{el.scrollTop=el.scrollHeight;});
  await page.getByRole('treeitem',{name:'Node 9999',exact:true}).waitFor();
  const lastNode=await page.getByRole('treeitem',{name:'Node 9999',exact:true}).getAttribute('aria-setsize');
  await page.screenshot({path:'output/playwright/scene-10000-last-node.png'});
  await page.locator('.dbfox-tree').evaluate(el=>{el.scrollTop=0;});
  const collapseStart=Date.now();
  await page.getByRole('button',{name:'Large Root',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('[role="treeitem"]').length===1);
  return {expanded,expandedMs,lastNodeSetSize:lastNode,collapsed:await page.locator('[role="treeitem"]').count(),collapsedMs:Date.now()-collapseStart};
}
