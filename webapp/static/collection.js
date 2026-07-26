/* Interactive collection: client-side search/filter/sort over the whole
   collection grid, plus lazy image loading (IntersectionObserver → batch-resolve
   CDN images via /cards/collection, 75 at a time) so a 1,800-card grid only
   fetches images for cards you actually scroll to. Cards open the shared panel
   (they carry data-card, handled by cardpanel.js). */
(function () {
  var grid = document.getElementById('collgrid');
  if (!grid) return;
  var figs = [].slice.call(grid.querySelectorAll('figure.mc'));
  var search = document.getElementById('collsearch');
  var countEl = document.getElementById('collcount');
  var typeSel = document.getElementById('collType');
  var roleSel = document.getElementById('collRole');
  var sortSel = document.getElementById('collSort');
  var indeck = document.getElementById('collIndeck');
  var priced = document.getElementById('collPriced');
  var colorBtns = [].slice.call(document.querySelectorAll('.colorbtn'));
  var sel = {};                       // selected colors

  function colorOk(f) {
    var on = Object.keys(sel).filter(function (k) { return sel[k]; });
    if (!on.length) return true;
    var cc = f.getAttribute('data-colors') || '';
    if (cc === '' || cc === 'C') return true;      // colorless / unknown fit any pick
    for (var i = 0; i < cc.length; i++) if (!sel[cc[i]]) return false;  // subset
    return true;
  }
  function matches(f) {
    var qv = (search.value || '').trim().toLowerCase();
    if (qv && f.getAttribute('data-name').indexOf(qv) < 0) return false;
    if (!colorOk(f)) return false;
    if (typeSel.value && f.getAttribute('data-type') !== typeSel.value) return false;
    if (roleSel.value && (',' + f.getAttribute('data-roles') + ',').indexOf(',' + roleSel.value + ',') < 0) return false;
    if (indeck.checked && !f.getAttribute('data-decks')) return false;
    if (priced.checked && !f.getAttribute('data-price')) return false;
    return true;
  }
  function apply() {
    var n = 0;
    figs.forEach(function (f) {
      var m = matches(f);
      f.hidden = !m;
      if (m) { n++; io.observe(f); }
    });
    countEl.textContent = n.toLocaleString() + ' card' + (n === 1 ? '' : 's');
  }
  function sortGrid() {
    var by = sortSel.value;
    figs.sort(function (a, b) {
      if (by === 'value') return (parseFloat(b.getAttribute('data-price')) || 0) - (parseFloat(a.getAttribute('data-price')) || 0);
      if (by === 'mv') return ((parseFloat(a.getAttribute('data-mv')) || 0) - (parseFloat(b.getAttribute('data-mv')) || 0)) || a.getAttribute('data-name').localeCompare(b.getAttribute('data-name'));
      if (by === 'staple') {
        // lower EDHREC rank = more played; cards not yet resolved sort last
        var ra = parseInt(a.getAttribute('data-edhrec'), 10) || Infinity;
        var rb = parseInt(b.getAttribute('data-edhrec'), 10) || Infinity;
        return (ra - rb) || a.getAttribute('data-name').localeCompare(b.getAttribute('data-name'));
      }
      return a.getAttribute('data-name').localeCompare(b.getAttribute('data-name'));
    });
    figs.forEach(function (f) { grid.appendChild(f); });
  }

  // --- lazy batch image loading ---
  var byName = {}, queue = [], timer = null;
  figs.forEach(function (f) {
    var img = f.querySelector('img'); if (!img) return;
    var k = f.getAttribute('data-card').toLowerCase();
    if (!byName[k]) byName[k] = { name: f.getAttribute('data-card'), imgs: [], figs: [], done: false, queued: false };
    byName[k].imgs.push(img);
    byName[k].figs.push(f);
  });

  // "How staple is this?" — Scryfall ships an EDHREC rank on every card (1 = most played
  // in Commander), and the batch call above already returns it, so the chip is free.
  function stapleChip(fig, rank) {
    if (!rank || fig.querySelector('.staple')) return;
    var tier = rank <= 100 ? ['top100', 'TOP 100']
             : rank <= 500 ? ['top500', 'TOP 500']
             : rank <= 2000 ? ['top2k', 'TOP 2K'] : null;
    if (!tier) return;                       // only badge genuinely-staple cards
    var s = document.createElement('span');
    s.className = 'staple ' + tier[0];
    s.textContent = tier[1];
    s.title = 'EDHREC rank #' + rank + ' — how widely this card is played in Commander';
    fig.appendChild(s);
    fig.setAttribute('data-edhrec', rank);   // lets us sort by staple-ness
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      var rec = byName[e.target.getAttribute('data-card').toLowerCase()];
      if (rec && !rec.done && !rec.queued) { rec.queued = true; queue.push(rec.name); schedule(); }
    });
  }, { rootMargin: '400px' });
  function schedule() { if (!timer) timer = setTimeout(function () { timer = null; flush(); }, 120); }
  function flush() {
    while (queue.length) {
      var batch = queue.splice(0, 75);
      fetch('https://api.scryfall.com/cards/collection', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifiers: batch.map(function (n) { return { name: n }; }) })
      }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !j.data) return;
        j.data.forEach(function (card) {
          var iu = card.image_uris || (card.card_faces && card.card_faces[0] && card.card_faces[0].image_uris);
          var url = iu && iu.normal, k = (card.name || '').toLowerCase();
          var rec = byName[k] || byName[(card.name || '').split('//')[0].trim().toLowerCase()];
          if (!rec) return;
          if (url) { rec.imgs.forEach(function (i) { i.src = url; }); rec.done = true; }
          rec.figs.forEach(function (f) { stapleChip(f, card.edhrec_rank); });
        });
        if (sortSel.value === 'staple') sortGrid();   // fold newly-ranked cards in
      }).catch(function () {});
    }
  }

  colorBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      var c = b.getAttribute('data-color');
      sel[c] = !sel[c]; b.classList.toggle('on', sel[c]); apply();
    });
  });
  search.addEventListener('input', apply);
  [typeSel, roleSel, indeck, priced].forEach(function (el) { el.addEventListener('change', apply); });
  sortSel.addEventListener('change', function () {
    // Ranks arrive lazily with the images, so sorting by "most played" would only order
    // what you've scrolled past. Selecting it resolves the rest of the collection (in
    // 75-card batches) and the grid re-sorts as each batch lands.
    if (sortSel.value === 'staple') {
      Object.keys(byName).forEach(function (k) {
        var rec = byName[k];
        if (!rec.queued) { rec.queued = true; queue.push(rec.name); }
      });
      schedule();
    }
    sortGrid();
  });
  apply();
})();
