// UAT: every main page at phone, Fold, tablet and desktop widths.
//
//   node webapp/uat/sweep.js [base-url]        (default http://127.0.0.1:5000)
//
// Env: UAT_PASSWORD (if the server runs with MTG_PASSWORD), UAT_OUT (screenshot dir),
// UAT_SIZES (e.g. "412x915,884x1104,1440x900"). Logs in, visits each page, opens
// the interactive states (deck-card menu, phone More sheet, card panel) and writes a
// screenshot of each, auditing the open card panel too. Exit 1 on a FAIL:
//   FAIL  page-level horizontal overflow · a tap target under 24 px (WCAG 2.5.8)
//   WARN  a tap target under 44 px · a control you can only reach by scrolling a
//         table or tab bar sideways · text clipped mid-word
// The 2026-10-14 audit found the old version (36 px, overlays and scrollers skipped)
// printing "no flags" over a clipped Pins action and a cut-off Power tab.
// The screenshots still need eyes — read them.
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const PASS = process.env.UAT_PASSWORD || '';
const OUT = process.env.UAT_OUT || fs.mkdtempSync(path.join(os.tmpdir(), 'uat-sweep-'));
const SIZES = (process.env.UAT_SIZES || '360x780,412x915,600x960,768x1024,884x1104,1024x768,1280x800,1440x900').split(',');
const UA_M = 'Mozilla/5.0 (Linux; Android 14; SM-F946U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36';
const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
const PAGES = [['home', '/'], ['build', '/build-next'], ['collection', '/collection'],
               ['coll-grid', '/collection?view=grid&group=type'],
               ['coll-filters', '/collection?filters=1'], ['coll-help', '/collection?help=1'],
               ['coll-add', '/collection/add'], ['coll-manage', '/collection/manage'],
               ['wishlist', '/wishlist'], ['shared', '/shared'], ['pins', '/pins'],
               ['import', '/decks/import'], ['arrivals', '/collection/arrivals'],
               ['people', '/people'], ['activity', '/activity']];

function audit() {          // runs in the page
  const vw = document.documentElement.clientWidth;
  // Hidden things and closed <details> are not on screen; an OPEN overlay is
  // (closed ones carry [hidden]), so the card panel is audited when it shows.
  const skip = (el) => el.closest('[hidden], details:not([open]) > :not(summary)');
  const scroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return p; } return null; };
  const label = (el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}"${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 16)}"`;
  const wide = [...document.querySelectorAll('body *')].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width && r.right > vw + 1 && getComputedStyle(el).position !== 'fixed' && !skip(el) && !scroller(el);
  }).slice(0, 5).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`);
  // Visually hidden controls (a 1px file input behind its styled label, opacity 0)
  // are not targets; the label that stands in for them is, and is checked itself.
  const controls = [...document.querySelectorAll('a, button, summary, select, input:not([type=hidden]):not(.tabinput), label[for]')]
    .filter((el) => { const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      return r.width > 2 && r.height > 2 && cs.opacity !== '0' && cs.visibility !== 'hidden' && !skip(el); });
  // Inline links inside running text are exempt (WCAG 2.5.8's inline exception).
  const inline = (el) => el.closest('p, li, td, .sub, footer, .explain, .tile-note');
  const tiny = [], small = [], sideways = [];
  for (const el of controls) {
    const r = el.getBoundingClientRect();
    if (el.closest('.deckcard .name')) continue;               // whole card is the target
    if (el.closest('label') && el.closest('label').getBoundingClientRect().height >= 44) continue;
    const sc = scroller(el);
    if (sc && r.left >= vw - 4) { sideways.push(label(el)); continue; }
    if (inline(el)) continue;
    if ((r.height < 24 || r.width < 24)) tiny.push(`${label(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
    else if (r.height < 44 && r.width < 300) small.push(`${label(el)} ${Math.round(r.height)}px`);
  }
  const clipped = [...document.querySelectorAll('td, th, .tile, .tile *, .chip, .tag, figcaption')].filter((el) => {
    if (skip(el) || !el.textContent.trim()) return false;
    const cs = getComputedStyle(el);
    return (cs.overflowX === 'hidden' || cs.overflowX === 'clip') && cs.textOverflow !== 'ellipsis'
      && el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 40;
  }).slice(0, 4).map((el) => `${el.tagName.toLowerCase()}"${el.textContent.trim().slice(0, 18)}"`);
  return { overflowX: document.documentElement.scrollWidth - vw, wide,
           tiny: tiny.slice(0, 6), small: small.slice(0, 6), sideways: sideways.slice(0, 4), clipped };
}

(async () => {
  const b = await chromium.launch({ executablePath: exe });
  const fails = [], warns = [];
  const note = (w, name, r) => {
    if (r.overflowX > 1 || r.wide.length) fails.push(`${w} ${name}: page overflows by ${r.overflowX}px ${r.wide.join(' ')}`);
    if (r.tiny.length) fails.push(`${w} ${name}: tap targets under 24px ${r.tiny.join(' | ')}`);
    if (r.small.length) warns.push(`${w} ${name}: tap targets under 44px ${r.small.join(' | ')}`);
    if (r.sideways.length) warns.push(`${w} ${name}: only reachable by scrolling sideways ${r.sideways.join(' | ')}`);
    if (r.clipped.length) warns.push(`${w} ${name}: clipped text ${r.clipped.join(' | ')}`);
  };
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
    const pages = deckHref ? [...PAGES, ['deck', deckHref], ['changes', deckHref + '/changes'],
                              ['optimize', deckHref + '/optimize']] : PAGES;
    for (const [name, url] of pages) {
      await p.goto(BASE + url, { waitUntil: 'load', timeout: 300000 });
      await p.waitForTimeout(300);
      note(w, name, await p.evaluate(audit));
      await p.screenshot({ path: `${OUT}/${w}-${name}.png` });
      if (name === 'home') {
        const menu = p.locator('.deckcard details.menu > summary').first();
        if (await menu.count()) { await menu.click(); await p.waitForTimeout(250);
          await p.screenshot({ path: `${OUT}/${w}-home-menu.png` }); await p.keyboard.press('Escape'); }
        if (mobile) { await p.locator('nav.rail .more > summary').click(); await p.waitForTimeout(250);
          await p.screenshot({ path: `${OUT}/${w}-home-more.png` }); await p.keyboard.press('Escape'); }
      }
      if (name === 'deck') {
        // Whichever view shows: a phone opens on the list (Wave 1.2), a desktop on tiles.
        const fig = p.locator('.dl-row[data-key]:visible, figure.mc[data-key]:visible').nth(1);
        if (await fig.count()) { await fig.scrollIntoViewIfNeeded(); await fig.click(); await p.waitForTimeout(600);
          note(w, 'deck-panel', await p.evaluate(audit));
          await p.screenshot({ path: `${OUT}/${w}-deck-panel.png` }); await p.keyboard.press('Escape'); }
      }
    }
    await ctx.close();
  }
  await b.close();
  if (warns.length) console.log('WARN:\n  ' + warns.join('\n  '));
  console.log(fails.length ? 'FAIL:\n  ' + fails.join('\n  ') : 'no failures (page overflow, targets under 24px)');
  console.log('screenshots: ' + OUT + '  (read them — the flags are not the review)');
  process.exit(fails.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
