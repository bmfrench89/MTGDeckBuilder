/* Site-wide card panel (Phase 0).
   Any element with data-card="<name>" opens a bottom-sheet with grounded local
   data (from /api/card) plus live Scryfall image / oracle text / rulings.
   Uses event delegation so dynamically-added cards (Phase 1 collection) work too. */
(function () {
  var ov = document.getElementById('cardpanel');
  if (!ov) return;
  var cur = null, curData = null, curCard = null;
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

  // Grounded "how it works": role scaffold (server) + mechanic tags read off the oracle.
  var MECH = [
    [/\bdraw\b[^.]*\bcards?\b/, 'draws cards'],
    [/counter target/, 'counters spells'],
    [/(destroy|exile) target/, 'spot removal'],
    [/(destroy|exile) all|each (creature|player|opponent)/, 'symmetric / board-wide'],
    [/search your library/, 'tutors from your library'],
    [/add \{|add one mana|mana of any/, 'produces mana'],
    [/return .*from (your |a )?graveyard/, 'graveyard recursion'],
    [/create .*token/, 'makes tokens'],
    [/hexproof|indestructible|protection from|\bward\b/, 'protection / resilience'],
    [/sacrifice|whenever .*dies/, 'sacrifice synergy'],
    [/extra turn/, 'takes an extra turn'],
    [/can't (untap|attack|block|cast)|skip .*(untap|draw)/, 'stax / denial'],
    [/double|copy target|for each/, 'doubling / scaling']
  ];
  function mechanics(oracle) {
    var t = (oracle || '').toLowerCase(), out = [];
    for (var i = 0; i < MECH.length && out.length < 3; i++) if (MECH[i][0].test(t)) out.push(MECH[i][1]);
    return out;
  }
  function renderStrategy() {
    var wrap = $('cp-stratwrap'), el = $('cp-strategy');
    if (!wrap || !el) return;
    if (curData && curData.note) { wrap.hidden = true; return; }  // curated "Why it works" wins
    var lead = curData && curData.strategy && curData.strategy.role_line;
    if (!lead && curCard && curCard.type_line) {                  // non-owned: fall back to Scryfall
      var mv = curCard.cmc != null ? (curCard.cmc + '-mana ') : '';
      lead = 'A ' + mv + curCard.type_line.split('//')[0].trim().toLowerCase() + '.';
    }
    var mech = curCard ? mechanics(oracleOf(curCard)) : [];
    var notes = [];
    if (curData && curData.strategy && curData.strategy.in_decks) notes.push('in ' + curData.strategy.in_decks + ' of your decks');
    if (curData && curData.combos && curData.combos.length) notes.push('a piece of ' + curData.combos.length + ' combo' + (curData.combos.length > 1 ? 's' : '') + ' you can assemble');
    var html = '';
    if (lead) html += '<p style="margin:.2em 0">' + esc(lead) + '</p>';
    if (mech.length) html += '<p style="margin:.4em 0">' + mech.map(function (m) { return '<span class="cp-tag">' + esc(m) + '</span>'; }).join(' ') + '</p>';
    if (notes.length) html += '<p class="cp-imgmeta" style="margin:.2em 0">Plays as: ' + esc(notes.join(' · ')) + '</p>';
    if (!html) { wrap.hidden = true; return; }
    el.innerHTML = html; wrap.hidden = false;
  }

  function render(d) {
    curData = d;
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

    if ((d.combos && d.combos.length) || (d.completes && d.completes.length)) {
      wrap('cp-combowrap', true);
      var comboHtml = (d.combos || []).map(function (c) {
        return '<div class="cp-combo"><b>' + esc(c.name) + '</b> → ' + esc(c.result) +
          (c.early ? '<span class="early">EARLY → B4</span>' : '') +
          '<br><span class="cp-imgmeta">needs: ' + (c.with || []).map(esc).join(', ') + '</span></div>';
      }).join('');
      // The reverse signal: this card is the ONE missing piece somewhere.
      comboHtml += (d.completes || []).map(function (c) {
        return '<div class="cp-combo"><b>Completes a combo in ' + esc(c.deck) + '</b>' +
          '<br><span class="cp-imgmeta">' + esc(c.combo) + ' → ' + esc(c.result) + '</span></div>';
      }).join('');
      $('cp-combos').innerHTML = comboHtml;
    } else wrap('cp-combowrap', false);

    if (d.decks && d.decks.length) {
      wrap('cp-deckwrap', true);
      $('cp-decks').textContent = d.decks.join(' · ');
    } else wrap('cp-deckwrap', false);

    renderPin(d);
    renderStrategy();
  }

  /* Pin = you deciding which deck gets the one physical copy; every other deck then
     treats it as spoken for (optimize / auto_build / edhrec all honour it).
     The picker offers only decks that actually RUN the card: pinning a card nothing
     plays is the "stale" state the /pins page exists to flag, so we don't mint one.
     An ALREADY-stale pin is the exception — it must be visible and releasable here. */
  function renderPin(d) {
    var wrapEl = $('cp-pinwrap'), sel = $('cp-pin-deck'), st = $('cp-pin-state');
    if (!wrapEl || !sel || !st) return;
    var decks = (d.decks || []).slice(), stale = d.pinned && decks.indexOf(d.pinned) < 0;
    if (!decks.length && !d.pinned) { wrapEl.hidden = true; return; }
    if (stale) decks.push(d.pinned);            // so it can be seen and released
    var opts = ['<option value="none">— not pinned —</option>'];
    decks.forEach(function (s) {
      opts.push('<option value="' + esc(s) + '"' + (s === d.pinned ? ' selected' : '') +
        '>' + esc(s) + (stale && s === d.pinned ? ' (stale)' : '') + '</option>');
    });
    sel.innerHTML = opts.join('');
    sel.value = d.pinned || 'none';
    st.textContent = d.pinned
      ? (stale
        ? 'Pinned to ' + d.pinned + ' — but that deck does not run this card (stale).'
        : 'Pinned to ' + d.pinned + ' — other decks treat this copy as spoken for.')
      : 'Not pinned — freely shared across your decks.';
    wrap('cp-pin-err', false);
    wrapEl.hidden = false;
  }

  function savePin() {
    var btn = $('cp-pin-btn'), sel = $('cp-pin-deck'), err = $('cp-pin-err');
    if (!btn || !sel || !cur) return;
    var name = cur, body = new FormData();
    body.append('card', name);                  // server norms it; don't pre-normalize
    body.append('deck', sel.value);
    body.append('json', '1');
    btn.disabled = true;
    fetch('/pins/move', { method: 'POST', body: body })
      .then(function (r) {
        // The app sits behind a shared-password session: an expired one answers a POST
        // with 401 (and a GET with the login page as HTML). Either way this is not JSON,
        // and failing silently would leave the panel showing a pin that never saved.
        var ct = r.headers.get('content-type') || '';
        if (!r.ok || ct.indexOf('application/json') < 0) throw new Error('not-json');
        return r.json();
      })
      .then(function (j) {
        if (!j || !j.ok) throw new Error('not-ok');
        if (cur !== name) return;               // panel moved on while we were saving
        return fetch('/api/card/' + encodeURIComponent(name))
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (fresh) { if (cur === name && fresh) render(fresh); });
      })
      .catch(function () {
        if (err) { err.textContent = 'Could not save the pin — your session may have expired. Reload and log in.'; err.hidden = false; }
      })
      .then(function () { btn.disabled = false; });
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
        curCard = j; renderStrategy();
        if (j.rulings_uri) loadRulings(j.rulings_uri, name);
      }).catch(function () { orc.textContent = '(Card text unavailable.)'; });
  }

  function open(name) {
    cur = name; curData = curCard = null; show();
    ['cp-stratwrap', 'cp-whywrap', 'cp-combowrap', 'cp-deckwrap', 'cp-rulewrap',
      'cp-pinwrap', 'cp-pin-err'].forEach(function (id) { wrap(id, false); });
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
  var pb = $('cp-pin-btn'); if (pb) pb.addEventListener('click', savePin);
})();
