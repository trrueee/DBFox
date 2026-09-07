async(page)=>{
 const position=page.getByRole('spinbutton',{name:'播放位置 ms',exact:true});
 const object=page.locator('.dbfox-animation__preview-object');
 const seek=async value=>{await position.fill(String(value));await position.press('Tab');};
 await seek(0);const begin=await object.getAttribute('style');
 await seek(4000);const contact=await object.getAttribute('style');if(contact===begin)throw Error('Seek did not project position');
 await seek(7900);await page.getByRole('button',{name:'播放',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('[aria-label="播放位置 ms"]').value==='8000');
 await page.getByRole('button',{name:'播放',exact:true}).waitFor();
 const ended=await object.getAttribute('style');
 await page.getByRole('button',{name:'播放',exact:true}).click();
 await page.waitForFunction(()=>{const t=Number(document.querySelector('[aria-label="播放位置 ms"]').value);return t>100&&t<4000;});
 await page.getByRole('button',{name:'暂停',exact:true}).click();
 const replay=Number(await position.inputValue());if(replay>=4000)throw Error('Replay failed to start from beginning');
 await page.getByRole('button',{name:'起点',exact:true}).click();
 if(await position.inputValue()!=='0')throw Error('Start reset failed');
 return {begin,contact,ended,replay,finalTick:await position.inputValue()};
}
