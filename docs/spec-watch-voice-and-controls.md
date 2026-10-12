# Spec — Watch tab: video-style controls and a natural narrator

**Status:** ◐ Parts A and B shipped 2026-10-12 — `scripts/assets/clips_player.{js,css}`
(control bar ⏮ ▶/❚❚ ■ ⏭ under the picture, tap-to-pause with a flashed icon, Stop, S key,
narration choice remembered per device, `WT_SPEECH.rank` / `.sentences` exported for Node
tests, the voice menu with "Hear it" and the device tips), `build_dashboard.clips_html`,
`scripts/clips.py` (`spoken()` builds every scene's `speak` line; `pronunciations.csv`
starts empty) · tests in `tests/test_clips.py`. Part C (recorded narration) waits on the
audition run (§5 step 2); Media Session lands with it. Phone layout as shipped: the scene
bar and the voice-menu button share the first line, ⏮ ▶ ■ ⏭ and 🔊 the second, so every
target stays 44 px on a 344 px Fold cover screen.

**Player ask (2026-10-12):** "Can the voice of the video sound less robotic and can we
add play/stop buttons to the videos? Or is that too difficult."
**Decision (player, 2026-10-12):** free only. Recorded narration from a free,
open-source voice model, with no paid voice service and no API key.

Neither is difficult. The controls are a small change to the player. The voice comes in
two steps: pick a better voice from the device now, then record narration later.

---

## 1. What's there today (measured 2026-10-12)

**Controls.** Before the first play there is a big ▶ over the picture. After that, the
controls sit in a row *under the captions*: a `Play`/`Pause` word button, ↺ (restart),
the scene bar, the clock and `Voice off`/`Voice on`. The keyboard has Space/K and ←/→.
Measured on a 344×882 Fold cover screen, a 390×844 phone and a 412×915 phone:

- The row sits about 120 px below the picture, with the captions in between.
- **Tapping the picture while it plays does nothing.** The button still read "Pause"
  after a scripted tap on the picture.
- **There is no Stop.** Pause leaves the clip mid-scene. ↺ restarts the clip and plays
  it straight away.

The buttons exist, but they don't act like a video's. "Add play/stop buttons" is a fair
reading of what the player sees.

**Voice.** `speak()` makes one `SpeechSynthesisUtterance` per scene with `lang='en-US'`
and `rate=1.05`. It **never chooses a voice**, so the device's default voice reads the
text. On many devices that default is the plainest voice installed, such as a legacy
desktop voice or the phone maker's own engine, and 1.05× speed rushes it. There are no
audio files.

## 2. Part A: controls that behave like a video (small, ships first)

1. **Tap the picture to play or pause.** A ▶ or ❚❚ icon flashes in the centre and fades
   out over about 600 ms. The before-play overlay stays as it is.
2. **Fix the control bar to the bottom edge of the picture.** Move it above the captions
   so the picture and its buttons form one block:
   `⏮ previous scene · ▶/❚❚ · ■ stop · ⏭ next scene · scene bar · clock · 🔊 narration`.
   - Use icon buttons with 44 px targets.
   - Give each an `aria-label` ("Play", "Pause", "Stop", "Previous scene", "Next scene",
     "Narration on" / "Narration off").
   - On phones the scene bar keeps its own line, as it does today.
3. **Stop** pauses, silences the narration and rewinds to scene 1 of the current clip.
   The big ▶ shows again, labelled "Play · <clip title>". ↺ is retired: Stop then Play
   does the same job.
4. **⏮ and ⏭ step through scenes.** ⏭ on the last scene moves to the next clip. ⏮ on
   scene 1 restarts the clip.
5. **Keyboard:** Space/K play and pause, ←/→ change scene, and the new **S** key stops.
6. **Narration on/off is remembered per device.** Read and write `localStorage` inside
   try/catch, so the page still works when storage is blocked.
7. **Lock-screen and headphone buttons.** Register `navigator.mediaSession` handlers for
   play, pause, stop, previoustrack and nexttrack, with the clip title as metadata. This
   only works while an `<audio>` element is playing, so it lands with Part C.

Unchanged: the storyboard gate (`clips.py`), the no-script outline and the print view.

**Acceptance**

- On a phone viewport, a scripted tap on the picture pauses a playing clip and a second
  tap resumes it.
- Stop rewinds to scene 1, cancels any speech in progress and shows the overlay. Play
  then starts from scene 1.
- At 344×882, 390×844 and 412×915, the whole picture and the control bar fit on screen
  together, with no scrolling between them.
- `webapp/uat/upgrade.js` passes. `webapp/uat/sweep.js` runs and its screenshots are
  read (the CLAUDE.md rule for UI changes).
- `test_clips` checks that the new buttons and their labels are in the markup and that
  the CSS braces still balance.

## 3. Part B: a better voice from the device (small; also the permanent fallback)

1. **Choose a voice instead of taking the default.** `speechSynthesis.getVoices()`
   fills in asynchronously, so also listen for `voiceschanged`. Rank the voices like this:
   1. English first: en-US, then en-GB, AU, CA, IE and IN.
   2. Then by quality words in the name:
      - `Natural`, `Neural` or `Online` (the neural voices in Edge and Windows);
      - `Premium` or `Enhanced` (Apple voices the user has downloaded);
      - `Google` (Chrome's server voices).
   3. Rank `Compact`, `eSpeak` and the macOS novelty voices last.
2. **Add a voice menu to the player.**
   - It lists the device's English voices, best first.
   - Each voice has a sample about 2 seconds long.
   - The choice is remembered per device, so each person's phone keeps its own pick.
3. **Pacing.**
   - Speak at rate 1.0 instead of 1.05.
   - Queue one utterance per sentence. That gives natural pauses between sentences and
     avoids Chrome dropping long utterances, which it does after about 15 seconds.
4. **Build the spoken text in Python, once.**
   - `clips.py` gives each scene a `speak` string. Today `sayable()` builds it in the
     player's JS.
   - It spells symbols the way a player says them:
     - `{B}` becomes "black";
     - `{3}{B}{B}` becomes "three, black, black";
     - "MV" becomes "mana value";
     - "ETB" becomes "enters".
   - It applies a pronunciation list, `data/reference/pronunciations.csv`
     (`Word,Say as`), for names that voice engines get wrong.
   - The list starts **empty**. An entry is added only when the player hears a name said
     wrong; no pronunciations are guessed.
   - Part C records exactly the same text, so both voices say the same words.
5. **Device tip, shown in the voice menu (no code).**
   - Android: Settings → Text-to-speech → set *Speech Services by Google* as the
     preferred engine and download its high-quality English voice.
   - iPhone: Settings → Accessibility → Spoken Content → Voices → English → download an
     *Enhanced* or *Premium* voice.
   - The menu lists the new voice once it's installed.

**The limit:** Part B can only use voices the device already has. A phone with only a
basic engine will still sound basic. Part C fixes that.

**Acceptance**

- The ranking is a pure function, unit-testable in Node against a fixture voice list.
  For example, `Microsoft Aria Online (Natural)` must beat `Microsoft David Desktop`, and
  `Samantha (Enhanced)` must beat `Samantha`.
- The sentence splitter keeps "Mana Vault." and "{3}{B}{B}" whole.
- `speak` normalisation is tested in Python: mana symbols, the pronunciation list, and
  `[[Card|shown]]` references becoming the shown text.

## 4. Part C: recorded narration, free

```
<stem>.clips.json changes (push to a session branch)
  └─ narrate.yml on a GitHub runner (the repo's network arm)
       ├─ clips.py --narration-plan → scenes whose spoken text has no recording yet
       ├─ synthesize with a free, open-source voice model (on the runner's CPU)
       ├─ ffmpeg → MP3, mono, 64 kbps
       ├─ write data/narration/<stem>/<hash>.mp3 and data/narration/<stem>.json (manifest)
       └─ commit back to the branch (the deck-verify.yml pattern)
merge → hosted app syncs → /narration/<stem>/<hash>.mp3 served behind the login
player: scene has a recording → play it · no recording → device voice (Part B)
```

**Engine: the player picks it by ear, not the spec.**

- Two candidates, both free and open-source, both run on a CPU runner:
  - **Kokoro-82M** (Apache-2.0): a small model with some of the most natural open
    voices.
  - **Piper**: lighter and faster, a step less natural. Each Piper voice has its own
    license, so check it.
- A one-off **audition run** records the same three Iron Fortress scenes in about six
  voices, for example:
  - Kokoro `af_heart`, `af_bella`, `am_michael`, `bm_george`;
  - Piper `en_US-ryan-high`, `en_GB-alan-medium`.
- The player listens on their phone and picks one.
- The pick goes in `data/reference/narration.json` (`engine`, `voice`, `speed`).
- A deck can override it with a top-level `"voice"` in its clips file.
- The sandbox can't download these models and the runner can, so the audition run is
  also the spike that confirms the model facts above.

**Content-addressed audio.**

- Each file is named with the first 16 hex characters of sha256 over five values: the
  `speak` text, the engine, the model version, the voice and the speed.
- Changing a caption re-records only that scene.
- Identical lines share one file.
- The same commit prunes a deck's unreferenced files.
- The manifest maps each hash to `{file, ms}`.

**Timing follows the narrator.**

- A scene with a recording runs for `max(dur, recording + 0.4 s)`, whether narration
  is on or off. The clip length doesn't change with the toggle, and the voice is never
  cut off.
- `clips.py` computes these lengths, so the scene bar and the clip times stay accurate.

**Stale recordings are flagged, never hidden.**

- A scene whose text changed since it was recorded plays with the device voice.
- The tab says "N scenes use your device's voice until they're re-recorded".
- `clips.py --check` reports a missing recording as a **warning, not a failure**. The
  runner fixes it on the next push, and a failure here would block unrelated deck edits
  in CI.

**Playback.**

- One `<audio>` element is reused for every scene. The Play tap unlocks it, because
  phones only allow sound after a tap. The next scene's file is preloaded.
- Pause, Stop and seeking all control the audio.
- Media Session handles the lock screen and headphones (Part A, item 7).
- Narration defaults to **on** once recordings exist. The tap on the overlay's Play
  button counts as permission. After that, each device's own choice wins.

**Serving.**

- A Flask route `/narration/<stem>/<file>` serves only files listed in that deck's
  manifest, using `send_from_directory` and `Cache-Control: public,
  max-age=31536000, immutable`. The file name is the content hash, so it never changes.
- The route sits behind the existing login.
- **The service worker must not handle `/narration/`.** Today every non-static GET goes
  through `respondWith(fetch(...))`. Audio uses Range requests, and putting a service
  worker in that path is a known way to break playback on iPhone. `sw.js` gets an early
  `return` for `/narration/`, like the one it already has for non-GET requests.
  `tests/test_pwa.py` pins that.

**Size.**

- About 3:20 of speech per deck is roughly 1.6 MB at 64 kbps mono.
- The PythonAnywhere free disk is about 512 MB. Ten decks with clips would use about
  16 MB.
- The repo grows only by the scenes that change, about 50 KB each.

**Standalone dashboards** (the CLI's one-file HTML and the app's "export HTML") can't
link to files, so they use the device voice from Part B. An `--embed-narration` flag
(base64, about 2 MB extra) is out of scope for v1.

**`scripts/` stays stdlib-only.**

- The planner and manifest code live in `scripts/clips.py`, or in a new stdlib-only
  `scripts/narration.py`.
- The synthesis step needs the model runtime, a third-party package. It lives outside
  `scripts/` (for example `.github/narrate/synthesize.py`) and only ever runs on the
  runner.
- `tool-contract.md` gets rows for the new script and workflow, otherwise
  `test_tool_contract` fails.

**Acceptance**

- On the hosted app, on a phone, Iron Fortress's four clips play in the chosen recorded
  voice. Turning narration off keeps the same timing.
- Edit one caption and push: the runner records only that scene. Until it has, that
  scene uses the device voice and the tab says so.
- `/narration/...` returns 200 or 206 with immutable caching, refuses names not in the
  manifest (no path traversal), and is never handled by the service worker.
- `clips.py --check` stays green while a recording is missing.
- Tests cover:
  - hash stability: the same inputs give the same name; changing any one input gives a
    new name;
  - manifest pruning;
  - the scene-length maths.

## 5. Order of work

1. **PR 1:** Part A and Part B together. Player and `clips.py` only, no new
   dependencies, with UAT.
2. **Audition run:** the player picks a voice.
3. **PR 2:** Part C.

## 6. Open questions

- Which voice? The audition decides.
- Should narration default to on once recordings exist? Proposed yes; each device's own
  choice overrides it.
