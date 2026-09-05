async(page)=>{
  if(await page.getByRole('button',{name:'关闭 Pixel Studio',exact:true}).count())await page.getByRole('button',{name:'关闭 Pixel Studio',exact:true}).click();
  if(!await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).count())await page.getByRole('button',{name:'Pixel Red Team',exact:true}).click();
  await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).click();
  const opened=page.waitForResponse(r=>r.url().includes('/operations/documents.get')&&r.status()===200);
  await page.getByRole('button',{name:'打开作品',exact:true}).click();
  const initial=await(await opened).json();
  const canvas=page.getByRole('application',{name:'像素画布 16 × 16',exact:true});await canvas.waitFor();
  const invoke=(name,payload)=>page.evaluate(async({name,payload,project})=>{
    const {fetchEnginePath}=await import('/src/lib/api/client.ts');
    const response=await fetchEnginePath(`/dlcs/dbfox.pixel/operations/${name}?project_id=${project}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    return {status:response.status,body:await response.json()};
  },{name,payload,project:initial.summary.project_id});
  const head=()=>invoke('documents.head',{document_id:initial.summary.document_id});
  const writes=[],heads=[];
  const onRequest=request=>{if(request.method()==='POST'&&request.url().includes('/operations/documents.apply'))writes.push(request.postDataJSON());if(request.method()==='POST'&&request.url().includes('/operations/documents.head'))heads.push(request.url());};
  const xy=async(x,y)=>{const b=await canvas.boundingBox();if(!b)throw new Error('No live canvas');return {x:b.x+(x+0.5)*b.width/16,y:b.y+(y+0.5)*b.height/16};};
  const begin=async(x,y)=>{const p=await xy(x,y);await page.mouse.move(p.x,p.y);await page.mouse.down();};
  const move=async(x,y)=>{const p=await xy(x,y);await page.mouse.move(p.x,p.y);};
  page.on('request',onRequest);
  try{
    await page.getByRole('button',{name:'画笔 B',exact:true}).click();
    await begin(0,0);
    for(let i=1;i<130;i++)await move(i%16,Math.floor(i/16));
    await page.mouse.up();await page.getByRole('alert').filter({hasText:'本次笔迹超过 128 段，已全部取消。'}).waitFor();
    const oversize={head:await head(),writes:writes.length};
    if(oversize.head.body.revision!==initial.summary.revision||writes.length)throw new Error('Oversize gesture partially committed');
    await begin(2,2);await move(5,2);await canvas.press('Escape');await page.mouse.up();
    const escape={head:await head(),writes:writes.length};
    if(escape.head.body.revision!==initial.summary.revision||writes.length)throw new Error('Escape gesture committed');
    await begin(3,3);await move(7,3);
    // Space activates the close button without releasing the captured mouse on
    // the canvas first. A normal mouse click would end the gesture before close.
    const close=page.getByRole('button',{name:'关闭 Pixel Studio',exact:true});await close.focus();await close.press('Space');
    await canvas.waitFor({state:'detached'});await page.mouse.up();
    const headRequests=heads.length;await page.waitForTimeout(1300);
    const closed={canvas:await canvas.count(),writes:writes.length,latePolls:heads.length-headRequests,head:await head()};
    if(closed.canvas||closed.writes||closed.latePolls||closed.head.body.revision!==initial.summary.revision)throw new Error('Closed canvas retained gesture or poll');
    await page.getByRole('button',{name:'打开 Pixel Studio',exact:true}).click();await page.getByRole('button',{name:'打开作品',exact:true}).click();await canvas.waitFor();
    const reopened={tabs:await page.getByRole('tab',{name:'Pixel Studio',exact:true}).count(),styles:await page.locator('link[data-dbfox-dlc="dbfox.pixel"]').count()};
    if(reopened.tabs!==1||reopened.styles!==1)throw new Error('Reopen did not produce one active owner');
    await begin(4,4);await move(8,4);
    const mutationId=await page.evaluate(()=>crypto.randomUUID());
    const human=await invoke('documents.apply',{document_id:initial.summary.document_id,expected_version:initial.summary.revision,mutation_id:mutationId,operations:[{kind:'rename',title:`Adversarial Human During Drag ${initial.summary.revision+1}`}]});
    if(human.status!==200)throw new Error('Human edit failed');
    await page.waitForTimeout(1200);
    const during=await page.locator('.dbfox-pixel__heading small').innerText();
    const rejected=page.waitForResponse(r=>r.url().includes('/operations/documents.apply')&&r.status()===409);
    await page.mouse.up();const failure=await(await rejected).json();
    await page.waitForFunction(v=>document.querySelector('.dbfox-pixel__heading small')?.textContent?.endsWith(`r${v}`),human.body.revision);
    await page.waitForTimeout(250);
    const after=await head();
    // This Electron CDP connection reports null postData for both fetch POSTs.
    // The real 409, frozen displayed revision and durable head prove the fence;
    // count network requests separately rather than inventing missing bodies.
    if(after.body.revision!==human.body.revision||writes.length!==2||!during.endsWith(`r${initial.summary.revision}`))throw new Error(JSON.stringify({message:'Stale gesture replayed or overwrote human state',after,human,writes,during}));
    await page.screenshot({path:'output/playwright/pixel-redteam-gestures.png'});
    return {initial:initial.summary,oversize,escape,closed,reopened,human,during,failure,after,writes};
  }finally{if(await canvas.count())await canvas.press('Escape');await page.mouse.up();page.off('request',onRequest);}
}
