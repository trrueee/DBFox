async (page) => {
  await page.reload();
  await page.getByRole('button', { name: 'Shader Native Agent Fixed QA', exact: true }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: /Native Responses GPU repair/ }).click();
  await page.waitForTimeout(1000);
  return { text: await page.locator('body').innerText(), alerts: await page.getByRole('alert').allTextContents() };
}
