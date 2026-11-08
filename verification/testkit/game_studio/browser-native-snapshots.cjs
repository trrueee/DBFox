async (page) => {
  const request = await page.waitForRequest((value) => value.url().includes('/operations/playtest.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const projects = await (await page.context().request.get(base + 'projects', { headers })).json();
  const project = projects.find((item) => item.name === 'Game Native Agent QA');
  const operation = async (name, data) => {
    const response = await page.context().request.post(`${base}dlcs/dbfox.game/operations/${name}?project_id=${project.id}`, { headers, data });
    const raw = await response.text(); if (!response.ok()) throw new Error(raw); await response.dispose(); return raw;
  };
  const game = JSON.parse(await operation('games.list', {})).items.find((item) => item.title === 'Native Agent Fox Survival');
  const pages = [];
  for (const version of [3, 4, 5]) {
    for (const section of ['summary', 'scenes', 'entities', 'behaviors', 'rules', 'variables', 'assets']) {
      const raw = await operation('games.get', { game_id: game.id, version, section, offset: 0, limit: 50 });
      if (JSON.parse(raw).has_more) throw new Error('The acceptance dataset unexpectedly exceeds one bounded page');
      pages.push({ version, section, raw });
    }
  }
  return { projectId: project.id, gameId: game.id, pages, note: 'Raw public JSON preserves canonical number spelling for the Python audit' };
}
