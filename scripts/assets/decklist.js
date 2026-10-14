/* The Deck tab's list (docs/spec-ux-refresh.md, Wave 1.2). Inlined into every
   dashboard by build_dashboard, so the file stays one self-contained page.
   - List or Cards: remembered on this device. A phone starts on the list, a
     wider screen on the cards it always had.
   - Find in this deck: filters both views by name, accent-insensitive, and
     hides a section with nothing left in it.
   - Each section header folds its section away.
   Without this script the page shows the image grid, every section open. */
(function () {
  var root = document.querySelector('.dl');
  if (!root) return;
  var KEY = 'mtg.deckview';
  var phone = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  var buttons = root.querySelectorAll('.dl-views button');

  function setView(view) {
    root.setAttribute('data-view', view);
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute('aria-pressed', String(buttons[i].getAttribute('data-view') === view));
    }
  }
  setView(saved === 'list' || saved === 'grid' ? saved : (phone ? 'list' : 'grid'));
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function () {
      var view = this.getAttribute('data-view');
      setView(view);
      try { localStorage.setItem(KEY, view); } catch (e) {}
    });
  }

  function fold(sec, closed) {
    sec.classList.toggle('collapsed', closed);
    var t = sec.querySelector('.dl-tog');
    if (t) t.setAttribute('aria-expanded', String(!closed));
  }
  var togs = root.querySelectorAll('.dl-tog');
  for (var j = 0; j < togs.length; j++) {
    togs[j].addEventListener('click', function () {
      var sec = this.closest('.dl-sec');
      fold(sec, !sec.classList.contains('collapsed'));
    });
  }

  function norm(s) {
    s = (s || '').toLowerCase();
    return s.normalize ? s.normalize('NFD').replace(/[̀-ͯ]/g, '') : s;
  }
  var q = root.querySelector('.dl-q'), none = root.querySelector('.dl-none');
  var secs = root.querySelectorAll('.dl-sec');
  if (q) q.addEventListener('input', function () {
    var want = norm(q.value.trim()), any = false;
    for (var a = 0; a < secs.length; a++) {
      var items = secs[a].querySelectorAll('.mc[data-name], .dl-row[data-name]'), hit = false;
      for (var b = 0; b < items.length; b++) {
        var ok = !want || norm(items[b].getAttribute('data-name')).indexOf(want) >= 0;
        items[b].hidden = !ok;
        if (ok) hit = true;
      }
      secs[a].hidden = !!want && !hit;
      if (want && hit) fold(secs[a], false);
      if (hit) any = true;
    }
    if (none) none.hidden = !want || any;
  });

  // Paper gets every section, folded or not.
  window.addEventListener('beforeprint', function () {
    for (var c = 0; c < secs.length; c++) fold(secs[c], false);
  });
})();
