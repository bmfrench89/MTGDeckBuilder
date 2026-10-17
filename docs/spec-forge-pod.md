# The household pod: every deck plays every other (2026-10-17)

**Status:** v1 shipped. `scripts/forge_pod.py` runs on the player's PC, and the app's
Matchups page (`/matchups`) shows the newest run.
**Asked for by the player:** "Are you able to create a system where all of our decks can
play against each other in simulations?" The household's decks include some the player
doesn't pilot, so the matchups between them are the point.
**Planned as:** docs/spec-deck-uat.md, Next item 6, "Forge household pod".

## What it is
[Forge](https://github.com/Card-Forge/forge) is an open-source MTG rules engine with an AI
pilot. Version 2.0.15 (2026-09-28) has a headless `sim` mode, and `-f Commander` seats
every deck at 40 life with its commander. `forge_pod.py` drives it:

1. **Export.** Each deck becomes a `.dck` file (`[metadata] Name=<stem>`, `[Commander]`,
   `[Main]`).
   - Forge names a split card "A // B" and every other two-faced card by its front face, so
     the exporter writes what Forge's own card scripts call the card.
   - Names fold case and accents, as Forge's lookup does.
2. **Support check.** Every card is looked up in Forge's card scripts
   (`res/cardsfolder/cardsfolder.zip`, 34,010 files in 2.0.15).
   - **Forge doesn't refuse an unknown card.** It quietly removes it at game start, so the
     deck plays short. The report lists those cards per deck.
   - **Cards Forge marks `AI:RemoveDeck:All`** (its own AI plays them badly) stay in, and
     the report counts them.
   - **First check (all 18 decks):** every card is supported. Kami has 9 AI-flagged cards,
     Vaevictis 8, Y'shtola 7.
3. **Schedule.** Four-seat pods. Each deck plays the same number of games, within one, and
   seats rotate so each deck sits first about equally often.
4. **One game per JVM** (`-n 1`):
   - Forge's AI always chooses to play first.
   - In a multi-game run, each later game starts with a seat that didn't win the last one.
   - A timed-out game's thread can keep running inside the JVM.
5. **Parse every game.** Forge exits 0 even when a deck fails to load, so the output is the
   only truth. A game counts as **abandoned**, never a win, when any of these happens:
   - it prints "Stopping slow match as draw" (a timeout);
   - two or more seats report "has won", which Forge does for every survivor of a timeout;
   - it ends in a draw, a deck fails to load, there is no outcome, or the JVM passes its
     wall-clock limit.
6. **Aggregate.**
   - Win share counts finished games only. Chance in a 4-seat pod is 25%.
   - Head-to-head counts each pair's wins among the games they shared.
   - Forge's "Turn N" counts every player's turn and halves it, so in a 4-seat pod it is
     about twice the number of rounds.

## What it is not
**Forge's AI is a rough pilot.** It plays aggro and midrange fairly, and combo and control
badly (the deck-UAT research). Read the results like this:
- A win share is a matchup sketch, never a verdict.
- A deck built around a loop the AI doesn't see, such as Bartolomé's 600 combos or the
  Avacyn returns, will under-perform its real strength.
- A deck that beats down will over-perform.
- Small samples are noisy: with 16 games a deck's share is ±11 points at one standard
  error.

## Privacy
Forge's crash reporter falls back to the developers' Sentry server when no DSN is
configured. It honours external configuration, so every run passes
`-Dsentry.dsn=https://off@127.0.0.1/0` and reports go nowhere. The decks are already in
this private repo.

Forge also writes its own preferences and logs to the user's Forge folder, as it would
for anyone running it.

## Running it
```bash
python scripts/forge_pod.py --install                  # once: download + unpack Forge 2.0.15
python scripts/forge_pod.py --check                    # export + support report, no games
python scripts/forge_pod.py --games-per-deck 16 --workers 2 --seed 17
python scripts/forge_pod.py --report data/reference/pod/<date>.json
```
- **Where Forge lives:** `--install` unpacks it into `data/cache/forge/2.0.15/`, which is
  gitignored, about 300 MB. Java 17+ is required; the PC has Temurin 21.
- **Speed:** a 4-seat game takes about 30-60 s.
- **Memory:** each worker is a 2 GB-heap JVM, so set `--workers` by free memory, not cores.
- **Results:** `data/reference/pod/<date>.json`, committed. The app reads the newest one.
- **A stopped run keeps its games.** Each game is saved to `<results>.part` as it ends.
  Run the same command with `--resume` to play only the rest. The schedule and each
  game's seed come from `--seed`, so the resumed run plays the same pods an unbroken one
  would have.

## First run (2026-10-17)
All 18 decks: the 12 sleeved decks and 6 Lab decks. 72 games at `--games-per-deck 16 --seed 17`,
taking 56 minutes with 2 workers. Results: `data/reference/pod/2026-10-17.json`.
- **Harness checks:**
  - **Finished games:** 71 of 72. The one abandoned game hit Forge's 10-minute cap and
    named all four survivors winners; it was correctly left unscored.
  - **No seat bias:** wins by seat were 17 / 18 / 19 / 17, so rotating the seats cancels
    the AI's always-first choice.
  - **Game length:** Forge's turn 15-32 (median 23), which is each player's turn 8-16.
  - **How decks lost:** 208 times to life total, 4 to commander damage, 1 to an empty library.
- **The pilot shows, as predicted:**
  - Giada, the Angel beatdown deck, won 11 of 16.
  - Bartolomé's combo deck won 2 of 16.
  - Forge's script for Tom, Bert, and William gives its "{1}, sacrifice another creature:
    draw cards equal to its power" ability no AI logic. In a logged game the AI never used
    it (it used Skullclamp instead), and the deck won 1 of 16. Vaevictis's attack trigger
    has its own AI logic (`AILogic$ SacOneEach`), and that deck won 4 of 15.
- **Standings,** win share against 25% chance:

  | Win share | Decks |
  |---|---|
  | 69% | Giada |
  | 50% | Eriette |
  | 40% | Ur-Dragon |
  | 31% | Beorn, Y'shtola |
  | 27% | Vaevictis |
  | 25% | Kami, Mister Fantastic, Smaug, Tinybones |
  | 19% | Ur-Sphinx, Tinybones B4 |
  | 12-13% | Witherbloom, Bartolomé, Captain America, Dina |
  | 6-7% | Thorin, Tom, Bert, and William |

  With 16 games a deck, only Giada is clearly above chance (11 of 16 happens 0.03% of
  the time at 25%). Eriette is likely above (2.7%). Nothing is clearly below: Tom, Bert,
  and William and Thorin come closest (6% and 8%). The middle of the list is noise.

## Next (not built)
- **A runner workflow.** Private-repo GitHub runners are 2 vCPU / 8 GB, so 1-2 JVMs; fine
  for a weekly 40-game refresh.
- **Pinned matchups** (one group of decks against another) and 1v1 duels (`-f Commander` with two
  decks).
- **Merging runs** into one larger sample.
