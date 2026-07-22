/* Site-wide card panel (Phase 0).
   Any element with data-card="<name>" opens a bottom-sheet with grounded local
   data (from /api/card) plus live Scryfall image / oracle text / rulings.
   Uses event delegation so dynamically-added cards (Phase 1 collection) work too. */
(function () {
  var ov = document.getElementById('cardpanel');
  if (!ov) return;
  var cur = null;
  function $(id) { return document.getElementById(id); }
  function wrap(id, on) { var e = $(id); if (e) e.hidden = !on; }
  function esc(s) { var d = document.createElement('div'); d.textContent = (s == null ? '' : String(s)); return d.innerHTML; }

  function show() {
    ov.hidden = false; document.body.style.overflow = 'hidden';
    requestAnimationFrame(function () { ov.classList.add('show'); });
  }
  function close() {
    ov.classList.remove('show'); document.body.style.overflow = '';
    setTimeout(function () { ov.hidden = true; }, 260);
  }

  function render(d) {
    $('cp-name').textContent = d.name;
    var tags = [];
    if (d.owned) tags.push('<span class="cp-tag own">✓ ' + d.qty + '× owned</span>');
    else tags.push('<span class="cp-tag buy">not owned</span>');
    if (d.type) tags.push('<span class="cp-tag">' + esc(d.type) + '</span>');
    if (d.mv != null) tags.push('<span class="cp-tag">MV ' + esc(d.mv) + '</span>');
    (d.roles || []).forEach(function (r) { tags.push('<span class="cp-tag">' + esc(r) + '</span>'); });
    $('cp-tags').innerHTML = tags.join('');

    if (d.image && !$('cp-img').getAttribute('src')) $('cp-img').src = d.image;

    var labels = { tcgplayer: 'TCGplayer', manapool: 'ManaPool', cardkingdom: 'Card Kingdom' };
    $('cp-buy').innerHTML = Object.keys(labels).map(function (k) {
      return d.buy && d.buy[k] ? '<a href="' + esc(d.buy[k]) + '" target="_blank" rel="noopener">' + labels[k] + '</a>' : '';
    }).join('');

    if (d.note) {
      wrap('cp-whywrap', true);
      $('cp-why').textContent = d.note.why;
      $('cp-alts').textContent = (d.note.alts && d.note.alts.length) ? ('Alternatives: ' + d.note.alts.join(' · ')) : '';
    } else wrap('cp-whywrap', false);

    if (d.combos && d.combos.length) {
      wrap('cp-combowrap', true);
      $('cp-combos').innerHTML = d.combos.map(function (c) {
        return '<div class="cp-combo"><b>' + esc(c.name) + '</b> → ' + esc(c.result) +
          (c.early ? '<span class="early">EARLY → B4</span>' : '') +
          '<br><span class="cp-imgmeta">needs: ' + (c.with || []).map(esc).join(', ') + '</span></div>';
      }).join('');
    } else wrap('cp-combowrap', false);

    if (d.decks && d.decks.length) {
      wrap('cp-deckwrap', true);
      $('cp-decks').textContent = d.decks.join(' · ');
    } else wrap('cp-deckwrap', false);
  }

  function oracleOf(j) {
    if (j.oracle_text) return j.oracle_text;
    if (j.card_faces) return j.card_faces.map(function (f) { return (f.name ? f.name + '\n' : '') + (f.oracle_text || ''); }).join('\n\n// \n\n');
    return '';
  }

  function loadRulings(uri, name) {
    fetch(uri).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (cur !== name || !j || !j.data || !j.data.length) return;
      wrap('cp-rulewrap', true);
      $('cp-rulings').innerHTML = j.data.slice(0, 8).map(function (r) { return '<li>' + esc(r.comment) + '</li>'; }).join('');
    }).catch(function () {});
  }

  function enrich(name) {
    var orc = $('cp-oracle'); wrap('cp-oraclewrap', true);
    orc.textContent = 'Loading card text from Scryfall…'; orc.className = 'cp-oracle cp-loading';
    fetch('https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(name))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (cur !== name) return;
        if (!j) { orc.textContent = '(Card text unavailable — needs an internet connection.)'; return; }
        var iu = j.image_uris || (j.card_faces && j.card_faces[0] && j.card_faces[0].image_uris);
        if (iu && iu.normal) $('cp-img').src = iu.normal;
        orc.textContent = oracleOf(j) || '(no rules text)'; orc.className = 'cp-oracle';
        var bits = [];
        if (j.mana_cost) bits.push(j.mana_cost);
        if (j.type_line) bits.push(j.type_line);
        if (j.cmc != null) bits.push('MV ' + j.cmc);
        if (j.color_identity) bits.push('ID ' + (j.color_identity.join('') || 'C'));
        if (j.edhrec_rank) bits.push('EDHREC #' + j.edhrec_rank);
        if (j.prices && j.prices.usd) bits.push('~$' + j.prices.usd);
        $('cp-imgmeta').innerHTML = bits.map(esc).join(' &nbsp; ');
        if (j.rulings_uri) loadRulings(j.rulings_uri, name);
      }).catch(function () { orc.textContent = '(Card text unavailable.)'; });
  }

  function open(name) {
    cur = name; show();
    ['cp-whywrap', 'cp-combowrap', 'cp-deckwrap', 'cp-rulewrap'].forEach(function (id) { wrap(id, false); });
    $('cp-name').textContent = name; $('cp-tags').innerHTML = '';
    $('cp-buy').innerHTML = ''; $('cp-imgmeta').innerHTML = '';
    $('cp-img').removeAttribute('src');
    var sc = ov.querySelector('.cp-scroll'); if (sc) sc.scrollTop = 0;
    fetch('/api/card/' + encodeURIComponent(name)).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (cur === name && d) render(d); }).catch(function () {});
    enrich(name);
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest ? e.target.closest('[data-card]') : null;
    if (t) { e.preventDefault(); open(t.getAttribute('data-card')); }
    else if (e.target === ov) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !ov.hidden) { close(); return; }
    var t = e.target.closest ? e.target.closest('[data-card]') : null;
    if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open(t.getAttribute('data-card')); }
  });
  var x = ov.querySelector('.cp-close'); if (x) x.addEventListener('click', close);
})();
