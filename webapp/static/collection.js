/* The Collection's Cards tab (docs/spec-collection-rebuild.md §4).

   The server does the searching (scripts/collection_query.py) and renders every
   view; this script only makes it feel instant:
     * live search: typing swaps in /collection/results (the same partial a reload
       renders), keeping the last results on screen until the next arrive;
     * "Load more" appends /collection/rows and rewrites the URL, so Back lands at
       the same depth;
     * the Filters and help sheets are real modal dialogs: the back gesture closes
       them, focus goes in and comes back, and Filters shows a live "Show N cards";
     * List or Grid is remembered per device;
     * card images resolve in batches of 75 names (one Scryfall request each), only
       for rows near the screen, and a card with no image shows its name, never a
       broken-image glyph (docs/card-images.md).
   Without JavaScript every one of these is still a working link or form. */
(function () {
  var form = document.getElementById('collForm');
  var input = document.getElementById('collQ');
  var results = document.getElementById('collResults');
  var live = document.getElementById('collLive');
  if (!form || !input || !results) return;

  var VIEW_KEY = 'mtg.collview';
  var dirty = false;          // the query changed since the server rendered the sheets
  var seq = 0;                // newest live-search request; older answers are dropped

  function announce(text) { if (live) { live.textContent = ''; live.textContent = text; } }
  function params(f) {
    var p = new URLSearchParams();
    new FormData(f).forEach(function (v, k) { if (v !== '') p.append(k, v); });
    return p;
  }

  /* ---- List or Grid, remembered per device ------------------------------- */
  function storedView() { try { return localStorage.getItem(VIEW_KEY) || ''; } catch (e) { return ''; } }
  function currentView() {
    var list = document.getElementById('collList');
    var v = list && list.getAttribute('data-view');
    if (v === 'grid' || v === 'list') return v;
    return storedView() === 'grid' ? 'grid' : 'list';
  }
  function setView(v) {
    try { localStorage.setItem(VIEW_KEY, v); } catch (e) {}
    document.documentElement.setAttribute('data-collview', v);
    var list = document.getElementById('collList');
    if (list) list.setAttribute('data-view', v);
    [].forEach.call(document.querySelectorAll('.coll-views [data-view]'), function (a) {
      var on = a.getAttribute('data-view') === v;
      a.classList.toggle('on', on);
      if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
    [].forEach.call(document.querySelectorAll('img.coll-img[src]'), showImage);
  }

  /* ---- Images: resolved by name in batches, only near the screen ---------- */
  var byName = {}, queue = [], timer = null;
  function showImage(img) {
    var url = img.getAttribute(currentView() === 'grid' ? 'data-normal' : 'data-small');
    if (url && img.getAttribute('src') !== url) {
      img.onerror = function () { this.onerror = null; this.removeAttribute('src'); this.classList.add('noimg'); };
      img.src = url;
    }
  }
  function cdn(card, size) {
    var iu = card.image_uris || (card.card_faces && card.card_faces[0] && card.card_faces[0].image_uris);
    return iu && iu[size];
  }
  function flush() {
    timer = null;
    while (queue.length) runBatch(queue.splice(0, 75), 0);
  }
  function runBatch(names, attempt) {
    fetch('https://api.scryfall.com/cards/collection', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifiers: names.map(function (n) { return { name: n }; }) })
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j && attempt < 1) { setTimeout(function () { runBatch(names, 1); }, 1500); return; }
      ((j && j.data) || []).forEach(function (card) {
        var full = (card.name || '').toLowerCase();
        var rec = byName[full] || byName[full.split(' // ')[0]];
        if (!rec) return;
        rec.small = cdn(card, 'small'); rec.normal = cdn(card, 'normal');
      });
      names.forEach(function (n) { settle(byName[n.toLowerCase()]); });
    }).catch(function () {
      if (attempt < 1) { setTimeout(function () { runBatch(names, 1); }, 1500); return; }
      names.forEach(function (n) { settle(byName[n.toLowerCase()]); });
    });
  }
  function settle(rec) {
    if (!rec) return;
    rec.done = true;
    rec.imgs.forEach(function (img) {
      if (rec.small) {
        img.setAttribute('data-small', rec.small); img.setAttribute('data-normal', rec.normal || rec.small);
        showImage(img);
      } else {
        img.classList.add('noimg');          // the row still reads: name, counts, cost
      }
    });
  }
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      var img = e.target;
      if (img.getAttribute('data-small')) { showImage(img); return; }
      var name = img.getAttribute('data-name') || '';
      var k = name.toLowerCase();
      var rec = byName[k] || (byName[k] = { name: name, imgs: [], queued: false, done: false });
      if (rec.imgs.indexOf(img) < 0) rec.imgs.push(img);
      if (rec.done) { settle(rec); return; }
      if (!rec.queued) { rec.queued = true; queue.push(name); if (!timer) timer = setTimeout(flush, 120); }
    });
  }, { rootMargin: '400px' }) : null;
  function watchImages(root) {
    [].forEach.call(root.querySelectorAll('img.coll-img:not([src])'), function (img) {
      if (io) io.observe(img); else if (img.getAttribute('data-small')) showImage(img);
    });
  }

  /* ---- Load more ---------------------------------------------------------- */
  function wireMore() {
    var more = document.getElementById('collMore');
    if (!more || more._wired) return;
    more._wired = true;
    more.addEventListener('click', function (e) {
      var url = more.getAttribute('data-rows');
      if (!url || !window.fetch) return;
      e.preventDefault();
      more.setAttribute('aria-busy', 'true');
      fetch(url, { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          more.removeAttribute('aria-busy');
          if (!j) { location.href = more.href; return; }
          var list = document.getElementById('collList');
          var tmp = document.createElement('ul');
          tmp.innerHTML = j.html;
          var first = tmp.querySelector('.coll-row');
          while (tmp.firstChild) list.appendChild(tmp.firstChild);
          watchImages(list);
          var text = 'Showing ' + j.shown.toLocaleString() + ' of ' + j.matched.toLocaleString();
          var count = document.getElementById('collCount');
          if (count) count.textContent = text;
          announce(text);
          history.replaceState(history.state, '', j.url);
          if (j.more) {
            more.setAttribute('data-rows', j.rows_url);
            more.href = j.url.replace(/([?&])n=\d+/, '$1n=' + Math.min(j.shown + 100, 5000));
          } else {
            more.remove();
            if (first && first.focus) first.focus();      // focus never falls to <body>
          }
        }).catch(function () { location.href = more.href; });
    });
  }

  /* ---- Sort and group submit themselves; List/Grid switch in place -------- */
  function wireTools() {
    var sf = document.getElementById('collSortForm');
    if (sf && !sf._wired) {
      sf._wired = true;
      [].forEach.call(sf.querySelectorAll('select'), function (s) {
        s.addEventListener('change', function () {
          // A new sort key starts in its own natural direction (names A→Z, prices
          // high→low); keeping the old one would open Name as Z→A.
          if (s.name === 'order' && sf.elements.dir) sf.elements.dir.value = '';
          var p = params(sf).toString();                // only the fields that are set
          location.href = sf.getAttribute('action') + (p ? '?' + p : '');
        });
      });
    }
    [].forEach.call(document.querySelectorAll('.coll-views [data-view]'), function (a) {
      if (a._wired) return;
      a._wired = true;
      a.addEventListener('click', function (e) { e.preventDefault(); setView(a.getAttribute('data-view')); });
    });
  }
  function wireResults() {
    watchImages(results);
    wireMore();
    wireTools();
    var v = currentView();
    [].forEach.call(document.querySelectorAll('.coll-views [data-view]'), function (a) {
      var on = a.getAttribute('data-view') === v;
      a.classList.toggle('on', on);
      if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
    var n = results.querySelectorAll('.qchip:not(.clear)').length;
    var cnt = document.querySelector('#collFiltersBtn .cnt');
    var btn = document.getElementById('collFiltersBtn');
    if (btn) {
      if (n && !cnt) { cnt = document.createElement('span'); cnt.className = 'cnt'; btn.appendChild(document.createTextNode(' ')); btn.appendChild(cnt); }
      if (cnt) { if (n) cnt.textContent = n; else cnt.remove(); }
    }
  }

  /* ---- Live search -------------------------------------------------------- */
  function search() {
    var my = ++seq;
    var p = params(form);
    results.setAttribute('aria-busy', 'true');
    return fetch('/collection/results?' + p.toString(), { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (my !== seq) return;                         // a newer search is on its way
        results.removeAttribute('aria-busy');
        if (!j) { form.submit(); return; }
        if (io) io.disconnect();
        results.innerHTML = j.html;
        dirty = true;
        wireResults();
        announce(j.status);
        // Replace, never push: Back must not land on a URL whose results aren't shown.
        history.replaceState(null, '', j.url);
      }).catch(function () { if (my === seq) form.submit(); });
  }
  var debounce = null, lastQ = input.value;
  input.addEventListener('input', function () {
    clearTimeout(debounce);
    debounce = setTimeout(function () {
      if (input.value === lastQ) return;
      lastQ = input.value;
      search();
    }, 300);
  });
  form.addEventListener('submit', function (e) {
    if (!window.fetch) return;
    e.preventDefault();
    clearTimeout(debounce);
    lastQ = input.value;
    input.blur();                                       // a phone closes its keyboard
    search();
  });

  /* ---- Sheets: Filters and help ------------------------------------------- */
  function sheet(id, btnId) {
    var dlg = document.getElementById(id), btn = document.getElementById(btnId);
    if (!dlg || typeof dlg.showModal !== 'function') return null;
    var title = dlg.querySelector('h2[tabindex]');
    var opener = null;
    function open() {
      opener = document.activeElement;
      if (dlg.open) dlg.close();
      dlg.showModal();
      history.pushState({ collSheet: id }, '');
      if (title) title.focus();
    }
    dlg.addEventListener('close', function () {
      if (history.state && history.state.collSheet === id) history.back();
      var back = (opener && document.contains(opener)) ? opener : btn;
      if (back && back.focus) back.focus();
    });
    [].forEach.call(dlg.querySelectorAll('[data-close]'), function (x) {
      x.addEventListener('click', function (e) { e.preventDefault(); dlg.close(); });
    });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });  // the backdrop
    if (btn) btn.addEventListener('click', function (e) {
      e.preventDefault();
      // The sheet was rendered for the query the page loaded with; after live typing,
      // fetch a fresh page with it open instead of showing stale fields.
      if (dirty) {
        var u = new URL(location.href);
        u.searchParams.set(id === 'collFilters' ? 'filters' : 'help', '1');
        location.href = u.toString();
        return;
      }
      open();
    });
    // Opened by the no-JavaScript URL (?filters=1 / ?help=1): make it a real modal,
    // and drop the flag so a reload doesn't reopen it.
    if (dlg.hasAttribute('open')) {
      dlg.removeAttribute('open');
      var u = new URL(location.href);
      u.searchParams.delete('filters'); u.searchParams.delete('help');
      history.replaceState(null, '', u.pathname + u.search);
      open();
    }
    return dlg;
  }
  window.addEventListener('popstate', function () {
    [].forEach.call(document.querySelectorAll('dialog.sheet'), function (d) { if (d.open) d.close(); });
  });

  var filters = sheet('collFilters', 'collFiltersBtn');
  sheet('collHelp', 'collHelpBtn');

  /* The Filters sheet's live count: the fields composed exactly as Show composes them. */
  if (filters) {
    var ff = document.getElementById('collFilterForm');
    var show = document.getElementById('collFiltersShow');
    var reset = document.getElementById('collFiltersReset');
    var ct = null, cseq = 0;
    function count() {
      var my = ++cseq;
      fetch('/api/collection/count?' + params(ff).toString())
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (!j || my !== cseq) return;
          show.disabled = j.n === 0;
          show.textContent = j.n === 0 ? 'No cards match' :
            'Show ' + j.n.toLocaleString() + ' card' + (j.n === 1 ? '' : 's');
        }).catch(function () {});
    }
    function later() { clearTimeout(ct); ct = setTimeout(count, 250); }
    ff.addEventListener('input', later);
    ff.addEventListener('change', later);
    if (reset) reset.addEventListener('click', function (e) {
      e.preventDefault();
      [].forEach.call(ff.elements, function (el) {
        if (el.type === 'hidden' || el.tagName === 'BUTTON') return;
        if (el.type === 'checkbox') el.checked = false;
        else if (el.type === 'radio') el.checked = el.value === 'fits';
        else if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
      });
      later();
    });
    filters.addEventListener('close', function () { clearTimeout(ct); });
    var o = filters.showModal;
    filters.showModal = function () { o.call(filters); count(); };
    if (filters.open) count();
    // Leave the sheet's own history entry before navigating, or Back would return to
    // a duplicate of the page the sheet was opened on.
    ff.addEventListener('submit', function (e) {
      if (!(history.state && history.state.collSheet)) return;
      e.preventDefault();
      var go = function () { window.removeEventListener('popstate', go); ff.submit(); };
      window.addEventListener('popstate', go);
      history.back();
    });
  }

  wireResults();
})();
