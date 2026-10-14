// UAT: the flows a player runs, end to end, read back from the deck FILES.
//
//   node webapp/uat/flows.js <base-url> <decks-dir>
//
// Run it against a SCRATCH copy of the decks (and collection): it edits decks, and
// puts every file it touched back afterwards. Env: UAT_PASSWORD when the server runs
// with MTG_PASSWORD. Prints PASS / FAIL / SKIP per flow; exit 1 on any FAIL.
//
// Why it exists: the 2026-10-14 UX audit found edit flows that silently damaged
// decks — a one-tap Replace put a white card into mono-green Beorn, "+ Add card"
// filed Cultivate under Commander, the ⚡ report vanished, the mulligan trainer
// counted one hand three times — and every one passed sweep.js, which photographs
// pages but never runs a flow. sweep.js checks how pages LOOK; this checks what
// they DO.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const DECKS = process.argv[3];
const PASS = process.env.UAT_PASSWORD || '';
const exe = fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined;
if (!DECKS || !fs.existsSync(DECKS)) { console.error('usage: flows.js <base-url> <decks-dir>'); process.exit(2); }

const results = [];
const pass = (f, why) => results.push(['PASS', f, why || '']);
const fail = (f, why) => results.push(['FAIL', f, why || '']);
const skip = (f, why) => results.push(['SKIP', f, why || '']);

// --- the deck files, read the way the app writes them ----------------------------
function parseDeck(text) {
  const out = { colors: '', commander: [], cards: [], sections: {}, total: 0 };
  let section = '';
  for (const raw of text.split('\n')) {
    const s = raw.trim();
    const hdr = s.match(/^#\s*Colors:\s*(.*)$/i);
    if (hdr) out.colors = (hdr[1].toUpperCase().match(/[WUBRG]/g) || []).join('');
    const sec = s.match(/^#\s*---\s*(.+?)\s*---\s*$/);
    if (sec) { section = sec[1]; continue; }
    if (!s || s.startsWith('#')) continue;
    const m = s.match(/^(\d+)x?\s+(.+)$/);
    const name = m ? m[2] : s;
    out.total += m ? Number(m[1]) : 1;
    (out.sections[section] = out.sections[section] || []).push(name);
    if (section.toLowerCase().startsWith('commander')) out.commander.push(name);
    else out.cards.push(name);
  }
  return out;
}
const BASICS = /^(snow-covered )?(plains|island|swamp|mountain|forest|wastes)$/i;
const read = (f) => fs.readFileSync(f, 'utf8');
function snapshot(stem) {
  const files = {};
  for (const f of fs.readdirSync(DECKS)) if (f.startsWith(stem + '.')) files[f] = read(path.join(DECKS, f));
  return files;
}
function restore(stem, files) {
  for (const f of fs.readdirSync(DECKS)) {
    if (!f.startsWith(stem + '.')) continue;
    const p = path.join(DECKS, f);
    if (f in files) fs.writeFileSync(p, files[f]); else fs.unlinkSync(p);
  }
}

(async () => {
  const b = await chromium.launch({ executablePath: exe });
  const ctx = await b.newContext({ viewport: { width: 412, height: 915 }, isMobile: true,
                                   hasTouch: true, serviceWorkers: 'block' });
  const p = await ctx.newPage();
  await p.goto(BASE + '/', { waitUntil: 'load', timeout: 300000 });
  if (p.url().includes('/login')) {
    await p.fill('input[name=password]', PASS);
    await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), p.click('button[type=submit]')]);
  }
  const api = p.request;
  const search = async (q, stem, strict) => {
    const r = await api.get(`${BASE}/api/collection/search?q=${encodeURIComponent(q)}&deck=${encodeURIComponent(stem)}${strict ? '&strict=1' : ''}`);
    return r.ok() ? r.json() : [];
  };
  const QUERIES = ['so', 'an', 'ar', 'dr', 'th', 'el', 'st', 're', 'li', 'ma', 'go', 'sh'];

  // A deck with 1–4 colours, so off-colour cards exist, and a nonbasic card to act on.
  const decks = fs.readdirSync(DECKS).filter((f) => f.endsWith('.txt')).sort();
  let stem = null, deck = null;
  for (const f of decks) {
    const d = parseDeck(read(path.join(DECKS, f)));
    if (d.colors && d.colors.length < 5 && d.commander.length && d.cards.some((n) => !BASICS.test(n))) {
      stem = f.slice(0, -4); deck = d; break;
    }
  }
  if (!stem) { console.log('No suitable deck (needs a # Colors: header with 1–4 colours).'); process.exit(2); }
  const target = deck.cards.find((n) => !BASICS.test(n));
  const deckFile = path.join(DECKS, stem + '.txt');
  console.log(`deck: ${stem} [${deck.colors}] · acting on: ${target}`);

  // F1 · Replace refuses an off-colour card, and the replace search never offers one.
  {
    let off = null;
    for (const q of QUERIES) {
      const list = await search(q, stem, false);
      off = (list || []).find((it) => it.legal === false);
      if (off) break;
    }
    if (!off) skip('F1 replace refuses off-colour', 'no colour data in this collection');
    else {
      const before = read(deckFile);
      const r = await api.post(`${BASE}/deck/${stem}/card`, { form: { action: 'replace', name: target, replacement: off.name }, maxRedirects: 0 });
      const after = read(deckFile);
      if (r.status() === 409 && before === after) pass('F1 replace refuses off-colour', `${off.name} refused (409), file untouched`);
      else fail('F1 replace refuses off-colour', `${off.name}: status ${r.status()}, file ${before === after ? 'untouched' : 'CHANGED'}`);
      let leak = null;
      for (const q of QUERIES.slice(0, 6)) {
        leak = ((await search(q, stem, true)) || []).find((it) => it.legal === false);
        if (leak) break;
      }
      if (leak) fail('F1b in-colour replace search', `strict search offered ${leak.name}`);
      else pass('F1b in-colour replace search', 'strict search offered only in-colour cards');
    }
  }

  // F2 · The commander can't be swapped from a one-tap sheet.
  {
    const before = read(deckFile);
    const r = await api.post(`${BASE}/deck/${stem}/card`, { form: { action: 'remove', name: deck.commander[0] }, maxRedirects: 0 });
    const after = read(deckFile);
    if (r.status() === 409 && before === after) pass('F2 commander guarded', 'remove refused (409), file untouched');
    else fail('F2 commander guarded', `status ${r.status()}, file ${before === after ? 'untouched' : 'CHANGED'}`);
  }

  // F3 · "+ Add card" with no section files the card by type, never under Commander,
  // and says when the deck is no longer 100.
  {
    const files = snapshot(stem);
    const have = new Set([...deck.cards, ...deck.commander].map((n) => n.toLowerCase()));
    let pick = null;
    for (const q of QUERIES) {
      pick = ((await search(q, stem, true)) || []).find((it) => !have.has(it.name.toLowerCase()) && !BASICS.test(it.name));
      if (pick) break;
    }
    if (!pick) skip('F3 add files by type', 'no in-colour owned card outside the deck');
    else {
      const r = await api.post(`${BASE}/deck/${stem}/add`, { form: { name: pick.name, section: '' } });
      const j = r.ok() ? await r.json() : {};
      const after = parseDeck(read(deckFile));
      const where = Object.keys(after.sections).find((s) => (after.sections[s] || []).some((n) => n.toLowerCase() === pick.name.toLowerCase()));
      const total = after.total;
      if (!j.ok) fail('F3 add files by type', `add refused: ${j.error || r.status()}`);
      else if (!where || where.toLowerCase().startsWith('commander')) fail('F3 add files by type', `${pick.name} landed under "${where}"`);
      else if (where !== j.section) fail('F3 add files by type', `reply said "${j.section}", file has "${where}"`);
      else pass('F3 add files by type', `${pick.name} → ${where}`);
      const wasHundred = parseDeck(files[stem + '.txt']).total === 100;
      if (wasHundred && !(j.size_note || '').includes('101')) fail('F3b size warning', `no warning at ${total} cards: ${j.size_note}`);
      else if (wasHundred) pass('F3b size warning', j.size_note);
      else skip('F3b size warning', `deck was ${parseDeck(files[stem + '.txt']).total} cards, not 100`);
    }
    restore(stem, files);
  }

  // F4 · ⚡ opens a REVIEW and writes nothing (spec-optimizer-judgment Phase B).
  {
    const files = snapshot(stem);
    const before = read(deckFile);
    await p.goto(`${BASE}/deck/${stem}/optimize`, { waitUntil: 'load', timeout: 300000 });
    const h = await p.evaluate(() => (document.querySelector('h1') || {}).textContent || '');
    if (!/Suggested swaps/.test(h)) fail('F4 optimize review shown', `heading was "${h.trim().slice(0, 60)}"`);
    else if (read(deckFile) !== before) fail('F4 optimize review shown', 'opening the review wrote the deck');
    else pass('F4 optimize review shown', 'review page, deck untouched');
    restore(stem, files);
  }

  // F5 · The mulligan trainer counts one decision once.
  {
    await p.goto(`${BASE}/deck/${stem}/mulligan`, { waitUntil: 'load', timeout: 300000 });
    const keep = p.locator('#keep');
    try {
      await keep.waitFor({ state: 'visible', timeout: 20000 });
      await keep.click();
      await p.locator('#reveal').waitFor({ state: 'visible', timeout: 20000 });
      const askShown = await p.evaluate(() => getComputedStyle(document.getElementById('ask')).display !== 'none');
      const stats = await p.textContent('#stats');
      if (askShown) fail('F5 mulligan counts once', 'Keep/Mulligan still showing after the decision');
      else if (!/^\s*1 hand/.test(stats || '')) fail('F5 mulligan counts once', `stats read "${(stats || '').trim()}"`);
      else pass('F5 mulligan counts once', (stats || '').trim().slice(0, 60));
    } catch (e) { fail('F5 mulligan counts once', String(e).slice(0, 120)); }
  }

  // F6 · No raw markdown on the screen opponents read, and pages arrive compressed.
  {
    const r = await api.get(`${BASE}/deck/${stem}/table-card`);
    const html = await r.text();
    const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<[^>]+>/g, ' ');
    if (/\*\*|(^|\s)\*\w/.test(text)) fail('F6 table card is clean', 'raw markdown asterisks in the visible text');
    else pass('F6 table card is clean', 'no raw markdown');
    const g = await api.get(`${BASE}/`, { headers: { 'Accept-Encoding': 'gzip' } });
    const enc = (g.headers()['content-encoding'] || '');
    if (enc.includes('gzip')) pass('F6b pages compressed', 'Content-Encoding: gzip');
    else fail('F6b pages compressed', `Content-Encoding: "${enc}"`);
  }

  // --- Wave 1.1: every edit can be undone, through the screens a player taps ----
  // Compared as {section: sorted cards}: an undo may put a card back at the end of
  // its section rather than on its old line, which reads the same to a player.
  const shape = (text) => {
    const d = parseDeck(text), out = {};
    for (const [s, names] of Object.entries(d.sections)) out[s] = [...names].map((n) => n.toLowerCase()).sort();
    return JSON.stringify(out);
  };
  const toast = async () => p.evaluate(() => {
    const t = document.querySelector('[data-utoast]');
    return t && !t.hidden ? { msg: t.querySelector('.ut-msg').textContent, label: t.querySelector('.ut-btn').textContent } : null;
  });

  // F7 · Replace from the card panel, then Undo from the toast it leaves.
  {
    const files = snapshot(stem);
    const before = read(deckFile);
    try {
      await p.goto(`${BASE}/deck/${stem}`, { waitUntil: 'load', timeout: 300000 });
      const opened = await p.evaluate((t) => {
        // Whichever view is showing (a phone opens on the list since Wave 1.2).
        const f = [...document.querySelectorAll('.dl-row[data-key], figure.mc[data-key]')]
          .find((x) => x.getAttribute('data-key').toLowerCase() === t.toLowerCase() && x.offsetParent);
        if (!f) return false;
        f.scrollIntoView(); f.click(); return true;
      }, target);
      if (!opened) throw new Error(`no card tile for ${target}`);
      await p.locator('#cm-replace').waitFor({ state: 'visible', timeout: 30000 });
      await p.click('#cm-replace');
      const have = new Set([...deck.cards, ...deck.commander].map((n) => n.toLowerCase()));
      let picked = null;
      for (const q of QUERIES) {
        await p.fill('#cm-search', q);
        await p.waitForTimeout(700);
        picked = await p.evaluate((haveList) => {
          const have = new Set(haveList);
          const b = [...document.querySelectorAll('#cm-searchres .cm-searchitem')]
            .find((x) => !have.has(x.textContent.replace(/ ×\d+$/, '').toLowerCase()) &&
                         !/^(snow-covered )?(plains|island|swamp|mountain|forest|wastes)\b/i.test(x.textContent));
          if (!b) return null;
          return b.textContent.replace(/ ×\d+$/, '');
        }, [...have]);
        if (picked) break;
      }
      if (!picked) { skip('F7 panel replace → toast → Undo', 'no in-colour owned card to swap in'); }
      else {
        await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }),
          p.evaluate((nm) => [...document.querySelectorAll('#cm-searchres .cm-searchitem')]
            .find((x) => x.textContent.replace(/ ×\d+$/, '') === nm).click(), picked)]);
        const t = await toast();
        const swapped = read(deckFile).toLowerCase().includes(picked.toLowerCase());
        if (!swapped) fail('F7 panel replace → toast → Undo', `the replace didn't land (${picked})`);
        else if (!t || !/Replaced/.test(t.msg)) fail('F7 panel replace → toast → Undo', 'no Undo toast after the panel reload');
        else {
          await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), p.click('.utoast .ut-btn')]);
          const back = read(deckFile);
          const redo = await toast();
          if (shape(back) !== shape(before)) fail('F7 panel replace → toast → Undo', 'the list did not come back');
          else pass('F7 panel replace → toast → Undo',
            `${target} ⇄ ${picked}; ${back === before ? 'byte-identical' : 'same sections'}; then "${redo ? redo.label : 'no'}" offered`);
        }
      }
    } catch (e) { fail('F7 panel replace → toast → Undo', String(e).slice(0, 140)); }
    restore(stem, files);
  }

  // F8 · ⚡ review → tick every proposal → apply, then undo the whole run in one tap.
  {
    const files = snapshot(stem);
    const before = read(deckFile);
    try {
      await p.goto(`${BASE}/deck/${stem}/optimize`, { waitUntil: 'load', timeout: 300000 });
      const n = await p.$$eval('input[name="pick"]', (els) => { els.forEach((e) => { e.checked = true; }); return els.length; });
      if (!n) { skip('F8 ⚡ run → Undo all', 'the optimizer proposed no swaps on this deck'); restore(stem, files); }
      else await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }),
        p.click('form[action$="/optimize"] button[type="submit"]')]);
      const t = n ? await toast() : null;
      if (!n) { /* skipped above */ }
      else if (read(deckFile) === before) skip('F8 ⚡ run → Undo all', 'the ticked swaps were no longer proposed');
      else if (!t) fail('F8 ⚡ run → Undo all', 'swaps were written but no Undo toast');
      else {
        await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), p.click('.utoast .ut-btn')]);
        if (shape(read(deckFile)) === shape(before)) pass('F8 ⚡ run → Undo all', `"${t.msg.trim()}" → ${t.label} → list restored`);
        else fail('F8 ⚡ run → Undo all', 'the list did not come back');
      }
    } catch (e) { fail('F8 ⚡ run → Undo all', String(e).slice(0, 140)); }
    restore(stem, files);
  }

  // F9 · The Changes page: Undo on a row, and the row then reads "Undone".
  {
    const files = snapshot(stem);
    const before = read(deckFile);
    try {
      let pick = null;
      const have = new Set([...deck.cards, ...deck.commander].map((n) => n.toLowerCase()));
      for (const q of QUERIES) {
        pick = ((await search(q, stem, true)) || []).find((it) => !have.has(it.name.toLowerCase()) && !BASICS.test(it.name));
        if (pick) break;
      }
      if (!pick) skip('F9 Changes page Undo', 'no in-colour owned card to swap in');
      else {
        await api.post(`${BASE}/deck/${stem}/card`, { form: { action: 'replace', name: target, replacement: pick.name }, maxRedirects: 0 });
        await p.goto(`${BASE}/deck/${stem}/changes`, { waitUntil: 'load', timeout: 300000 });
        const label = `Undo: ${pick.name} replacing ${target}`;
        await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }),
          p.click(`button[aria-label="${label.replace(/"/g, '\\"')}"]`)]);
        const undoneShown = await p.evaluate(() => [...document.querySelectorAll('.chg-act')].some((x) => x.textContent.trim() === 'Undone'));
        if (shape(read(deckFile)) !== shape(before)) fail('F9 Changes page Undo', 'the list did not come back');
        else if (!undoneShown) fail('F9 Changes page Undo', 'the row does not read "Undone"');
        else pass('F9 Changes page Undo', `${pick.name} → Undo → "Undone"`);
      }
    } catch (e) { fail('F9 Changes page Undo', String(e).slice(0, 140)); }
    restore(stem, files);
  }

  // F10 · Database mode: put back an earlier version from the Changes page.
  {
    const files = snapshot(stem);
    const before = read(deckFile);
    try {
      let pick = null;
      const have = new Set([...deck.cards, ...deck.commander].map((n) => n.toLowerCase()));
      for (const q of QUERIES) {
        pick = ((await search(q, stem, true)) || []).find((it) => !have.has(it.name.toLowerCase()) && !BASICS.test(it.name));
        if (pick) break;
      }
      if (!pick) skip('F10 restore an earlier version', 'no in-colour owned card to swap in');
      else {
        await api.post(`${BASE}/deck/${stem}/card`, { form: { action: 'replace', name: target, replacement: pick.name }, maxRedirects: 0 });
        await p.goto(`${BASE}/deck/${stem}/changes`, { waitUntil: 'load', timeout: 300000 });
        if (!(await p.locator('#versions').count())) skip('F10 restore an earlier version', 'files backend: versions are kept in database mode only');
        else {
          const btn = p.locator('form[action$="/restore"] button').first();
          if (!(await btn.count())) fail('F10 restore an earlier version', 'no earlier version offered');
          else {
            p.once('dialog', (d) => d.accept());
            await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), btn.click()]);
            const t = await toast();
            if (shape(read(deckFile)) !== shape(before)) fail('F10 restore an earlier version', 'the list did not come back');
            else if (!t) fail('F10 restore an earlier version', 'no Undo toast after the restore');
            else pass('F10 restore an earlier version', t.msg.trim());
          }
        }
      }
    } catch (e) { fail('F10 restore an earlier version', String(e).slice(0, 140)); }
    restore(stem, files);
  }

  // F12 · The deck page on a phone (Wave 1.2): the tabs on the first screen, the list
  // by default, the filter narrows it, a row opens the panel, the card zooms.
  {
    try {
      await p.goto(`${BASE}/deck/${stem}`, { waitUntil: 'load', timeout: 300000 });
      const why = [];
      const st = await p.evaluate(() => {
        const tabs = document.querySelector('.tabs'), dl = document.querySelector('.dl');
        const row = document.querySelector('.dl-row'), fig = document.querySelector('figure.mc');
        return { tabsTop: tabs ? tabs.getBoundingClientRect().top : 1e9, vh: innerHeight,
                 view: dl && dl.getAttribute('data-view'),
                 rowShown: !!(row && row.offsetParent), figShown: !!(fig && fig.offsetParent),
                 glanceOpen: !!(document.getElementById('glance') || {}).open };
      });
      if (st.tabsTop > st.vh) why.push(`tabs start ${Math.round(st.tabsTop)}px down, past the first screen (${st.vh}px)`);
      if (st.view !== 'list' || !st.rowShown || st.figShown) why.push(`view ${st.view}: rows ${st.rowShown ? 'shown' : 'hidden'}, tiles ${st.figShown ? 'shown' : 'hidden'}`);
      if (st.glanceOpen) why.push('the tiles are open on a phone');
      const word = target.split(/\s+/)[0].toLowerCase();
      await p.fill('.dl-q', word);
      const f = await p.evaluate((w) => {
        const rows = [...document.querySelectorAll('.dl-row')], shown = rows.filter((r) => r.offsetParent);
        return { shown: shown.length, all: rows.length,
                 bad: shown.filter((r) => !r.getAttribute('data-name').includes(w)).length };
      }, word);
      if (!(f.shown > 0 && f.shown < f.all && f.bad === 0)) why.push(`filter "${word}": ${f.shown}/${f.all} rows shown, ${f.bad} not matching`);
      await p.evaluate((t) => {
        const r = [...document.querySelectorAll('.dl-row')].find((x) => x.offsetParent && x.getAttribute('data-name') === t.toLowerCase());
        if (r) r.click();
      }, target);
      await p.waitForTimeout(500);
      if (!(await p.evaluate(() => { const o = document.getElementById('cardmodal'); return !!(o && !o.hidden); }))) why.push('a row did not open the card panel');
      else {
        await p.click('#cm-img');
        const zoomed = await p.locator('.cm-zoom').count();
        if (zoomed) await p.click('.cm-zoom');
        const gone = !(await p.locator('.cm-zoom').count());
        if (!zoomed || !gone) why.push(`tap-to-zoom: ${zoomed ? 'opened' : 'did not open'}, ${gone ? 'closed' : 'did not close'}`);
      }
      if (why.length) fail('F12 phone deck page', why.join('; '));
      else pass('F12 phone deck page', `tabs at ${Math.round(st.tabsTop)}px of ${st.vh}; list by default; "${word}" → ${f.shown}/${f.all} rows; row → panel → zoom`);
    } catch (e) { fail('F12 phone deck page', String(e).slice(0, 140)); }
  }

  // F13 · The Collection page sorts without freezing. The accessibility batch's
  // card-name observer re-scanned the whole grid for every tile a sort moved, and
  // every sort froze the page for 4-6 s (17-29 s on a slow phone) while all 14
  // flows above passed, because none of them sorted 3,294 tiles and timed it. Since
  // the rebuild (docs/spec-collection-rebuild.md) a sort is a server round trip, so
  // it is timed from the choice to the new page's first frame.
  {
    try {
      await p.goto(`${BASE}/collection`, { waitUntil: 'load', timeout: 300000 });
      if (!(await p.$('#collSort'))) skip('F13 collection sort is quick', 'no sort control on this build');
      else {
        const times = [], orders = [];
        for (const v of ['mv', 'free', '']) {
          const t0 = Date.now();
          await Promise.all([p.waitForNavigation({ waitUntil: 'load', timeout: 60000 }),
                             p.selectOption('#collSort', v)]);
          await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0))));
          times.push(Date.now() - t0);
          orders.push(await p.evaluate(() => new URL(location.href).searchParams.get('order') || ''));
        }
        const n = await p.evaluate(() => document.querySelectorAll('[data-card]').length);
        if (Math.max(...times) > 2500) fail('F13 collection sort is quick', `${n} rows; sorts took ${times.join(' / ')} ms`);
        else if (orders.join(',') !== 'mv,free,') fail('F13 collection sort is quick', `the URL carried order ${orders.join(' / ')}`);
        else pass('F13 collection sort is quick', `${n} rows; sorts took ${times.join(' / ')} ms`);
      }
    } catch (e) { fail('F13 collection sort is quick', String(e).slice(0, 140)); }
  }

  // F14 · The Collection rebuild on a phone (docs/spec-collection-rebuild.md §4): the
  // first card on the first screen, live search, a scope chip, a chip removing its own
  // term, the Filters sheet's count agreeing with the page it opens, "Load more"
  // keeping its depth through a visit to Add and Back, the sub-tabs, and the help
  // sheet giving focus back.
  {
    const why = [];
    try {
      await p.goto(`${BASE}/collection`, { waitUntil: 'load', timeout: 300000 });
      if (!(await p.$('#collQ'))) skip('F14 collection search', 'no search bar on this build');
      else {
        const top = await p.evaluate(() => { const r = document.querySelector('.coll-row');
          return r ? Math.round(r.getBoundingClientRect().top) : 1e9; });
        if (top > 915) why.push(`first card ${top}px down`);
        await p.fill('#collQ', 't:creature');
        await p.waitForFunction(() => /card/.test(document.getElementById('collLive').textContent),
                                null, { timeout: 15000 });
        if (!/q=t(%3A|:)creature/.test(p.url())) why.push('live search left the URL behind');
        await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), p.click('.scopes a:has-text("Free")')]);
        if (!/scope=free/.test(p.url())) why.push('Free chip: no scope in the URL');
        if (!/free copies/.test(await p.textContent('#collSummary'))) why.push('Free chip: the summary does not say so');
        await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), p.click('.applied .qchip >> nth=0')]);
        if (/[?&]q=/.test(p.url()) || !/scope=free/.test(p.url())) why.push(`removing the chip gave ${p.url()}`);
        await p.click('#collFiltersBtn');
        await p.waitForSelector('#collFilters[open]');
        await p.check('input[name=fi_c][value=G]');
        await p.check('input[name=fi_role][value=ramp]');
        await p.waitForFunction(() => { const t = document.getElementById('collFiltersShow').textContent;
          return /^Show [\d,]+ card|No cards match/.test(t); }, null, { timeout: 15000 });
        await p.waitForTimeout(600);                                   // the count settles
        const label = (await p.textContent('#collFiltersShow')).trim();
        const want = Number(((label.match(/[\d,]+/) || ['0'])[0]).replace(/,/g, ''));
        await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), p.click('#collFiltersShow')]);
        const got = Number((((await p.textContent('#collSummary')).match(/^([\d,]+) card/) || [0, '-1'])[1]).replace(/,/g, ''));
        if (want !== got) why.push(`the sheet said "${label}", the page shows ${got}`);
        await p.goto(`${BASE}/collection`, { waitUntil: 'load' });
        const more = p.locator('#collMore');
        let depth = '';
        if (await more.count()) {
          await more.scrollIntoViewIfNeeded();
          await more.click();
          await p.waitForFunction(() => document.querySelectorAll('.coll-row').length > 100, null, { timeout: 15000 });
          const n1 = await p.evaluate(() => document.querySelectorAll('.coll-row').length);
          await Promise.all([p.waitForNavigation({ waitUntil: 'load' }), p.click('.subtabs a:has-text("Add")')]);
          if (!(await p.$('#batch'))) why.push('the Add tab has no batch form');
          await p.goBack({ waitUntil: 'load' });
          const n2 = await p.evaluate(() => document.querySelectorAll('.coll-row').length);
          if (n2 !== n1) why.push(`Back after Load more showed ${n2} rows, not ${n1}`);
          depth = `; Load more → ${n1} rows, kept through Back`;
        }
        await p.goto(`${BASE}/collection/manage`, { waitUntil: 'load' });
        const cur = await p.evaluate(() => ((document.querySelector('.subtabs [aria-current=page]') || {}).textContent || '').trim());
        if (!/^Manage/.test(cur)) why.push(`the Manage tab is not marked current ("${cur}")`);
        await p.goto(`${BASE}/collection`, { waitUntil: 'load' });
        await p.click('#collHelpBtn');
        await p.waitForSelector('#collHelp[open]');
        await p.keyboard.press('Escape');
        await p.waitForTimeout(300);
        const focus = await p.evaluate(() => document.activeElement && document.activeElement.id);
        if (focus !== 'collHelpBtn') why.push(`help closed with focus on "${focus}"`);
        if (why.length) fail('F14 collection search', why.join('; '));
        else pass('F14 collection search', `first card at ${top}px; "${label}" = the page${depth}`);
      }
    } catch (e) { fail('F14 collection search', (why.join('; ') + ' ' + String(e)).slice(0, 200)); }
  }

  // F11 · Keyboard only (Wave 1.5): the skip link, then a card name opens the panel,
  // focus goes in, and Escape brings it back to the card, on both panels.
  {
    try {
      const kb = await b.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
      const k = await kb.newPage();
      await k.goto(BASE + '/', { waitUntil: 'load', timeout: 300000 });
      if (k.url().includes('/login')) {
        await k.fill('input[name=password]', PASS);
        await Promise.all([k.waitForNavigation({ waitUntil: 'load', timeout: 300000 }), k.click('button[type=submit]')]);
      }
      const why = [];
      await k.goto(`${BASE}/pins`, { waitUntil: 'load', timeout: 300000 });
      await k.keyboard.press('Tab');
      const skip = await k.evaluate(() => { const a = document.activeElement; const r = a.getBoundingClientRect();
        return a.classList.contains('skiplink') && r.top >= 0; });
      if (!skip) why.push('Tab did not land on a visible skip link');
      else {
        await k.keyboard.press('Enter');
        if (!(await k.evaluate(() => document.activeElement && document.activeElement.id === 'main'))) why.push('the skip link did not move focus to main');
      }
      // App panel: a card name is a tab stop; Enter opens; Escape returns focus.
      const hasCard = await k.evaluate(() => { const c = document.querySelector('[data-card][tabindex="0"]'); if (c) c.focus(); return !!c; });
      if (!hasCard) why.push('no focusable card name on Pins');
      else {
        await k.keyboard.press('Enter');
        await k.waitForTimeout(400);
        if (!(await k.evaluate(() => document.activeElement && document.activeElement.classList.contains('cp-close')))) why.push('app panel: focus did not move in');
        await k.keyboard.press('Escape');
        await k.waitForTimeout(400);
        if (!(await k.evaluate(() => document.activeElement && document.activeElement.hasAttribute('data-card')))) why.push('app panel: focus did not come back');
      }
      // Dashboard panel: a card tile.
      await k.goto(`${BASE}/deck/${stem}`, { waitUntil: 'load', timeout: 300000 });
      await k.evaluate(() => document.querySelector('figure.mc[data-key]').focus());
      await k.keyboard.press('Enter');
      await k.waitForTimeout(400);
      if (!(await k.evaluate(() => document.activeElement && document.activeElement.classList.contains('cm-close')))) why.push('deck panel: focus did not move in');
      await k.keyboard.press('Escape');
      await k.waitForTimeout(400);
      if (!(await k.evaluate(() => document.activeElement && document.activeElement.matches('figure.mc[data-key]')))) why.push('deck panel: focus did not come back');
      await kb.close();
      if (why.length) fail('F11 keyboard: skip link + panel focus', why.join('; '));
      else pass('F11 keyboard: skip link + panel focus', 'skip → main; Enter opens, focus in; Escape returns it (both panels)');
    } catch (e) { fail('F11 keyboard: skip link + panel focus', String(e).slice(0, 140)); }
  }

  await b.close();
  for (const [s, f, why] of results) console.log(`${s.padEnd(4)} ${f}${why ? ' — ' + why : ''}`);
  process.exit(results.some((r) => r[0] === 'FAIL') ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
