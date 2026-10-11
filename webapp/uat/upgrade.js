// UAT: does a DEPLOY reach a phone that already has the app installed?
//
//   node webapp/uat/upgrade.js <before-dir> <after-dir> [decks-dir]
//
// <before-dir>/<after-dir> are two checkouts of this repo (e.g. `git worktree add`
// the commit on main and your branch). One port, one PERSISTENT Chromium profile
// (service worker, Cache Storage and HTTP cache survive the swap), auth on like the
// hosted app. It installs BEFORE, opens the app twice so the service worker controls
// it, swaps the server to AFTER, then opens the app once — exactly what the player
// does after a sync — and checks that every same-origin stylesheet the page applied
// is rule-for-rule the file the server is serving now.
//
// Why this exists: the 2026-10-11 Arcane Ledger deploy passed every unit test and
// every fresh-browser screenshot, and still rendered the NEW page with the OLD
// app.css on the player's installed phone (the worker answered /static/ cache-first).
// Only a browser that had the previous version installed could see it.
//
// Needs Playwright + Chromium (preinstalled in Claude Code cloud sessions; elsewhere
// `npm i playwright && npx playwright install chromium`). Exit code 0 = pass.
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');

const [before, after, decks] = process.argv.slice(2).map((p) => p && path.resolve(p));
if (!before || !after) { console.error('usage: node upgrade.js <before-dir> <after-dir> [decks-dir]'); process.exit(2); }
const PORT = Number(process.env.UAT_PORT || 5099), BASE = `http://127.0.0.1:${PORT}`, PASS = 'uat-pass';
const OUT = process.env.UAT_OUT || fs.mkdtempSync(path.join(os.tmpdir(), 'uat-upgrade-'));
const UA = 'Mozilla/5.0 (Linux; Android 14; SM-F946U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36';
const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
let server = null;

async function deploy(dir) {
  if (server) { server.kill('SIGTERM'); await new Promise((r) => setTimeout(r, 1200)); }
  const log = fs.openSync(path.join(OUT, 'server.log'), 'a');
  server = spawn('python3', ['webapp/app.py'], { cwd: dir, stdio: ['ignore', log, log],
    env: { ...process.env, MTG_PORT: String(PORT), MTG_PASSWORD: PASS,
           ...(decks ? { MTG_DECKS_DIR: decks } : {}) } });
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(BASE + '/login')).status === 200) return; } catch (e) {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('server did not start in ' + dir);
}

async function open(page, label) {
  await page.goto(BASE + '/', { waitUntil: 'load', timeout: 300000 });
  if (page.url().includes('/login')) {
    await page.fill('input[name=password]', PASS);
    await Promise.all([page.waitForNavigation({ waitUntil: 'load', timeout: 300000 }),
                       page.click('button[type=submit]')]);
  }
  await page.waitForTimeout(2500);                 // let a new worker install/activate
  await page.screenshot({ path: path.join(OUT, `${label}.png`) });
  // Compare each applied same-origin sheet with the file the server is serving NOW.
  // The reference copy is fetched HERE, in Node, straight from the server: a fetch from
  // inside the page would go through the very service worker under test and could
  // come back with the same stale copy (the first draft of this harness passed the
  // broken deploy for exactly that reason).
  const hrefs = await page.evaluate(() => [...document.querySelectorAll('link[rel=stylesheet]')]
    .map((l) => l.href).filter((h) => new URL(h).origin === location.origin));
  const stale = [];
  for (const href of hrefs) {
    const fresh = await (await fetch(BASE + new URL(href).pathname + new URL(href).search)).text();
    const same = await page.evaluate(([h, text]) => {
      const link = [...document.querySelectorAll('link[rel=stylesheet]')].find((l) => l.href === h);
      if (!link || !link.sheet) return false;
      const probe = new CSSStyleSheet(); probe.replaceSync(text);
      const ser = (sheet) => [...sheet.cssRules].map((r) => r.cssText).join('\n');
      return ser(link.sheet) === ser(probe);
    }, [href, fresh]);
    if (!same) stale.push(new URL(href).pathname + new URL(href).search);
  }
  return stale;
}

(async () => {
  let failed = false;
  const ctx = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), 'uat-profile-')), {
    executablePath: exe, viewport: { width: 412, height: 915 }, deviceScaleFactor: 2.625,
    isMobile: true, hasTouch: true, userAgent: UA });
  const page = ctx.pages()[0] || await ctx.newPage();
  try {
    await deploy(before);
    await open(page, '1-before');
    await open(page, '2-before-again');
    await deploy(after);
    const stale = await open(page, '3-after-first-open');
    if (stale.length) { failed = true; console.log('FAIL first open after deploy applied STALE css: ' + stale.join(', ')); }
    else console.log('PASS first open after deploy applied the current stylesheets');
  } finally {
    await ctx.close();
    if (server) server.kill('SIGTERM');
  }
  console.log('screenshots + server log: ' + OUT);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); if (server) server.kill('SIGTERM'); process.exit(2); });
