async (page) => {
  const response = await page.context().request.get(page.url());
  const policy = response.headers()['content-security-policy'];
  await response.dispose();
  if (!policy || policy.includes('unsafe-eval') || !policy.includes("script-src 'self' dlc-asset:")) throw new Error('Production policy is absent or weakened');
  const probe = await page.evaluate(async () => {
    const violations = [];
    const listener = event => violations.push({ directive: event.effectiveDirective, blockedURI: event.blockedURI });
    document.addEventListener('securitypolicyviolation', listener);
    globalThis.__shaderInlineProbe = false;
    const script = document.createElement('script');
    script.textContent = 'globalThis.__shaderInlineProbe = true;';
    document.head.append(script);
    await new Promise(resolve => setTimeout(resolve, 100));
    script.remove(); document.removeEventListener('securitypolicyviolation', listener);
    const ran = globalThis.__shaderInlineProbe; delete globalThis.__shaderInlineProbe;
    return { ran, violations, visibility: document.visibilityState };
  });
  if (probe.ran || !probe.violations.some(item => item.directive === 'script-src-elem' && item.blockedURI === 'inline')) throw new Error('Actual Electron document did not enforce CSP');
  return { boundary: 'production dist served under verbatim imported Host policy, real Electron enforcement', policy, probe,
    loadedScripts: await page.locator('script[src]').evaluateAll(items => items.map(item => item.src)),
    styles: await page.locator('link[href*="dlc-asset"]').evaluateAll(items => items.map(item => item.href)) };
}
