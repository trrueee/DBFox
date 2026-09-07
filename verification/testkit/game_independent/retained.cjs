// Read already-observed v4 Artifact identities after the current game reaches v5.
async (page) => {
  const poll = await page.waitForRequest(r => r.url().includes('/operations/playtest.next'));
  const headers = await poll.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = poll.url().split('/api/v1/')[0] + '/api/v1/';
  const targets = [
    ['artifact_6ff8daf1a91a401d91448497f973d329', 'dbfox.game.playtest.v1'],
    ['artifact_19b55753006b433db80f97ea99dca2ad', 'dbfox.game.document.v1'],
  ];
  const reads = [];
  for (const [artifactId, representation] of targets) {
    const prefix = `${base}artifacts/${artifactId}/representations/${representation}`;
    const pageResponse = await page.context().request.post(prefix + '/read', { headers, data: { operation: 'page', parameters: { section: 'summary' } } });
    if (!pageResponse.ok()) throw new Error('Retained v4 page unavailable');
    const proof = await pageResponse.json(); await pageResponse.dispose();
    const stream = await page.context().request.post(prefix + '/stream', { headers, data: { operation: 'export', parameters: {} } });
    if (!stream.ok()) throw new Error('Retained v4 export unavailable');
    const bytesBase64 = (await stream.body()).toString('base64'); await stream.dispose();
    reads.push({ artifactId, representation, version: proof.source_version, hash: proof.source_fingerprint, bytesBase64 });
  }
  return reads;
}
