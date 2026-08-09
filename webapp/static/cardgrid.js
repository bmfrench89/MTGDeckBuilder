/* Card-image loader for the web app (build-deck view, later the collection grid).
   Resolves every card NAME -> its Scryfall CDN image in batches via
   POST /cards/collection (up to 75 ids per request), so a 100-card page is ~2
   requests to the un-rate-limited CDN instead of 100 hits on the 2/s
   /cards/named endpoint. That makes pictures load fast even on a name-only
   collection (no stored Scryfall ids). Anything the batch can't resolve falls
   back to its data-src (the by-name endpoint), throttled. Images are
   loading="lazy", so off-screen cards load as you scroll. */
(function () {
  var imgs = [].slice.call(document.querySelectorAll('figure.mc[data-card] img[data-src]'));
  if (!imgs.length) return;

  var byName = {};                     // lowercased name -> {orig, imgs:[...]}
  imgs.forEach(function (img) {
    var fig = img.closest('[data-card]');
    var name = fig && fig.getAttribute('data-card');
    if (!name) return;
    var k = name.toLowerCase();
    if (!byName[k]) byName[k] = { orig: name, imgs: [] };
    byName[k].imgs.push(img);
  });

  var keys = Object.keys(byName), resolved = {};
  function chunk(a, n) { var r = []; for (var i = 0; i < a.length; i += n) r.push(a.slice(i, i + n)); return r; }
  function cdn(card) {
    var iu = card.image_uris || (card.card_faces && card.card_faces[0] && card.card_faces[0].image_uris);
    return iu && iu.normal;
  }

  var batches = chunk(keys, 75), pending = batches.length;
  // One retry per batch — a single failed POST used to dump every card onto the
  // rate-limited by-name fallback at once (the 429 cascade in docs/card-images.md).
  function runBatch(batch, attempt) {
    fetch('https://api.scryfall.com/cards/collection', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifiers: batch.map(function (k) { return { name: byName[k].orig }; }) })
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (j && j.data) j.data.forEach(function (card) {
          var url = cdn(card), k = (card.name || '').toLowerCase();
          if (url && byName[k]) { byName[k].imgs.forEach(function (i) { i.src = url; }); resolved[k] = true; }
        });
        if (!j && attempt < 1) { setTimeout(function () { runBatch(batch, attempt + 1); }, 1500); return; }
        if (--pending === 0) fallback();
      }).catch(function () {
        if (attempt < 1) { setTimeout(function () { runBatch(batch, attempt + 1); }, 1500); return; }
        if (--pending === 0) fallback();
      });
  }
  batches.forEach(function (batch) { runBatch(batch, 0); });

  // Fallback: cards the batch didn't resolve -> their data-src. 700ms stays under
  // Scryfall's ~2/s by-name limit (400ms was over it); a failed load clears src so
  // the card shows its name cleanly instead of a broken-image glyph.
  function fallback() {
    var rest = [];
    keys.forEach(function (k) {
      if (!resolved[k]) byName[k].imgs.forEach(function (i) { if (!i.getAttribute('src')) rest.push(i); });
    });
    if (!rest.length) return;
    var q = rest.slice(), timer = setInterval(function () {
      var i = q.shift();
      if (!i) { clearInterval(timer); return; }
      if (!i.getAttribute('src')) {
        i.onerror = function () { this.onerror = null; this.removeAttribute('src'); };
        i.src = i.getAttribute('data-src');
      }
    }, 700);
  }
})();
