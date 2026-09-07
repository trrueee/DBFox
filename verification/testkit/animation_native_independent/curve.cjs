async(page)=>{
await page.getByRole('group',{name:'缓动控制点',exact:true}).getByRole('button',{name:'保存',exact:true}).click();
await page.getByRole('status').filter({hasText:'已保存 v10'}).waitFor();
await page.getByRole('spinbutton',{name:'控制点 1 时间',exact:true}).waitFor();
await page.screenshot({path:'output/playwright/animation-independent/narrow-curve.png'});
await page.getByRole('button',{name:'撤销',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('[aria-label="控制点 1 时间"]')?.value==='0.25');
await page.getByRole('button',{name:'导出固定版本',exact:true}).click();
await page.getByRole('button',{name:'下载 Animation JSON',exact:true}).click();
return await page.locator('article').innerText();
}