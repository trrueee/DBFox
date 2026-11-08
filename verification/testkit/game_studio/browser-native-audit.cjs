async (page) => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const request = await page.waitForRequest((value) => value.url().includes('/operations/playtest.next'));
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async (path, data, method = 'POST') => {
    const response = await page.context().request.fetch(base + path, { method, headers, ...(data === undefined ? {} : { data }) });
    const body = response.status() === 204 ? null : await response.json();
    if (!response.ok()) throw new Error(`${path}: ${JSON.stringify(body)}`);
    await response.dispose(); return body;
  };
  const project = (await api('projects', undefined, 'GET')).find((item) => item.name === 'Game Native Agent QA');
  const conversation = (await api('conversations', undefined, 'GET')).find((item) => item.project_id === project.id);
  const detail = await api(`conversations/${conversation.id}`, undefined, 'GET');
  const run = detail.runs.find((item) => item.status === 'completed');
  assert(run, 'Original native Agent Run must remain completed after upgrade');
  const artifacts = await api(`conversations/${conversation.id}/runs/${run.id}/artifacts`, undefined, 'GET');
  const proofs = [];
  for (const artifact of artifacts) {
    const representation = artifact.type === 'dbfox.game.playtest-report' ? 'dbfox.game.playtest.v1' : 'dbfox.game.document.v1';
    const page = await api(`artifacts/${artifact.id}/representations/${representation}/read`, { operation: 'page', parameters: { section: 'summary' } });
    assert(page.source_version === String(artifact.payload.version) && page.source_fingerprint === artifact.payload.content_hash && page.consistency === 'durable_snapshot', 'Immutable Artifact proof changed after upgrade');
    proofs.push({ artifactId: artifact.id, version: artifact.payload.version, contentHash: artifact.payload.content_hash, representation, report: page.payload.metadata.report });
  }
  const navigation = page.getByRole('navigation', { name: '主导航', exact: true });
  if (await page.getByRole('button', { name: '退出工作区全屏', exact: true }).count()) await page.getByRole('button', { name: '退出工作区全屏', exact: true }).click();
  if (await page.getByRole('button', { name: '关闭 Native Agent Fox Survival', exact: true }).count()) await page.getByRole('button', { name: '关闭 Native Agent Fox Survival', exact: true }).click();
  if (!await navigation.getByRole('button', { name: /^Native fox survival design and playtest/ }).isVisible()) await navigation.getByRole('button', { name: 'Game Native Agent QA', exact: true }).click();
  await navigation.getByRole('button', { name: /^Native fox survival design and playtest/ }).click();
  await page.locator('.game-artifact').first().waitFor();
  assert(await page.locator('.game-artifact').count() === artifacts.length, 'Every Game Artifact must mount, including nullable report_id documents');
  const exportView = page.locator('.game-artifact').filter({ has: page.getByRole('button', { name: '下载 Game 包', exact: true }) }).last();
  await exportView.getByRole('button', { name: '下载 Game 包', exact: true }).click();
  await exportView.getByRole('button', { name: '展开工件', exact: true }).click();
  const workspace = page.locator('.workspace-dock');
  const fixed = page.locator('.game-artifact').filter({ has: page.locator('.game-viewport') });
  await fixed.locator('canvas').waitFor();
  const canvas = await fixed.locator('canvas').boundingBox();
  const viewport = await fixed.locator('.game-viewport').boundingBox();
  assert(Math.abs(canvas.width - viewport.width) < 3 && Math.abs(canvas.height - viewport.height) < 3, 'Phaser canvas must fit the narrow Dock without !important');
  await page.screenshot({ path: '.tmp/game-phaser-review/native-artifact-narrow.png' });
  await page.getByRole('button', { name: '工作区全屏', exact: true }).click();
  await fixed.getByRole('button', { name: '播放固定版本', exact: true }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('.game-artifact .game-help')].some((item) => /tick [1-9]/.test(item.textContent)));
  await fixed.getByRole('button', { name: '暂停', exact: true }).click();
  await fixed.getByRole('button', { name: '重置', exact: true }).click();
  await page.screenshot({ path: '.tmp/game-phaser-review/native-artifact-wide.png' });
  return { runId: run.id, immutableProofs: proofs, mountedArtifacts: artifacts.length, narrowCanvas: canvas, narrowViewport: viewport, workspaceCount: await workspace.count(), styles: await page.locator('link[data-dbfox-dlc="dbfox.game"]').getAttribute('href') };
}
