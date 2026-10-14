// UAT: every main page at phone, Fold, tablet and desktop widths.
//
//   node webapp/uat/sweep.js [base-url]        (default http://127.0.0.1:5000)
//
// Env: UAT_PASSWORD (if the server runs with MTG_PASSWORD), UAT_OUT (screenshot dir),
// UAT_SIZES (e.g. "412x915,884x1104,1440x900"). Logs in, visits each page, opens
// the interactive states (deck-card menu, phone More sheet, card panel) and writes a
// screenshot of each. Flags, without needing eyes: page-level horizontal overflow
// and tap targets under 36px. The screenshots still need eyes — read them.
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const PASS = process.env.UAT_PASSWORD || '';
const OUT = process.env.UAT_OUT || fs.mkdtempSync(path.join(os.tmpdir(), 'uat-sweep-'));
const SIZES = (process.env.UAT_SIZES || '360x780,412x915,600x960,768x1024,884x1104,1024x768,1280x800,1440x900').split(',');
const UA_M = 'Mozilla/5.0 (Linux; Android 14; SM-F946U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36';
const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
const PAGES = [['home', '/'], ['build', '/build-next'], ['collection', '/collection'],
               ['wishlist', '/wishlist'], ['shared', '/shared'], ['pins', '/pins'],
               ['import', '/decks/import'], ['arrivals', '/collection/arrivals'],
               ['people', '/people'], ['activity', '/activity']];

function audit() {          // runs in the page
  const vw = document.documentElement.clientWidth;
  const skip = (el) => el.closest('[hidden], details:not([open]) > :not(summary), .cp-overlay, .cm-overlay');
  const scrollsX = (el) => { for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  const wide = [...document.querySelectorAll('body *')].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width && r.right > vw + 1 && getComputedStyle(el).position !== 'fixed' && !skip(el) && !scrollsX(el);
  }).slice(0, 5).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`);
  const small = [...document.querySelectorAll('a, button, summary, select, input:not(.tabinput)')].filter((el) => {
    const r = el.getBoundingClientRect();
    if (!r.width || skip(el) || el.closest('p, li, td, .sub, footer, .explain, .tile-note')) return false;
    if (el.closest('.deckcard .name')) return false;          // whole card is the target
    if (el.closest('label') && el.closest('label').getBoundingClientRect().height >= 36) return false;
    return r.height < 36 && r.width < 300;
  }).slice(0, 6).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}"${(el.textContent || '').trim().slice(0, 16)}" ${Math.round(el.getBoundingClientRect().height)}px`);
  return { overflowX: document.documentElement.scrollWidth - vw, wide, small };
}

(async () => {
  const b = await chromium.launch({ executablePath: exe });
  const flags = [];
  for (const sz of SIZES) {
    const [w, h] = sz.split('x').map(Number), mobile = w < 900;
    const ctx = await b.newContext({ viewport: { width: w, height: h }, serviceWorkers: 'block',
      ...(mobile ? { deviceScaleFactor: 2.625, isMobile: true, hasTouch: true, userAgent: UA_M } : {}) });
    const p = await ctx.newPage();
    await p.goto(BASE + '/', { waitUntil: 'load', timeout: 300000 });
    if (p.url().includes('/login')) {
      await p.screenshot({ path: `${OUT}/${w}-login.png` });
      await p.fill('input[name=password]', PASS);
      await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), p.click('button[type=submit]')]);
    }
    const deckHref = await p.evaluate(() => (document.querySelector('.deckcard .name a') || {}).getAttribute?.('href'));
    const pages = deckHref ? [...PAGES, ['deck', deckHref]] : PAGES;
    for (const [name, url] of pages) {
      await p.goto(BASE + url, { waitUntil: 'load', timeout: 300000 });
      await p.waitForTimeout(300);
      const r = await p.evaluate(audit);
      if (r.overflowX > 1 || r.wide.length) flags.push(`${w} ${name}: page overflows by ${r.overflowX}px ${r.wide.join(' ')}`);
      if (r.small.length) flags.push(`${w} ${name}: small tap targets ${r.small.join(' | ')}`);
      await p.screenshot({ path: `${OUT}/${w}-${name}.png` });
      if (name === 'home') {
        const menu = p.locator('.deckcard details.menu > summary').first();
        if (await menu.count()) { await menu.click(); await p.waitForTimeout(250);
          await p.screenshot({ path: `${OUT}/${w}-home-menu.png` }); await p.keyboard.press('Escape'); }
        if (mobile) { await p.locator('nav.rail .more > summary').click(); await p.waitForTimeout(250);
          await p.screenshot({ path: `${OUT}/${w}-home-more.png` }); await p.keyboard.press('Escape'); }
      }
      if (name === 'deck') {
        const fig = p.locator('figure.mc[data-key]').nth(1);
        if (await fig.count()) { await fig.scrollIntoViewIfNeeded(); await fig.click(); await p.waitForTimeout(600);
          await p.screenshot({ path: `${OUT}/${w}-deck-panel.png` }); await p.keyboard.press('Escape'); }
      }
    }
    await ctx.close();
  }
  await b.close();
  console.log(flags.length ? 'FLAGGED:\n  ' + flags.join('\n  ') : 'no overflow or small-target flags');
  console.log('screenshots: ' + OUT + '  (read them — the flags are not the review)');
})().catch((e) => { console.error(e); process.exit(2); });
