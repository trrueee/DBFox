async page => {
  const result = await page.evaluate(() => {
    const box = selector => {const e=document.querySelector(selector); return e ? {width:e.getBoundingClientRect().width,client:e.clientWidth,scroll:e.scrollWidth}:null;};
    return {innerWidth,innerHeight,compact:document.querySelector('.app-v3-stage')?.dataset.compact === 'true',stage:box('.app-v3-stage'),conversation:box('.app-conversation-panel'),dock:box('.app-dock-panel'),studio:box('.game-studio'),draft:document.querySelector('input[aria-label="游戏名称"]')?.value ?? [...document.querySelectorAll('input')].find(e=>e.value==='Unsaved layout draft')?.value,hasSeparator:!!document.querySelector('[aria-label="调整工作区宽度"]'),documentWidth:document.documentElement.scrollWidth};
  });
  if (result.documentWidth > result.innerWidth + 1) throw new Error('Host horizontal overflow');
  if (result.compact && result.dock.width > 44 && (Math.abs(result.dock.width-result.stage.width)>1 || result.conversation.width>1)) throw new Error('Compact Dock does not own stage');
  if (!result.compact && result.dock.width>44 && result.dock.width<319) throw new Error('Expanded Dock below minimum');
  return result;
}
