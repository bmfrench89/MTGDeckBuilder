/* Watch tab — animated deck clips (scripts/assets/clips_player.js).
 *
 * Plays the storyboard clips.py validated (embedded as #wt-data) on a mock table:
 * each scene places the deck's cards in zones, and a card that persists between
 * scenes (same key) slides to its new place, which is what turns a list of
 * captions into something that reads like a clip. Narration is opt-in and uses
 * the browser's own speechSynthesis, so there are no audio files.
 *
 * Controls behave like a video's (docs/spec-watch-voice-and-controls.md Part A):
 * tap the picture to play/pause, ⏮ ▶/❚❚ ■ ⏭ under it, S stops, ←/→ step scenes.
 * The voice (Part B) is the best English voice the DEVICE has, ranked by
 * WT_SPEECH.rank — a pure function, unit-tested in Node — and the player can pick
 * another; the spoken text itself is built once in Python (clips.spoken).
 *
 * Card art is borrowed from the decklist's images, which card_images.html already
 * resolves in one batch — the player adds no Scryfall requests of its own unless a
 * card has no decklist image at all (one batch POST, then nothing). Until art
 * arrives, and in a sandbox where it never will, a card is drawn as a named frame.
 */
var WT_SPEECH = (function () {
  'use strict';
  // English first; within English, how natural the engine sounds; then the region.
  var REGION = ['en-us', 'en-gb', 'en-au', 'en-ca', 'en-ie', 'en-in'];
  var NOVELTY = /\b(albert|bad news|bahh|bells|boing|bubbles|cellos|deranged|good news|hysterical|jester|organ|superstar|trinoids|whisper|wobble|zarvox|junior|ralph|fred|kathy|princess|bruce|agnes|vicki)\b/i;
  function lang(v) { return String((v && v.lang) || '').replace('_', '-').toLowerCase(); }
  function isEnglish(v) { return lang(v).indexOf('en') === 0; }
  function quality(v) {
    var n = String((v && v.name) || '');
    if (/compact|espeak/i.test(n) || NOVELTY.test(n)) return -1;
    if (/natural|neural|online/i.test(n)) return 3;
    if (/premium|enhanced/i.test(n)) return 2;
    if (/google/i.test(n)) return 1;
    return 0;
  }
  function region(v) {
    var i = REGION.indexOf(lang(v));
    return i < 0 ? REGION.length : i;
  }
  /** The device's English voices, best first. Pure: takes getVoices()'s list. */
  function rank(voices) {
    return Array.prototype.slice.call(voices || []).filter(isEnglish).sort(function (a, b) {
      return (quality(b) - quality(a)) || (region(a) - region(b)) ||
        ((b['default'] ? 1 : 0) - (a['default'] ? 1 : 0)) ||
        String(a.name).localeCompare(String(b.name));
    });
  }
  var ABBR = /(?:^|\s)(?:dr|mr|mrs|ms|st|vs|etc|e\.g|i\.e)\.$/i;
  /** Text -> sentences, one utterance each: natural pauses between them, and no
   * single utterance long enough for Chrome to drop (~15 s). Keeps "Mana Vault."
   * and "{3}{B}{B}" whole, and does not break after "Dr." or an initial ("B.F.M."). */
  function sentences(text) {
    var t = String(text || '').replace(/\s+/g, ' ').trim(), out = [], start = 0;
    for (var i = 0; i < t.length; i++) {
      var ch = t.charAt(i);
      if ((ch === '.' || ch === '!' || ch === '?') && t.charAt(i + 1) === ' ') {
        var piece = t.slice(start, i + 1);
        var nxt = t.charAt(i + 2);
        if (ABBR.test(piece) || /(?:^|[\s.])[A-Z]\.$/.test(piece) || !/[A-Z0-9"\u201c(\[{]/.test(nxt)) continue;
        out.push(piece.trim());
        start = i + 2;
      }
    }
    if (start < t.length) out.push(t.slice(start).trim());
    // Very long sentences are split again at a comma or semicolon.
    var res = [];
    out.forEach(function (s) {
      while (s.length > 220) {
        var cut = Math.max(s.lastIndexOf(', ', 200), s.lastIndexOf('; ', 200));
        if (cut < 40) break;
        res.push(s.slice(0, cut + 1).trim());
        s = s.slice(cut + 2);
      }
      if (s) res.push(s);
    });
    return res.filter(function (s) { return s.length; });
  }
  return { rank: rank, sentences: sentences, quality: quality };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = WT_SPEECH;

(function () {
  'use strict';
  if (typeof document === 'undefined') return;
  var root = document.getElementById('wt-root');
  var dataEl = document.getElementById('wt-data');
  if (!root || !dataEl) return;
  var CLIPS, AUDIO_BASE = '';
  try {
    var DATA = JSON.parse(dataEl.textContent) || {};
    CLIPS = DATA.clips || [];
    AUDIO_BASE = DATA.audio || '';
  } catch (e) { return; }
  if (!CLIPS.length) return;
  root.classList.add('wt-js');

  var stage = root.querySelector('.wt-stage');
  var headEl = root.querySelector('.wt-head'), subEl = root.querySelector('.wt-sub');
  var playBtn = root.querySelector('.wt-play'), stopBtn = root.querySelector('.wt-stop');
  var prevBtn = root.querySelector('.wt-prev'), nextBtn = root.querySelector('.wt-next');
  var voiceBtn = root.querySelector('.wt-voice'), prog = root.querySelector('.wt-prog');
  var menuBtn = root.querySelector('.wt-vmenu'), menu = root.querySelector('.wt-voices');
  var vsel = root.querySelector('.wt-vsel'), vtry = root.querySelector('.wt-vtry');
  var timeEl = root.querySelector('.wt-time'), chipsEl = root.querySelector('.wt-chips');
  var over = root.querySelector('.wt-over'), overT = root.querySelector('.wt-overt');
  var badges = root.querySelector('.wt-badges'), flashEl = root.querySelector('.wt-flash');
  var ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5v14l12-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    on: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    off: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 9.5l5 5M21.5 9.5l-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
  };
  // Per-device memory, never required: storage can be blocked or throw.
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {} return null; }
  var bands = {
    theirs: root.querySelector('.wt-band-theirs'),
    mine: root.querySelector('.wt-band-mine'),
    grave: root.querySelector('.wt-band-grave')
  };
  var REDUCED = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var synth = window.speechSynthesis;
  var CAN_SPEAK = !!(synth && window.SpeechSynthesisUtterance);
  // Recorded narration (Part C): one <audio> element reused for every scene, the
  // next scene's take preloaded. Only on the app surface, which serves the files.
  var HAS_TAKES = !!AUDIO_BASE && CLIPS.some(function (c) {
    return c.scenes.some(function (s) { return s.audio; });
  });
  var audioEl = HAS_TAKES ? new Audio() : null, preEl = HAS_TAKES ? new Audio() : null;
  if (audioEl) { audioEl.preload = 'auto'; preEl.preload = 'auto'; }
  if (!CAN_SPEAK) menuBtn.hidden = true;
  if (!CAN_SPEAK && !HAS_TAKES) voiceBtn.hidden = true;

  var ci = 0, si = 0, elapsed = 0, playing = false, last = 0, raf = 0, atEnd = false;
  // Narration defaults ON once recordings exist (the Play tap is the permission
  // phones need); after that each device's own choice wins.
  var pref = store('wt-narration');
  var voiceOn = pref === null ? HAS_TAKES : (pref === '1' && (CAN_SPEAK || HAS_TAKES));
  var speaking = false, talkId = 0;
  var voices = [], voice = null;
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
  // Fallback only: clips.py sends every scene's `speak` line (clips.spoken) — the
  // same words a recorded narrator will say. A payload from before that field
  // existed still gets its symbols read as words here.
  function sayable(t) {
    var M = { W: 'white', U: 'blue', B: 'black', R: 'red', G: 'green', C: 'colorless', T: 'tap' };
    return t.replace(/\{([^}]+)\}/g, function (_, s) { return (M[s] || s) + ' '; })
      .replace(/−/g, 'minus ').replace(/[…·]/g, ', ').replace(/\s+/g, ' ').trim();
  }
  function loadVoices() {
    if (!CAN_SPEAK) return;
    var list = WT_SPEECH.rank(synth.getVoices());
    if (!list.length) {
      // Some engines fill the list late (voiceschanged re-runs this); until then
      // say so rather than show an empty picker.
      if (!vsel.options.length) {
        var o = document.createElement('option');
        o.textContent = 'No English voices found yet';
        vsel.appendChild(o);
      }
      vsel.disabled = vtry.disabled = true;
      return;
    }
    vsel.disabled = vtry.disabled = false;
    voices = list;
    var want = store('wt-voice-pick');
    voice = list.filter(function (v) { return v.voiceURI === want || v.name === want; })[0] || list[0];
    vsel.textContent = '';
    list.forEach(function (v, i) {
      var o = document.createElement('option');
      o.value = String(i);
      o.textContent = v.name + ' (' + v.lang + ')' + (i === 0 ? ' — best on this device' : '');
      if (v === voice) o.selected = true;
      vsel.appendChild(o);
    });
  }
  function talk(text, done) {
    var parts = WT_SPEECH.sentences(text), id = ++talkId, left = parts.length;
    if (!left) { if (done) done(); return; }
    parts.forEach(function (p) {
      var u = new SpeechSynthesisUtterance(p);
      if (voice) { u.voice = voice; u.lang = voice.lang; } else u.lang = 'en-US';
      u.rate = 1.0;
      u.onend = u.onerror = function () {
        if (id !== talkId) return;          // a newer line has taken over
        if (--left === 0 && done) done();
      };
      synth.speak(u);
    });
  }
  function takeUrl(sc) { return sc && sc.audio && AUDIO_BASE ? AUDIO_BASE + sc.audio.file : ''; }
  function preloadNext() {
    if (!preEl) return;
    var sc = CLIPS[ci].scenes[si + 1] || (CLIPS[ci + 1] && CLIPS[ci + 1].scenes[0]);
    var u = takeUrl(sc);
    if (u && preEl.getAttribute('src') !== u) preEl.setAttribute('src', u);
  }
  function speak(sc) {
    if (!voiceOn) return;
    var u = takeUrl(sc);
    if (u && audioEl) {
      if (CAN_SPEAK) { try { synth.cancel(); } catch (e) {} }
      speaking = true;
      if (audioEl.getAttribute('src') !== u) audioEl.setAttribute('src', u);
      try { audioEl.currentTime = 0; } catch (e) {}
      var id = ++talkId;
      audioEl.onended = audioEl.onerror = function () { if (id === talkId) speaking = false; };
      var pr = audioEl.play();
      if (pr && pr.catch) pr.catch(function () { if (id === talkId) speaking = false; });
      preloadNext();
      return;
    }
    if (!CAN_SPEAK) return;
    try { synth.cancel(); } catch (e) {}
    speaking = true;
    talk(sc.speak || sayable(sc.say || (sc.head + (sc.sub ? '. ' + sc.sub : ''))),
      function () { speaking = false; });
  }
  function hush() {
    speaking = false;
    talkId++;
    if (audioEl) { try { audioEl.pause(); } catch (e) {} }
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
  function setPlayIcon() {
    playBtn.innerHTML = playing ? ICON.pause : ICON.play;
    playBtn.setAttribute('aria-label', playing ? 'Pause' : 'Play');
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
    setPlayIcon();
    // Resume a paused take where it stopped; anything else starts the scene's line.
    var u = takeUrl(scene());
    if (voiceOn && u && audioEl && audioEl.getAttribute('src') === u && audioEl.currentTime > 0
        && !audioEl.ended && elapsed > 0) {
      speaking = true;
      var pr = audioEl.play();
      if (pr && pr.catch) pr.catch(function () { speaking = false; });
    } else {
      speak(scene());
    }
    mediaState();
    raf = requestAnimationFrame(tick);
  }
  function pause() {
    playing = false;
    cancelAnimationFrame(raf);
    speaking = false;
    talkId++;
    if (audioEl) { try { audioEl.pause(); } catch (e) {} }   // kept, so Play resumes it
    if (CAN_SPEAK) { try { synth.cancel(); } catch (e) {} }
    setPlayIcon();
    mediaState();
  }
  // Lock screen and headphone buttons — they only reach a page that is playing an
  // <audio> element, so this is wired only when the deck has recorded takes.
  function mediaState() {
    if (!HAS_TAKES || !('mediaSession' in navigator)) return;
    try {
      if (window.MediaMetadata) {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: CLIPS[ci].title, artist: document.title.split(' · ')[0] || 'Deck clips' });
      }
      navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
    } catch (e) {}
  }
  function seek(c, s) {
    var was = playing;
    pause();
    atEnd = false;
    over.hidden = true;
    if (c !== ci) loadClip(c);
    si = s;
    elapsed = 0;
    showScene(true);
    if (was) play();
  }
  // Stop: silence, back to scene 1 of THIS clip, and the big Play button again.
  function stop() {
    pause();
    atEnd = false;
    si = 0;
    elapsed = 0;
    showScene(false);
    over.querySelector('.wt-big').innerHTML = ICON.play;
    overT.textContent = 'Play · ' + CLIPS[ci].title;
    over.hidden = false;
  }
  function next() {
    if (si + 1 < CLIPS[ci].scenes.length) seek(ci, si + 1);
    else if (ci + 1 < CLIPS.length) seek(ci + 1, 0);
  }
  function prev() {
    seek(ci, si > 0 ? si - 1 : 0);        // on scene 1: restart the clip
  }
  function flash(kind) {
    if (!flashEl || REDUCED) return;
    flashEl.innerHTML = ICON[kind];
    flashEl.classList.remove('go');
    flashEl.getBoundingClientRect();
    flashEl.classList.add('go');
  }
  function setVoice(on) {
    voiceOn = on;
    store('wt-narration', on ? '1' : '0');
    voiceBtn.innerHTML = on ? ICON.on : ICON.off;
    voiceBtn.setAttribute('aria-label', on ? 'Narration on' : 'Narration off');
    voiceBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    voiceBtn.classList.toggle('on', on);
    if (on && playing) speak(scene()); else if (!on) hush();
  }

  /* ---------- controls ---------- */
  playBtn.addEventListener('click', function () { if (playing) pause(); else play(); });
  over.addEventListener('click', play);
  stopBtn.addEventListener('click', stop);
  nextBtn.addEventListener('click', next);
  prevBtn.addEventListener('click', prev);
  // Tap the picture: play/pause, with the icon flashed in the middle like a video.
  stage.addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('.wt-over')) return;
    if (playing) { pause(); flash('pause'); } else { play(); flash('play'); }
  });
  voiceBtn.addEventListener('click', function () { setVoice(!voiceOn); });
  menuBtn.addEventListener('click', function () {
    var open = menu.hidden;
    menu.hidden = !open;
    menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) loadVoices();
  });
  vsel.addEventListener('change', function () {
    voice = voices[Number(vsel.value)] || voice;
    if (voice) store('wt-voice-pick', voice.voiceURI || voice.name);
  });
  vtry.addEventListener('click', function () {
    if (!CAN_SPEAK) return;
    hush();
    talk('Sol Ring taps for two colorless mana.');
  });
  root.addEventListener('keydown', function (ev) {
    if (ev.target && /^(BUTTON|SELECT)$/.test(ev.target.tagName) && (ev.key === ' ' || ev.key === 'Enter')) return;
    if (ev.target && ev.target.tagName === 'SELECT') return;
    if (ev.key === 'k' || ev.key === ' ') { ev.preventDefault(); if (playing) pause(); else play(); }
    else if (ev.key === 's' || ev.key === 'S') { ev.preventDefault(); stop(); }
    else if (ev.key === 'ArrowRight') next();
    else if (ev.key === 'ArrowLeft') prev();
  });
  if (HAS_TAKES && 'mediaSession' in navigator) {
    var acts = { play: play, pause: pause, stop: function () { stop(); },
                 previoustrack: function () { prev(); }, nexttrack: function () { next(); } };
    Object.keys(acts).forEach(function (k) {
      try { navigator.mediaSession.setActionHandler(k, acts[k]); } catch (e) {}
    });
  }
  if (CAN_SPEAK) {
    loadVoices();
    if (synth.addEventListener) synth.addEventListener('voiceschanged', loadVoices);
    else synth.onvoiceschanged = loadVoices;
  }

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
  setPlayIcon();
  setVoice(voiceOn);
  overT.textContent = 'Play · ' + CLIPS.length + ' clips · ' +
    fmt(CLIPS.reduce(function (a, c) { return a + c.total; }, 0));
})();
