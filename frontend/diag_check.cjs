const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: [
      '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
      '--disable-gpu-sandbox', '--no-sandbox', '--disable-dev-shm-usage'
    ]
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push('[console] ' + msg.text());
  });
  page.on('pageerror', (e) => errors.push('[pageerror] ' + e.message));
  page.on('requestfailed', (r) => errors.push('[requestfailed] ' + r.url() + ' ' + (r.failure()?.errorText || '')));
  page.on('crash', () => errors.push('[crash] page crashed, reloading...'));

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(3000);
      const alive = await page.evaluate(() => document.readyState);
      if (alive === 'complete' || alive === 'interactive') break;
    } catch (e) {
      errors.push('[attempt' + attempt + '] ' + e.message);
      try { await page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 }); } catch (_) {}
      await page.waitForTimeout(2000);
    }
  }

  const info = await page.evaluate(() => {
    const app = document.querySelector('#app');
    return {
      appChildren: app ? app.children.length : -1,
      bodyText: document.body ? document.body.innerText.slice(0, 400) : '',
      title: document.title,
      readyState: document.readyState,
    };
  }).catch((e) => ({ evalError: e.message }));

  console.log('=== RESULT ===');
  console.log(JSON.stringify(info, null, 2));
  console.log('=== ERRORS (' + errors.length + ') ===');
  errors.slice(0, 20).forEach((e) => console.log(e));
  await browser.close();
})();
