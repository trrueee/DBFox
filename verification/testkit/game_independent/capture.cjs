// Read the independent native dataset through public operations. No state writes.
async (page) => {
  const poll = await page.waitForRequest(r => r.url().includes('/operations/playtest.next'));
  const headers = await poll.allHeaders();
  delete headers['content-length']; delete headers.host;
  const base = poll.url().split('/api/v1/')[0] + '/api/v1/';
  const response = await page.context().request.get(base + 'projects', { headers });
  if (!response.ok()) throw new Error('Public project listing failed');
  const project = (await response.json()).find(p => p.name === 'Default Workspace');
  await response.dispose();
  if (!project) throw new Error('Independent default project missing');
  const read = async (operation, data) => {
    const response = await page.context().request.post(`${base}dlcs/dbfox.game/operations/${operation}?project_id=${project.id}`, { headers, data });
    const raw = await response.text();
    if (!response.ok()) throw new Error(`Public ${operation} read failed: ${response.status()}`);
    await response.dispose();
    return raw;
  };
  const game = JSON.parse(await read('games.list', {})).items.find(g => g.title === 'Independent Fox Review');
  if (!game) throw new Error('Independent UI-created game missing');
  const snapshots = [];
  for (let version = 2; version <= game.version; version++) {
   const pages = [];
   for (const section of ['summary', 'scenes', 'entities', 'behaviors', 'rules', 'variables', 'assets']) {
    const raw = await read('games.get', { game_id: game.id, version, section, offset: 0, limit: 50 });
    if (JSON.parse(raw).has_more) throw new Error('Independent dataset unexpectedly exceeds one page');
    // ASCII transport preserves Chinese and float spelling across Windows shell redirection.
    pages.push({ section, raw: raw.replace(/[^\x00-\x7F]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')) });
   }
   snapshots.push({ version, pages });
  }
  return { projectId: project.id, game, snapshots, capturedAt: new Date().toISOString(),
    csp: 'verbatim production Host policy in task-owned Electron',
    boundary: 'public read operations only, raw JSON preserved for canonical audit' };
}
