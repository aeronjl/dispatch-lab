// Exercise the same revealed menu that a user sees; never click hidden controls.
async function revealTool(page, selector) {
  const target = page.locator(selector).first();
  if (await target.isVisible()) return;
  if (!await page.locator('.m-utility').isVisible()) await page.locator('[data-do=menu]').click();
  await page.locator('[data-panel=tools]').click();
  await page.locator('[data-work-search]').fill('');
}
async function revealPlayback(page) {
  if (await page.locator('[data-m=controller]').isVisible()) return;
  if (!await page.locator('.m-utility').isVisible()) await page.locator('[data-do=menu]').click();
  await page.locator('[data-panel=run]').click();
}
async function revealOperation(page) {
  if (!await page.locator('.m-utility').isVisible()) await page.locator('[data-do=menu]').click();
  if (!await page.locator('[data-panel=operate]').isVisible()) await page.locator('[data-panel=work]').click();
  await page.locator('[data-panel=operate]').click();
}
module.exports = {revealTool, revealPlayback, revealOperation};
