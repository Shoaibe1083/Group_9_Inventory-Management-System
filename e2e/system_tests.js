const { chromium } = require('playwright');
// Usage: start the server, then run:  node e2e/system_tests.js  (needs: npm i playwright)
const B = process.env.BASE_URL || 'http://127.0.0.1:8000';
const results = [];
async function t(id, name, fn) {
  try { const r = await fn(); results.push([id, name, 'Pass', r || '']); }
  catch (e) { results.push([id, name, 'FAIL', String(e.message).split('\n')[0]]); }
}
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage();
  await t('SYS-01', 'Wrong password is refused', async () => {
    await p.goto(B + '/accounts/login/');
    await p.fill('input[name=username]', 'admin'); await p.fill('input[name=password]', 'wrong');
    await p.click('button[type=submit]'); await p.waitForLoadState();
    if (!p.url().includes('/accounts/login')) throw new Error('logged in with wrong password');
  });
  await t('SYS-02', 'Login with demo account opens dashboard', async () => {
    await p.fill('input[name=username]', 'admin'); await p.fill('input[name=password]', 'admin123');
    await p.click('button[type=submit]'); await p.waitForURL(B + '/');
    await p.getByText('Stock alerts').first().waitFor();
  });
  let before;
  await t('SYS-03', 'POS sale by barcode: scan, pay, complete', async () => {
    before = (await (await p.request.get(B + '/api/products/lookup/?code=2000000001609')).json());
    await p.goto(B + '/pos/');
    await p.fill('#scan', '2000000001609'); await p.press('#scan', 'Enter');
    await p.waitForFunction(() => document.querySelector('#cartCount').textContent.trim().startsWith('1'));
    await p.click('#checkout');
    await p.waitForSelector('#doneModal:not([hidden])', { timeout: 8000 });
    return (await p.textContent('#doneTitle')).trim();
  });
  await t('SYS-04', 'Receipt shows the product and total', async () => {
    const [rp] = await Promise.all([ctx.waitForEvent('page', { timeout: 3000 }).catch(() => null), p.click('#doneReceipt')]);
    const page = rp || p; await page.waitForLoadState();
    const txt = await page.textContent('body');
    if (!txt.includes('Dabur Honey')) throw new Error('product not on receipt');
    if (rp) await rp.close();
  });
  await t('SYS-05', 'Stock reduced by 1 and ledger row added', async () => {
    const after = await (await p.request.get(B + '/api/products/lookup/?code=2000000001609')).json();
    const q0 = (before.product || before).qty, q1 = (after.product || after).qty;
    if (q1 !== q0 - 1) throw new Error(`stock ${q0} -> ${q1}`);
    await p.goto(B + '/products/160/');
    if (!/sale/i.test(await p.textContent('body'))) throw new Error('no sale in history');
    return `stock ${q0} → ${q1}`;
  });
  await t('SYS-06', 'Stock Alerts page lists low product', async () => {
    await p.goto(B + '/alerts/');
    const txt = await p.textContent('body');
    if (!txt.includes('ACI Pure Miniket')) throw new Error('low product missing');
  });
  await t('SYS-07', 'Reports page and CSV export', async () => {
    await p.goto(B + '/reports/?range=30d'); await p.waitForSelector('canvas');
    const r = await p.request.get(B + '/reports/export/?range=30d');
    const ct = r.headers()['content-type'];
    if (r.status() !== 200 || !ct.includes('csv')) throw new Error('csv ' + r.status() + ' ' + ct);
  });
  await t('SYS-08', 'Global search (Ctrl+K) finds a product', async () => {
    await p.goto(B + '/'); await p.keyboard.press('Control+k');
    await p.waitForSelector('#cmdk:not([hidden])'); await p.fill('#cmdkInput', 'honey');
    await p.waitForFunction(() => /Honey/.test(document.querySelector('#cmdkList').textContent), null, { timeout: 5000 });
  });
  await t('SYS-09', 'Phone width (390 px): no sideways scroll', async () => {
    const m = await ctx.newPage(); await m.setViewportSize({ width: 390, height: 844 });
    await m.goto(B + '/'); const sw = await m.evaluate(() => document.documentElement.scrollWidth);
    await m.close(); if (sw > 392) throw new Error('scrollWidth ' + sw); return 'width ' + sw;
  });
  await t('SYS-10', 'After logout, pages need login again', async () => {
    await p.goto(B + '/');
    await Promise.all([p.waitForNavigation(), p.evaluate(() => document.querySelector('form[action*="logout"]').submit())]); await p.goto(B + '/pos/');
    if (!p.url().includes('/accounts/login')) throw new Error('not redirected: ' + p.url());
  });
  console.log(JSON.stringify(results, null, 1));
  await b.close();
})();
