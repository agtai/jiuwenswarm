/* First-use UI check with ten isolated headless Chromium contexts.
 * Requires Playwright and Chrome. Credentials are read from a private file;
 * screenshots and evidence contain no model/API/login values.
 */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const [accessFile, outputDirectory] = process.argv.slice(2);
  const access = JSON.parse(fs.readFileSync(accessFile, 'utf8').replace(/^\uFEFF/, ''));
  assert.equal(access.length, 10);
  fs.mkdirSync(outputDirectory, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const evidence = await Promise.all(access.map(async (entry, index) => {
      const context = await browser.newContext({
        httpCredentials: { username: entry.username, password: entry.password }
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.name));
      const response = await page.goto(entry.url, { waitUntil: 'networkidle', timeout: 60000 });
      assert.equal(response.status(), 200);
      assert.equal(await page.evaluate(() => window.isSecureContext), true);
      assert.equal(await page.title(), 'JiuwenSwarm');
      await page.getByRole('button', { name: 'More', exact: true }).click();
      if (!(await page.getByRole('heading', { name: 'Configuration', exact: true }).isVisible())) {
        await page.getByRole('button', { name: 'Configuration', exact: true }).click();
      }
      await page.getByRole('heading', { name: 'Configuration', exact: true }).waitFor();
      const empty = await page.locator('input[type="text"],input[type="password"]').evaluateAll(
        fields => fields.length >= 4 && fields.every(field => field.value === '')
      );
      assert.equal(empty, true);
      assert.equal(await page.getByRole('button', { name: 'Save', exact: true }).isDisabled(), true);
      assert.deepEqual(errors, []);
      if (index === 0) await page.screenshot({ path: path.join(outputDirectory, 'first-use-model-setup.png'), fullPage: true });
      return { instance: entry.instance, http: 200, secureContext: true, emptyModelFields: true,
        incompleteModelSaveRejected: true, pageErrors: errors.length };
    }));
    fs.writeFileSync(path.join(outputDirectory, 'browser-evidence.json'), JSON.stringify({
      observedAt: new Date().toISOString(), contexts: evidence, physicalMicrophone: 'not_run',
      agentToolJourney: 'requires_user_model'
    }, null, 2) + '\n');
    console.log(JSON.stringify({ browserContexts: evidence.length, passed: evidence.length,
      firstUseModelConfiguration: 'empty', physicalMicrophone: 'not_run' }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.log(JSON.stringify({ result: 'failed', errorType: error.name })); process.exitCode = 1; });
