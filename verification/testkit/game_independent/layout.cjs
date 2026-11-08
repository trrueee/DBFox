// Independent geometry observations from actual Electron window sizes.
async (page) => {
  const result = await page.evaluate(() => {
    const element = selector => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const bounds = node.getBoundingClientRect();
      return { width: bounds.width, height: bounds.height, clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth, inert: !!node.closest('[inert]') };
    };
    return { viewport: { width: innerWidth, height: innerHeight },
      documentWidth: document.documentElement.scrollWidth,
      stage: element('.app-v3-stage'), conversation: element('.app-conversation-panel'),
      dock: element('.app-dock-panel'), studio: element('.game-studio'),
      compact: document.querySelector('.app-v3-stage')?.dataset.compact === 'true',
      draft: [...document.querySelectorAll('input')].find(e => e.value === 'Independent layout draft')?.value ?? null,
      selectedGame: document.querySelector('select[aria-label="选择游戏"]')?.value ?? null,
      separator: !!document.querySelector('[aria-label="调整工作区宽度"]') };
  });
  if (result.documentWidth > result.viewport.width + 1) throw new Error('Document horizontal overflow');
  if (result.studio && result.studio.scrollWidth > result.studio.clientWidth + 1) throw new Error('Game content horizontal overflow');
  if (result.compact && result.studio && result.dock.width > 44.5) {
    if (Math.abs(result.dock.width - result.stage.width) > 1 || result.conversation.width > 1 || !result.conversation.inert) throw new Error('Compact visible and focus state disagree: ' + JSON.stringify(result));
  }
  return result;
}
