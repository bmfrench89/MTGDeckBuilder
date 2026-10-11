# Tergrid — Grave Pact Engine (option 2 of 3 · Bracket 4)

**Study copy — theory build, not from the collection.** Rebuilt 2026-10-11 as a Bracket 4 deck with no budget limit; the player buys the cards. Every card's text, commander legality and price comes from the deck-verify GitHub runner (run 38162140013). Field % = share of 12,851 Tergrid decks on EDHREC (snapshot 2026-10-11). **Prices are estimates** — Scryfall market price of each card's cheapest printing on 2026-10-11, not a quote.

## The commander (verified)

**Tergrid, God of Fright** — {3}{B}{B} — Legendary Creature — God

- Menace
- Whenever an opponent sacrifices a nontoken permanent or discards a permanent card, you may put that card from a graveyard onto the battlefield under your control.

**Tergrid's Lantern** (back face) — {3}{B} — Legendary Artifact

- {T}: Target player loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.
- {3}{B}: Untap Tergrid's Lantern.

## Why this is Bracket 4

15 Game Changers, counting Tergrid herself (Bracket 3 allows three): Tergrid, God of Fright, Orcish Bowmasters, Opposition Agent, Braids, Cabal Minion, Vampiric Tutor, Demonic Tutor, Imperial Seal, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Bolas's Citadel, The One Ring, Necropotence, Ancient Tomb. On top of that: 10 fast-mana pieces and 7 tutors, and a two-card infinite (Exquisite Blood + Sanguine Bond). power.py rates it **Bracket 4 — Optimized**. Play it at tables that agreed to Bracket 4.

## The plan: every death becomes a steal

1. **Turn every death into an edict.** Grave Pact (each other player) and Dictate of Erebos (flash; each opponent) — each time a creature you control dies, they each sacrifice a creature. Butcher of Malakir does it on a body; Sheoldred, Whispering One makes each opponent sacrifice a creature on their upkeep; Braids, Cabal Minion makes **each** player sacrifice an artifact, creature or land on their own upkeep. With Tergrid out, every one of those nontoken sacrifices is a creature you take.
2. **Free outlets, recurring fodder.** Phyrexian Altar, Ashnod's Altar, Viscera Seer, Carrion Feeder, Yawgmoth and Phyrexian Tower sacrifice on demand; Gravecrawler and Bloodghast come back from the graveyard; Bitterblossom and Ophiomancer make a new body every upkeep. Skullclamp, Village Rites, Midnight Reaper and Liliana, Dreadhorde General turn the deaths into cards.
3. **Fast mana and tutors** as in the other two builds: the same core lands Tergrid early, and the tutors find whichever engine piece is missing. Sidisi, Undead Vizier is a tutor on a Zombie body.

## How it wins

- **The infinite loop.** Gravecrawler can be cast from your graveyard while you control another Zombie: Carrion Feeder, Sidisi, Fleshbag or Accursed Marauder, Midnight Reaper, Gray Merchant, or a token from Liliana, Dreadhorde General's +1.
- **Loop with Phyrexian Altar:** sacrifice Gravecrawler for {B}, recast it for {B}, repeat.
- **Loop with Pitiless Plunderer and a free outlet** (Carrion Feeder, Viscera Seer): each death makes a Treasure, and the Treasure recasts Gravecrawler.
- **What each loop does:** Blood Artist and Zulaport Cutthroat drain; with Grave Pact or Dictate out each opponent also sacrifices a creature, and Tergrid takes every nontoken one.
- **Exquisite Blood + Sanguine Bond** — the two-card drain loop; any drain starts it.
- **Torment of Hailfire** and **Gray Merchant** close a long game.

## Pilot

- **Engine first, Tergrid second** is fine here: Grave Pact and the outlets work without her, and she turns their output into stolen creatures.
- **Count Zombies before you loop.** Gravecrawler needs a different Zombie on the battlefield while it is in the graveyard.
- **Keep a free outlet on the battlefield.** Sacrificing a creature in response to removal still triggers Grave Pact.

**Mulligan** hands without an engine piece, an outlet or a tutor; one fast-mana piece plus two lands and a tutor is a keep.

## Traps
- **Cruel Celebrant is out on purpose** — it is white-black ({W}{B}) and not legal under a mono-black commander.
- **Count your library before you loop.** Liliana, Dreadhorde General draws a card on every death and Midnight Reaper on every nontoken death, and neither draw is optional. With either out, the Gravecrawler loop is capped by the cards left in your library. Midnight Reaper also deals 1 damage to you per death.
- **Lightning Greaves is left out on purpose.** Shroud also blocks your Mithril Coat attach, Kaya's Ghostform, Feign Death and the other return spells.
- **Dauthi Voidwalker is left out on purpose.** It exiles every card that would go to an opponent's graveyard, and Tergrid returns cards from a graveyard — with Dauthi out she steals nothing.
- **Toxic Deluge kills her.** It is −X/−X, which indestructible does not stop. Cast it before she lands, or keep X at 4 or less.
- **Hexproof does not stop edicts or wraths; indestructible does not stop exile, −X/−X or an edict.** Kaya's Ghostform is the one piece that answers exile as well as dying.
- **When a return effect triggers, leave her where she went.** Kaya's Ghostform, Feign Death, Undying Evil and the rest return her from the graveyard (Ghostform also from exile). If you move her to the command zone instead, the trigger finds nothing. (That choice is a Commander rule, not card text — uncited here; rules.py can confirm it on your PC.)
- **Mana Vault and Grim Monolith don't untap in your untap step** (Monolith: {4} to untap). Mox Diamond needs a land card to discard; Chrome Mox must imprint a nonartifact, nonland card — imprint a black one or it can't make {B}.
- **Tergrid only takes nontoken permanents and permanent cards.** Sheoldred's Edict has a nontoken mode — use it. A discarded instant or sorcery gives her nothing.

## Numbers (computed 2026-10-11)

- **Field overlap:** 14/25 = 56% of Tergrid's top-25 nonland cards.
- **Roles (deckcore):** 30 lands · ramp 9 · draw 8 · removal 14 · wipes 1 · average MV 2.74 · resilience 3 protection · 4 recursion (counted from resilience_staples.csv).
- **Lands:** 30, and the app's Lands tile flags that as short — its template doesn't count fast mana. With 6 mana rocks and moxen (Sol Ring, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Arcane Signet) this deck has 36 permanent mana sources, before Lotus Petal and the two rituals.
- **Goldfish (4,000 games, on the play):** Tergrid on the battlefield by turn 3 20%, turn 4 41%, turn 5 59%; mean turn 5.2. **Read these as a floor:** the simulator makes every mana rock produce from the turn after it resolves (a deliberate pessimism) and keeps only 2–5-land hands, while this deck's speed comes from 0- and 1-mana artifacts that tap the turn they land (Chrome Mox, Mox Diamond, Lotus Petal, Mana Vault). Real play is faster; by how much is not measured.
- **Cost estimate:** ~$3,163 for all 82 non-basic cards, Tergrid included (Swamps not counted). **To buy: ~$3,109** for the 65 cards the collection snapshot doesn't have — they are this deck's buy list. You own the other 17. Free now: Archfiend of Depravity, Dark Ritual, Soul Shatter, Sol Ring, Arcane Signet. Already sleeved in another deck: Viscera Seer (dina-essence-brewer, yshtola-nights-blessed); Bloodghast (dina-essence-brewer); Blood Artist (dina-essence-brewer, yshtola-nights-blessed); Zulaport Cutthroat (dina-essence-brewer); Ophiomancer (dina-essence-brewer); Snuff Out (yshtola-nights-blessed); Grim Tutor (yshtola-nights-blessed); Toxic Deluge (dina-essence-brewer, yshtola-nights-blessed); Feed the Swarm (dina-essence-brewer); Skullclamp (cosmic-spider-man); Swiftfoot Boots (beorn-the-fierce); Bojuka Bog (dina-essence-brewer) — a second copy of those would add ~$49. Most expensive: Mox Diamond ~$1,109, Grim Monolith ~$478, Imperial Seal ~$165, Chrome Mox ~$153, Ancient Tomb ~$120, The One Ring ~$110, Mana Vault ~$92, Urborg, Tomb of Yawgmoth ~$56.

## Card roles (every nonland card is named here, so the optimizer leaves them alone)

- **Fast mana:** Sol Ring, Mana Vault, Grim Monolith, Chrome Mox, Mox Diamond, Lotus Petal, Dark Ritual, Cabal Ritual, Jet Medallion, Arcane Signet
- **Tutors:** Demonic Tutor, Vampiric Tutor, Imperial Seal, Grim Tutor, Diabolic Intent, Beseech the Mirror, Sidisi, Undead Vizier
- **Card advantage:** Necropotence, Bolas's Citadel, The One Ring, Skullclamp, Village Rites, Midnight Reaper, Braids, Arisen Nightmare
- **Every death becomes a steal:** Grave Pact, Dictate of Erebos, Butcher of Malakir, Braids, Cabal Minion, Sheoldred, Whispering One, Liliana, Dreadhorde General
- **Edicts:** Flare of Malice, Sheoldred's Edict, Liliana's Triumph, Soul Shatter, Innocent Blood, Plaguecrafter, Fleshbag Marauder, Accursed Marauder, Archfiend of Depravity, Smallpox, Rankle, Master of Pranks
- **Sacrifice outlets:** Phyrexian Altar, Ashnod's Altar, Viscera Seer, Carrion Feeder, Yawgmoth, Thran Physician
- **Fodder that comes back:** Gravecrawler, Bloodghast, Bitterblossom, Ophiomancer, Pitiless Plunderer
- **Drain and kill:** Blood Artist, Zulaport Cutthroat, Gray Merchant of Asphodel, Exquisite Blood, Sanguine Bond, Torment of Hailfire
- **Keep Tergrid on the battlefield:** Mithril Coat, Swiftfoot Boots, Kaya's Ghostform, Feign Death, Undying Evil, Demonic Gifts
- **Removal and disruption:** Snuff Out, Deadly Rollick, Toxic Deluge, Feed the Swarm, Orcish Bowmasters, Opposition Agent
