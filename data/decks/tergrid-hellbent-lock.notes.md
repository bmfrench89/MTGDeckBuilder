# Tergrid — Hellbent Lock (option 3 of 3 · Bracket 4)

**Study copy — theory build, not from the collection.** Rebuilt 2026-10-11 as a Bracket 4 deck with no budget limit; the player buys the cards. Every card's text, commander legality and price comes from the deck-verify GitHub runner (run 38162140013). Field % = share of 12,851 Tergrid decks on EDHREC (snapshot 2026-10-11). **Prices are estimates** — Scryfall market price of each card's cheapest printing on 2026-10-11, not a quote.

## The commander (verified)

**Tergrid, God of Fright** — {3}{B}{B} — Legendary Creature — God

- Menace
- Whenever an opponent sacrifices a nontoken permanent or discards a permanent card, you may put that card from a graveyard onto the battlefield under your control.

**Tergrid's Lantern** (back face) — {3}{B} — Legendary Artifact

- {T}: Target player loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.
- {3}{B}: Untap Tergrid's Lantern.

## Why this is Bracket 4

15 Game Changers, counting Tergrid herself (Bracket 3 allows three): Tergrid, God of Fright, Orcish Bowmasters, Opposition Agent, Braids, Cabal Minion, Vampiric Tutor, Demonic Tutor, Imperial Seal, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Bolas's Citadel, The One Ring, Necropotence, Ancient Tomb. On top of that: 11 fast-mana pieces and 5 tutors. power.py rates it **Bracket 4 — Optimized (cEDH-leaning)** and adds that with this many Game Changers on this low a curve it is close to Bracket 5 (cEDH) if tuned for a competitive table. Play it at tables that agreed to Bracket 4.

## The plan: empty every hand, keep it empty, punish it

1. **Empty the hands early.** Grief (evoke), Unmask, Thoughtseize, Duress, Inquisition, Hymn, Mind Twist off fast mana, Dark Deal and Delirium Skeins, Memory Jar; Burglar Rat, Elderfang Disciple and Liliana's Specter on bodies; Tourach kicked (two at random, and it grows with every discard after).
2. **Keep them empty.** Necrogen Mists and Bottomless Pit (a discard every upkeep), Oppression (every spell costs a card), The Raven Man, Liliana of the Veil, Liliana, Waker of the Dead, Rankle; Mindslicer dying makes every player discard their hand.
3. **Punish the empty hand.** Waste Not (Zombies, mana or cards per discard), Megrim (2 damage) and Liliana's Caress (2 life) on every discard, Painful Quandary (5 life or a card per spell), Tinybones (each opponent with no cards loses 10), Torment of Hailfire.
4. **Play off the top, not from your hand.** Bolas's Citadel lets you cast from the top of your library, so your own symmetric discard costs you little; Necropotence and The One Ring refill you between locks.

## How it wins

- **Tinybones, Trinket Thief**: {4}{B}{B} — each opponent with no cards in hand loses 10 life.
- **Megrim + Liliana's Caress** turn every forced discard into 4 life lost; Waste Not turns the same discards into Zombies, mana and cards.
- **Tergrid's stolen board** — every permanent card they discard is yours.
- **Torment of Hailfire** when they have nothing left to discard.

## Pilot

- **Crack Memory Jar in your second main phase.** Every player draws seven, then discards their hand at the next end step — yours. Every card they discard is a Waste Not trigger, and every permanent card among them is a Tergrid steal. With Megrim and Liliana's Caress out, that is up to 28 life from each opponent (seven discards at 4 each).
- **Your locks are symmetric** (Necrogen Mists, Bottomless Pit, Oppression, Smallpox, Pox, Braids): lead with Bolas's Citadel or an empty hand of your own before you lock.
- **Opposition Agent and Bowmasters punish the outs** they try to dig for. Bowmasters also pings for every card Memory Jar, Dark Deal or Geier Reach Sanitarium makes them draw.

**Mulligan** hands with no discard and no tutor; this deck wins by acting first.

## Traps
- **Lightning Greaves is left out on purpose.** Shroud also blocks your Mithril Coat attach, Kaya's Ghostform, Feign Death and the other return spells.
- **Dauthi Voidwalker is left out on purpose.** It exiles every card that would go to an opponent's graveyard, and Tergrid returns cards from a graveyard — with Dauthi out she steals nothing.
- **Toxic Deluge kills her.** It is −X/−X, which indestructible does not stop. Cast it before she lands, or keep X at 4 or less.
- **Hexproof does not stop edicts or wraths; indestructible does not stop exile, −X/−X or an edict.** Kaya's Ghostform is the one piece that answers exile as well as dying.
- **When a return effect triggers, leave her where she went.** Kaya's Ghostform, Feign Death, Undying Evil and the rest return her from the graveyard (Ghostform also from exile). If you move her to the command zone instead, the trigger finds nothing. (That choice is a Commander rule, not card text — uncited here; rules.py can confirm it on your PC.)
- **Mana Vault and Grim Monolith don't untap in your untap step** (Monolith: {4} to untap). Mox Diamond needs a land card to discard; Chrome Mox must imprint a nonartifact, nonland card — imprint a black one or it can't make {B}.
- **Tergrid only takes nontoken permanents and permanent cards.** Sheoldred's Edict has a nontoken mode — use it. A discarded instant or sorcery gives her nothing.

## Numbers (computed 2026-10-11)

- **Field overlap:** 19/25 = 76% of Tergrid's top-25 nonland cards.
- **Roles (deckcore):** 30 lands · ramp 10 · draw 8 · removal 9 · wipes 1 · average MV 2.51 · resilience 3 protection · 4 recursion (counted from resilience_staples.csv).
- **Lands:** 30, and the app's Lands tile flags that as short — its template doesn't count fast mana. With 7 mana rocks and moxen (Sol Ring, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Arcane Signet, Fellwar Stone) this deck has 37 permanent mana sources, before Lotus Petal and the two rituals.
- **Goldfish (4,000 games, on the play):** Tergrid on the battlefield by turn 3 18%, turn 4 36%, turn 5 57%; mean turn 5.3. **Read these as a floor:** the simulator makes every mana rock produce from the turn after it resolves (a deliberate pessimism) and keeps only 2–5-land hands, while this deck's speed comes from 0- and 1-mana artifacts that tap the turn they land (Chrome Mox, Mox Diamond, Lotus Petal, Mana Vault). Real play is faster; by how much is not measured.
- **Cost estimate:** ~$2,972 for all 82 non-basic cards, Tergrid included (Swamps not counted). **To buy: ~$2,930** for the 70 cards the collection snapshot doesn't have — they are this deck's buy list. You own the other 12. Free now: Dark Ritual, Syphon Mind, Sol Ring, Arcane Signet, Megrim. Already sleeved in another deck: Snuff Out (yshtola-nights-blessed); Grim Tutor (yshtola-nights-blessed); Toxic Deluge (dina-essence-brewer, yshtola-nights-blessed); Feed the Swarm (dina-essence-brewer); Fellwar Stone (captain-america-team-leader, the-ur-dragon, yshtola-nights-blessed); Swiftfoot Boots (beorn-the-fierce); Bojuka Bog (dina-essence-brewer) — a second copy of those would add ~$38. Most expensive: Mox Diamond ~$1,109, Grim Monolith ~$478, Imperial Seal ~$165, Chrome Mox ~$153, Ancient Tomb ~$120, The One Ring ~$110, Mana Vault ~$92, Urborg, Tomb of Yawgmoth ~$56.

## Card roles (every nonland card is named here, so the optimizer leaves them alone)

- **Fast mana:** Sol Ring, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Lotus Petal, Dark Ritual, Cabal Ritual, Jet Medallion, Arcane Signet, Fellwar Stone
- **Tutors:** Demonic Tutor, Vampiric Tutor, Imperial Seal, Grim Tutor, Beseech the Mirror
- **Card advantage:** Necropotence, Bolas's Citadel, The One Ring, Syphon Mind, Geth's Grimoire, Braids, Arisen Nightmare
- **Empty their hands:** Grief, Thoughtseize, Duress, Inquisition of Kozilek, Unmask, Hymn to Tourach, Mind Twist, Dark Deal, Delirium Skeins, Memory Jar, Burglar Rat, Elderfang Disciple, Liliana's Specter, Tourach, Dread Cantor
- **Keep them empty:** The Raven Man, Necrogen Mists, Bottomless Pit, Oppression, Mindslicer, Liliana of the Veil, Liliana, Waker of the Dead, Rankle, Master of Pranks
- **Punish the empty hand:** Waste Not, Megrim, Liliana's Caress, Painful Quandary, Tinybones, Trinket Thief, Torment of Hailfire
- **Sacrifice and stax:** Smallpox, Pox, Braids, Cabal Minion, Sheoldred's Edict, Liliana's Triumph, Flare of Malice, Accursed Marauder
- **Keep Tergrid on the battlefield:** Mithril Coat, Swiftfoot Boots, Kaya's Ghostform, Feign Death, Undying Evil, Demonic Gifts
- **Removal and disruption:** Snuff Out, Deadly Rollick, Toxic Deluge, Feed the Swarm, Orcish Bowmasters, Opposition Agent
