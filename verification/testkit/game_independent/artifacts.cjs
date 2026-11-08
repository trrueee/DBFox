// Read-only fixed Artifacts and real DownloadItem actions; no injected engine result.
async (page) => {
  const ensure = (ok, message) => { if (!ok) throw new Error(message); };
  const poll = await page.waitForRequest(r => r.url().includes('/operations/playtest.next'));
  const headers = await poll.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = poll.url().split('/api/v1/')[0] + '/api/v1/';
  const reads = [];
  const requests = [];
  const observe = r => {
    if (r.url().includes('/api/v1/')) requests.push({ path: '/api/v1/' + r.url().split('/api/v1/')[1].split('?')[0], method: r.method() });
  };
  page.on('request', observe);
  const readArtifact = async (name, representation, button) => {
    const pending = page.waitForResponse(r => r.url().includes(`/representations/${representation}/read`));
    await page.getByRole('tab', { name, exact: true }).click();
    const response = await pending;
    const proof = await response.json();
    const artifactId = response.url().split('/artifacts/')[1].split('/')[0];
    ensure(proof.source_version === '4' && proof.consistency === 'durable_snapshot', 'Wrong fixed snapshot');
    const stream = await page.context().request.post(`${base}artifacts/${artifactId}/representations/${representation}/stream`, { headers, data: { operation: 'export', parameters: {} } });
    ensure(stream.ok(), 'Representation stream failed');
    const bytes = await stream.body(); await stream.dispose();
    await page.getByRole('button', { name: button, exact: true }).click();
    reads.push({ artifactId, representation, version: proof.source_version, hash: proof.source_fingerprint, bytesBase64: bytes.toString('base64') });
  };
  try {
    await readArtifact('Independent Fox Review · Playtest', 'dbfox.game.playtest.v1', '下载 Playtest 报告');
    await readArtifact('Independent Fox Review', 'dbfox.game.document.v1', '下载 Game 包');
    const fixed = page.locator('.game-artifact');
    await fixed.locator('canvas').waitFor();
    await fixed.getByRole('button', { name: '播放固定版本', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.game-artifact .game-help')].some(e => /tick [1-9]/.test(e.textContent)));
    await fixed.getByRole('button', { name: '暂停', exact: true }).click();
    const paused = await fixed.innerText(); await page.waitForTimeout(150);
    ensure(await fixed.innerText() === paused, 'Fixed preview pause failed');
    await fixed.getByRole('button', { name: '重置', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('.game-artifact .game-help')].some(e => /tick 0/.test(e.textContent)));
    const bounds = await fixed.locator('canvas').boundingBox();
    await page.screenshot({ path: 'output/playwright/game-independent-fixed-document.png' });
    const readsOnly = requests.filter(r => r.method !== 'GET' && !r.path.includes('/representations/') && !r.path.includes('/operations/playtest.next'));
    ensure(readsOnly.length === 0, 'Unexpected runtime request during immutable viewing');
    return { reads, previewPauseReset: true, bounds, requestCount: requests.length, nonReadRequests: readsOnly };
  } finally { page.off('request', observe); }
}
