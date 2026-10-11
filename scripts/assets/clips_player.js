/* Watch tab — animated deck clips (scripts/assets/clips_player.js).
 *
 * Plays the storyboard clips.py validated (embedded as #wt-data) on a mock table:
 * each scene places the deck's cards in zones, and a card that persists between
 * scenes (same key) slides to its new place, which is what turns a list of
 * captions into something that reads like a clip. Narration is opt-in and uses
 * the browser's own speechSynthesis, so there are no audio files.
 *
 * Card art is borrowed from the decklist's images, which card_images.html already
 * resolves in one batch — the player adds no Scryfall requests of its own unless a
 * card has no decklist image at all (one batch POST, then nothing). Until art
 * arrives, and in a sandbox where it never will, a card is drawn as a named frame.
 */
(function () {
  'use strict';
  var root = document.getElementById('wt-root');
  var dataEl = document.getElementById('wt-data');
  if (!root || !dataEl) return;
  var CLIPS;
  try { CLIPS = (JSON.parse(dataEl.textContent) || {}).clips || []; } catch (e) { return; }
  if (!CLIPS.length) return;
  root.classList.add('wt-js');

  var stage = root.querySelector('.wt-stage');
  var headEl = root.querySelector('.wt-head'), subEl = root.querySelector('.wt-sub');
  var playBtn = root.querySelector('.wt-play'), restartBtn = root.querySelector('.wt-restart');
  var voiceBtn = root.querySelector('.wt-voice'), prog = root.querySelector('.wt-prog');
  var timeEl = root.querySelector('.wt-time'), chipsEl = root.querySelector('.wt-chips');
  var over = root.querySelector('.wt-over'), overT = root.querySelector('.wt-overt');
  var badges = root.querySelector('.wt-badges');
  var bands = {
    theirs: root.querySelector('.wt-band-theirs'),
    mine: root.querySelector('.wt-band-mine'),
    grave: root.querySelector('.wt-band-grave')
  };
  var REDUCED = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var synth = window.speechSynthesis;
  var CAN_SPEAK = !!(synth && window.SpeechSynthesisUtterance);
  if (!CAN_SPEAK) voiceBtn.hidden = true;

  var ci = 0, si = 0, elapsed = 0, playing = false, last = 0, raf = 0, atEnd = false;
  var voiceOn = false, speaking = false;
  var els = {};

  /* ---------- card art ---------- */
  var deckImgs = {}, art = {};
  Array.prototype.forEach.call(document.querySelectorAll('img[data-src][alt]'), function (im) {
    var a = im.getAttribute('alt');
    if (a && !deckImgs[a]) deckImgs[a] = im;
  });
  function urlFor(name) {
    if (art[name]) return art[name];
    var im = deckImgs[name], s = im && im.getAttribute('src');
    if (s) art[name] = s;
    return s || null;
  }
  function setArt(e, url) {
    if (e._img || !url) return;
    var img = new Image();
    img.alt = '';
    img.decoding = 'async';
    img.onload = function () { e.classList.add('has-img'); };
    img.onerror = function () { img.remove(); e._img = null; e._failed = true; };
    img.src = url;
    e.querySelector('.wt-face').appendChild(img);
    e._img = img;
  }
  function refreshArt() {
    Object.keys(els).forEach(function (k) {
      var e = els[k];
      if (e._name && !e._img && !e._failed) setArt(e, urlFor(e._name));
    });
  }
  // A card with no decklist image (a list-view dashboard) gets one batch lookup.
  function ownBatch() {
    var want = {};
    CLIPS.forEach(function (c) { c.scenes.forEach(function (s) { s.cards.forEach(function (cd) {
      if (cd.name && !deckImgs[cd.name] && !art[cd.name]) want[cd.name] = 1;
    }); }); });
    var names = Object.keys(want).slice(0, 75);
    if (!names.length || !window.fetch) return;
    fetch('https://api.scryfall.com/cards/collection', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifiers: names.map(function (n) { return { name: n }; }) })
    }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j || !j.data) return;
      j.data.forEach(function (c) {
        var iu = c.image_uris || (c.card_faces && c.card_faces[0] && c.card_faces[0].image_uris);
        if (!iu || !iu.normal) return;
        names.forEach(function (n) {
          if (c.name === n || c.name.split(' // ')[0] === n) art[n] = iu.normal;
        });
      });
      refreshArt();
    }).catch(function () {});
  }
  var polls = 0;
  var pollTimer = setInterval(function () {
    polls++;
    refreshArt();
    if (polls === 8) ownBatch();
    if (polls > 60) clearInterval(pollTimer);
  }, 500);

  /* ---------- cards ---------- */
  function typeClass(t) {
    t = (t || '').toLowerCase();
    var order = ['creature', 'planeswalker', 'instant', 'sorcery', 'artifact', 'enchantment', 'land'];
    for (var i = 0; i < order.length; i++) if (t.indexOf(order[i]) >= 0) return order[i];
    return '';
  }
  function makeCard(cd) {
    var e = document.createElement('div');
    var ty = cd.ph ? '' : typeClass(cd.type);
    e.className = 'wt-card' + (cd.ph ? ' wt-ph' : '') + (ty ? ' wt-ty-' + ty : '');
    var face = document.createElement('div');
    face.className = 'wt-face';
    var fr = document.createElement('div');
    fr.className = 'wt-frame';
    var n = document.createElement('b');
    n.className = 'wt-n';
    n.textContent = cd.ph || cd.name;
    fr.appendChild(n);
    if (!cd.ph && cd.cost) {
      var c = document.createElement('span');
      c.className = 'wt-c';
      c.textContent = cd.cost;
      fr.appendChild(c);
    }
    if (!cd.ph && cd.type) {
      var t = document.createElement('span');
      t.className = 'wt-t';
      t.textContent = cd.type;
      fr.appendChild(t);
    }
    face.appendChild(fr);
    e.appendChild(face);
    e._name = cd.name || null;
    e._label = n;
    stage.appendChild(e);
    if (cd.name) setArt(e, urlFor(cd.name));
    return e;
  }

  /* ---------- layout ---------- */
  var AR = 63 / 88;
  var LABEL = 20;   // the band label strip above a zone's cards (px)
  function rectsFor(W, H, used) {
    var pad = Math.max(8, W * 0.03);
    var left = used.grave ? W * 0.27 : pad;
    var right = used.stack ? W * 0.64 : W - pad;
    var r = {
      theirs: { x: left, y: Math.max(H * 0.06, LABEL + 4), w: right - left, h: H * 0.34 },
      mine: { x: left, y: H * 0.6, w: right - left, h: H * 0.35 },
      hero: { x: pad, y: H * 0.05, w: W - 2 * pad, h: H * 0.9 },
      stack: { x: W * 0.67, y: H * 0.2, w: W * 0.3, h: H * 0.6 },
      grave: { x: W * 0.03, y: H * 0.3, w: W * 0.21, h: H * 0.42 }
    };
    var top = used.theirs ? H * 0.44 : H * 0.06;
    var bot = used.mine ? H * 0.6 - LABEL - 6 : H * 0.94;
    if (bot - top < H * 0.3) { top = H * 0.06; bot = H * 0.94; }
    r.row = { x: left, y: top, w: right - left, h: bot - top };
    return r;
  }
  function placeGrid(n, rect, square) {
    var ar = square ? 1 : AR, best = null;
    for (var rows = 1; rows <= 3; rows++) {
      var cols = Math.ceil(n / rows);
      var gap = Math.max(6, Math.min(rect.w, rect.h) * 0.035);
      var h = Math.min((rect.h - (rows - 1) * gap) / rows, (rect.w - (cols - 1) * gap) / cols / ar);
      if (!best || h > best.h + 0.5) best = { rows: rows, cols: cols, h: h, gap: gap };
    }
    var out = [], slot = best.h * ar, w = best.h * AR;
    var gridH = best.rows * best.h + (best.rows - 1) * best.gap;
    for (var i = 0; i < n; i++) {
      var row = Math.floor(i / best.cols), col = i % best.cols;
      var inRow = Math.min(best.cols, n - row * best.cols);
      var rowW = inRow * slot + (inRow - 1) * best.gap;
      var x = rect.x + (rect.w - rowW) / 2 + col * (slot + best.gap) + (slot - w) / 2;
      var y = rect.y + (rect.h - gridH) / 2 + row * (best.h + best.gap);
      out.push({ x: x, y: y, w: w, h: best.h });
    }
    return out;
  }
  function setBand(b, rect, on) {
    if (!b) return;
    b.classList.toggle('on', !!on);
    if (!rect) return;
    b.style.left = (rect.x - 6) + 'px';
    b.style.top = (rect.y - LABEL) + 'px';
    b.style.width = (rect.w + 12) + 'px';
    b.style.height = (rect.h + LABEL + 6) + 'px';
  }
  function place(e, P, rot, op, enter, zone) {
    e.style.setProperty('--wt-fs', Math.max(9, P.h * 0.075).toFixed(1) + 'px');
    e.style.setProperty('--wt-fs-sm', Math.max(8, P.h * 0.058).toFixed(1) + 'px');
    e.style.zIndex = zone === 'stack' ? 6 : zone === 'hero' ? 5 : 2;
    var tf = 'translate(' + P.x.toFixed(1) + 'px,' + P.y.toFixed(1) + 'px) rotate(' + rot + 'deg)';
    if (enter && !REDUCED) {
      var dy = zone === 'theirs' ? -50 : zone === 'mine' ? 50 : 0, dx = zone === 'stack' ? 70 : 0;
      e.style.transition = 'none';
      e.style.width = P.w + 'px';
      e.style.height = P.h + 'px';
      e.style.opacity = '0';
      e.style.transform = 'translate(' + (P.x + dx).toFixed(1) + 'px,' + (P.y + dy).toFixed(1) +
        'px) rotate(' + rot + 'deg) scale(.86)';
      e.getBoundingClientRect();
      e.style.transition = '';
    }
    e.style.width = P.w + 'px';
    e.style.height = P.h + 'px';
    e.style.transform = tf;
    e.style.opacity = String(op);
  }
  function layout(scene, animate) {
    var R = stage.getBoundingClientRect(), W = R.width, H = R.height;
    if (!W || !H) return false;
    if (!animate) stage.classList.add('wt-instant');
    var used = {}, byZone = {};
    scene.cards.forEach(function (cd) {
      used[cd.zone] = true;
      (byZone[cd.zone] = byZone[cd.zone] || []).push(cd);
    });
    var rects = rectsFor(W, H, used), keep = {};
    Object.keys(byZone).forEach(function (z) {
      var list = byZone[z], pos;
      var tapped = list.some(function (cd) { return (cd.fx || []).indexOf('tap') >= 0; });
      if (z === 'grave') {
        var p = placeGrid(1, rects.grave)[0];
        pos = list.map(function (_, i) { return { x: p.x + i * 5, y: p.y + i * 5, w: p.w, h: p.h }; });
      } else {
        pos = placeGrid(list.length, rects[z], tapped);
      }
      list.forEach(function (cd, i) {
        var e = els[cd.key], fresh = !e;
        if (fresh) e = els[cd.key] = makeCard(cd);
        else if (cd.ph && e._label.textContent !== cd.ph) e._label.textContent = cd.ph;
        keep[cd.key] = true;
        var fx = cd.fx || [];
        e.classList.toggle('fx-glow', fx.indexOf('glow') >= 0);
        e.classList.toggle('fx-back', fx.indexOf('back') >= 0);
        var rot = (fx.indexOf('tap') >= 0 ? 90 : 0) + (z === 'stack' ? -4 : 0);
        place(e, pos[i], rot, fx.indexOf('dim') >= 0 ? 0.38 : 1, fresh && animate, z);
      });
    });
    Object.keys(els).forEach(function (k) {
      if (keep[k]) return;
      var e = els[k];
      delete els[k];
      if (!animate || REDUCED) { e.remove(); return; }
      e.style.opacity = '0';
      e.style.transform += ' scale(.9)';
      setTimeout(function () { e.remove(); }, 500);
    });
    setBand(bands.theirs, used.theirs && rects.theirs, used.theirs);
    setBand(bands.mine, used.mine && rects.mine, used.mine);
    setBand(bands.grave, used.grave && rects.grave, used.grave);
    if (!animate) {
      stage.getBoundingClientRect();
      requestAnimationFrame(function () { stage.classList.remove('wt-instant'); });
    }
    return true;
  }

  /* ---------- scenes ---------- */
  function scene() { return CLIPS[ci].scenes[si]; }
  function fmt(s) {
    s = Math.max(0, Math.round(s));
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }
  function renderBadges(sc) {
    badges.textContent = '';
    if (sc.turn) {
      var t = document.createElement('span');
      t.className = 'wt-badge';
      t.textContent = 'Turn ' + sc.turn;
      badges.appendChild(t);
    }
    if (sc.pool) {
      var p = document.createElement('span');
      p.className = 'wt-badge';
      p.appendChild(document.createTextNode('Mana'));
      sc.pool.split('').forEach(function (ch) {
        var i = document.createElement('i');
        i.className = 'wt-pip wt-pip-' + ch;
        i.textContent = ch;
        p.appendChild(i);
      });
      badges.appendChild(p);
    }
  }
  function sayable(t) {
    var M = { W: 'white', U: 'blue', B: 'black', R: 'red', G: 'green', C: 'colorless', T: 'tap' };
    return t.replace(/\{([^}]+)\}/g, function (_, s) { return (M[s] || s) + ' '; })
      .replace(/−/g, 'minus ').replace(/[…·]/g, ', ').replace(/\s+/g, ' ').trim();
  }
  function speak(sc) {
    if (!voiceOn || !CAN_SPEAK) return;
    try { synth.cancel(); } catch (e) {}
    var u = new SpeechSynthesisUtterance(sayable(sc.say || (sc.head + (sc.sub ? '. ' + sc.sub : ''))));
    u.lang = 'en-US';
    u.rate = 1.05;
    speaking = true;
    u.onend = u.onerror = function () { speaking = false; };
    synth.speak(u);
  }
  function hush() {
    speaking = false;
    if (CAN_SPEAK) { try { synth.cancel(); } catch (e) {} }
  }
  function showScene(animate) {
    var sc = scene();
    headEl.textContent = sc.head;
    subEl.textContent = sc.sub || '';
    renderBadges(sc);
    layout(sc, animate);
    markProgress();
    if (playing) speak(sc);
  }
  function markProgress() {
    var segs = prog.children, scs = CLIPS[ci].scenes, before = 0;
    for (var i = 0; i < segs.length; i++) {
      var p = i < si ? 100 : i > si ? 0 : Math.min(100, elapsed / (scs[i].dur * 10));
      segs[i].firstChild.style.setProperty('--p', p.toFixed(1) + '%');
      if (i === si) segs[i].setAttribute('aria-current', 'step');
      else segs[i].removeAttribute('aria-current');
      if (i < si) before += scs[i].dur;
    }
    timeEl.textContent = fmt(Math.min(before + elapsed / 1000, CLIPS[ci].total)) + ' / ' +
      fmt(CLIPS[ci].total);
  }
  function buildProgress() {
    prog.textContent = '';
    CLIPS[ci].scenes.forEach(function (sc, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'wt-seg';
      b.style.flexGrow = String(sc.dur);
      b.setAttribute('aria-label', 'Scene ' + (i + 1) + ': ' + sc.head);
      b.appendChild(document.createElement('i'));
      b.addEventListener('click', function () { seek(ci, i); });
      prog.appendChild(b);
    });
  }
  function markChips() {
    Array.prototype.forEach.call(chipsEl.children, function (b, i) {
      b.setAttribute('aria-pressed', i === ci ? 'true' : 'false');
      if (i === ci && chipsEl.scrollWidth > chipsEl.clientWidth) {
        chipsEl.scrollLeft = Math.max(0, b.offsetLeft - chipsEl.offsetLeft - 8);
      }
    });
  }
  function buildChips() {
    CLIPS.forEach(function (c, i) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'wt-chip';
      b.appendChild(document.createTextNode((i + 1) + ' · ' + c.title));
      var l = document.createElement('span');
      l.className = 'wt-len';
      l.textContent = fmt(c.total);
      b.appendChild(l);
      b.addEventListener('click', function () { seek(i, 0); play(); });
      chipsEl.appendChild(b);
    });
    markChips();
  }
  function clearStage() {
    Object.keys(els).forEach(function (k) { els[k].remove(); });
    els = {};
  }
  function loadClip(c) {
    ci = c;
    si = 0;
    elapsed = 0;
    clearStage();
    buildProgress();
    markChips();
  }

  /* ---------- clock ---------- */
  function tick(now) {
    if (!playing) return;
    elapsed += last ? Math.min(now - last, 250) : 0;
    last = now;
    var dur = scene().dur * 1000;
    // With narration on, a scene waits for its sentence to finish (up to 8s more):
    // cutting the voice off mid-word is worse than a slightly longer scene.
    if (elapsed >= dur && !(voiceOn && speaking && elapsed < dur + 8000)) {
      advance();
    } else {
      markProgress();
    }
    if (playing) raf = requestAnimationFrame(tick);
  }
  function advance() {
    elapsed = 0;
    if (si + 1 < CLIPS[ci].scenes.length) {
      si++;
      showScene(true);
    } else if (ci + 1 < CLIPS.length) {
      loadClip(ci + 1);
      showScene(true);
    } else {
      pause();
      atEnd = true;
      markProgress();
      overT.textContent = 'Watch again';
      over.querySelector('.wt-big').textContent = '↺';
      over.hidden = false;
    }
  }
  function play() {
    if (playing) return;
    if (atEnd) {
      atEnd = false;
      loadClip(0);
      showScene(false);
    }
    playing = true;
    last = 0;
    over.hidden = true;
    playBtn.textContent = 'Pause';
    speak(scene());
    raf = requestAnimationFrame(tick);
  }
  function pause() {
    playing = false;
    cancelAnimationFrame(raf);
    hush();
    playBtn.textContent = 'Play';
  }
  function seek(c, s) {
    var was = playing;
    pause();
    atEnd = false;
    if (c !== ci) loadClip(c);
    si = s;
    elapsed = 0;
    showScene(true);
    if (was) play();
  }

  /* ---------- controls ---------- */
  playBtn.addEventListener('click', function () { if (playing) pause(); else play(); });
  over.addEventListener('click', play);
  restartBtn.addEventListener('click', function () { seek(ci, 0); play(); });
  voiceBtn.addEventListener('click', function () {
    voiceOn = !voiceOn;
    voiceBtn.classList.toggle('on', voiceOn);
    voiceBtn.textContent = voiceOn ? 'Voice on' : 'Voice off';
    if (voiceOn && playing) speak(scene()); else hush();
  });
  root.addEventListener('keydown', function (ev) {
    if (ev.target && ev.target.tagName === 'BUTTON' && (ev.key === ' ' || ev.key === 'Enter')) return;
    if (ev.key === 'k' || ev.key === ' ') { ev.preventDefault(); if (playing) pause(); else play(); }
    else if (ev.key === 'ArrowRight' && si + 1 < CLIPS[ci].scenes.length) seek(ci, si + 1);
    else if (ev.key === 'ArrowLeft' && si > 0) seek(ci, si - 1);
  });

  // Never play to a hidden tab or a backgrounded page.
  document.addEventListener('visibilitychange', function () { if (document.hidden) pause(); });
  Array.prototype.forEach.call(document.querySelectorAll('.tabinput'), function (inp) {
    inp.addEventListener('change', function () {
      if (!stage.getClientRects().length) pause();
      else layout(scene(), false);
    });
  });
  var resizeT = 0;
  function relayout() {
    clearTimeout(resizeT);
    resizeT = setTimeout(function () { layout(scene(), false); }, 100);
  }
  if (window.ResizeObserver) new ResizeObserver(relayout).observe(stage);
  else window.addEventListener('resize', relayout);

  /* ---------- start ---------- */
  buildChips();
  buildProgress();
  showScene(false);
  overT.textContent = 'Play · ' + CLIPS.length + ' clips · ' +
    fmt(CLIPS.reduce(function (a, c) { return a + c.total; }, 0));
})();
