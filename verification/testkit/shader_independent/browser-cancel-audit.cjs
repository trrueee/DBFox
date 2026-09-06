async (page) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const observed = page.waitForRequest(request => request.url().includes('/api/v1/projects'));
  await page.reload(); const request = await observed;
  const headers = await request.allHeaders(); delete headers['content-length']; delete headers.host;
  const base = request.url().split('/api/v1/')[0] + '/api/v1/';
  const api = async path => { const response = await page.context().request.get(base + path, { headers }); const result = await response.json(); if (!response.ok()) throw new Error(path); await response.dispose(); return result; };
  const sessions = await api('conversations'); const session = sessions.find(item => item.title === 'Independent late compute cancellation');
  const final = await api(`conversations/${session.id}`); const artifacts = await api(`conversations/${session.id}/runs/${final.runs[0].id}/artifacts`);
  return { boundary: 'Read-only audit of original cancellation Run after browser route teardown error; no admission replay', final, artifacts };
}
