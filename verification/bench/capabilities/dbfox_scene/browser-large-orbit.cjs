async (page) => {
  await page.getByRole('button',{name:'聚焦 F',exact:true}).click();
  const metrics = page.evaluate(async()=>{
    const intervals=[]; const tasks=[];
    const observer=new PerformanceObserver(items=>tasks.push(...items.getEntries().map(e=>e.duration)));
    observer.observe({entryTypes:['longtask']});
    await new Promise(resolve=>{let previous;const end=performance.now()+3000;const step=t=>{if(previous!==undefined)intervals.push(t-previous);previous=t;if(t<end)requestAnimationFrame(step);else resolve();};requestAnimationFrame(step);});
    observer.disconnect();return {intervals,longTasks:tasks};
  });
  await page.mouse.move(660,450);
  await page.mouse.down();
  for(let i=0;i<45;i++) await page.mouse.move(660+i*3,450+i,{steps:2});
  await page.mouse.up();
  const result = await metrics;
  result.intervals.sort((a,b)=>a-b);
  await page.screenshot({path:'output/playwright/scene-10000-orbit.png'});
  return {samples:result.intervals.length,medianMs:result.intervals[Math.floor(result.intervals.length*.5)],p95Ms:result.intervals[Math.floor(result.intervals.length*.95)],maxMs:result.intervals.at(-1),longTasks:result.longTasks};
}
