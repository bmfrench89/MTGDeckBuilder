# Tergrid — Iron Fortress (option 1 of 3 · Bracket 4)

**Study copy — theory build, not from the collection.** Rebuilt 2026-10-11 as a Bracket 4 deck, then re-tuned the same day to a $100-per-card cap (the six cards over it were Mox Diamond, Grim Monolith, Imperial Seal, Chrome Mox, Ancient Tomb and The One Ring); the player buys the cards. Every card's text, commander legality and price comes from the deck-verify GitHub runner (run 38184868187). Field % = share of 12,851 Tergrid decks on EDHREC (snapshot 2026-10-11). **Prices are estimates** — Scryfall market price of each card's cheapest printing on 2026-10-11, not a quote.

## The commander (verified)

**Tergrid, God of Fright** — {3}{B}{B} — Legendary Creature — God

- Menace
- Whenever an opponent sacrifices a nontoken permanent or discards a permanent card, you may put that card from a graveyard onto the battlefield under your control.

**Tergrid's Lantern** (back face) — {3}{B} — Legendary Artifact

- {T}: Target player loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.
- {3}{B}: Untap Tergrid's Lantern.

## Why this is Bracket 4

9 Game Changers, counting Tergrid herself (Bracket 3 allows three): Tergrid, God of Fright, Orcish Bowmasters, Opposition Agent, Braids, Cabal Minion, Vampiric Tutor, Demonic Tutor, Mana Vault, Bolas's Citadel, Necropotence. On top of that: 10 fast-mana pieces and 6 tutors, and a two-card infinite (Exquisite Blood + Vito, Thorn of the Dusk Rose). power.py rates it **Bracket 4 — Optimized (cEDH-leaning)** and adds that with this many Game Changers on this low a curve it is close to Bracket 5 (cEDH) if tuned for a competitive table. Play it at tables that agreed to Bracket 4.

## The plan: Tergrid early, and she stays

1. **Land her early.** Sol Ring, Mana Vault, Lotus Petal, Dark Ritual and Cabal Ritual are real acceleration, not ramp; Basalt Monolith and Mind Stone keep the mana coming. Every card here is under $100 — the moxen, Grim Monolith and Ancient Tomb were cut for price. A turn-one line exists: Swamp, Dark Ritual ({B}{B}{B}), Mana Vault off one of them, tap it for {C}{C}{C} — that is {3}{B}{B}.
2. **Cover the turn she enters.** Cavern of Souls (name God) makes her uncounterable; Defense Grid taxes every spell cast outside its controller's turn by {3}. Then equip: Commander's Plate (protection from white, blue, red and green), Champion's Helm and Swiftfoot Boots (hexproof), Mithril Coat (**flash**, attaches itself on entry — indestructible in response to a wrath). Tyrite Sanctum puts an indestructible counter on a God for {4} and the land itself, and Tergrid is one.
3. **Make removal not stick.** Kaya's Ghostform (returns her if she dies **or is exiled**), Feign Death, Undying Evil, Not Dead After All, Demonic Gifts, Malakir Rebirth. Command Beacon puts her back in your hand instead of paying commander tax. **The hole is edicts:** hexproof and indestructible don't stop one, so Black Market Connections can make a 3/2 token on each of your turns (you lose 3 life) for an edict to take instead of her.
4. **Feed her from the first trigger.** Free and cheap discard (Grief by evoke, Unmask by exiling a black card, Thoughtseize, Duress, Hymn, Mind Twist), repeating discard (The Raven Man, Necrogen Mists, Bottomless Pit, Liliana of the Veil, Rankle), and edicts — Flare of Malice (free if you sacrifice a nontoken black creature) and Soul Shatter take each opponent's highest-mana-value creature or planeswalker, Sheoldred's Edict takes a nontoken creature, and Braids, Cabal Minion makes each player sacrifice an artifact, creature or land on their own upkeep.
5. **Find the piece you need.** Six tutors (Demonic, Vampiric, Insatiable Avarice, Grim, Diabolic Intent, Beseech the Mirror — bargain an artifact, enchantment or token, such as Lotus Petal, and it casts an MV-4-or-less card free). Insatiable Avarice is a Spree card: {B} plus {2} puts any card on top; add {B}{B} and a target player draws three and loses 3 life — yourself for the card you just found, or an opponent into Orcish Bowmasters or Exquisite Blood. Draw: Necropotence, Geth's Grimoire (a card whenever an opponent discards), Bolas's Citadel, Syphon Mind, Braids, Arisen Nightmare, Black Market Connections.

## How it wins

- **The stolen board.** Every edict and discard hands you a threat; Tergrid swings with menace.
- **Exquisite Blood + Vito, Thorn of the Dusk Rose** — two cards, both tutorable. Any life loss by an opponent makes you gain that much; any life you gain makes an opponent lose it. It does not stop until the table is dead.
- **Torment of Hailfire** off Cabal Coffers, Cabal Stronghold (a {B} per basic Swamp), Urborg or Nykthos mana; **Gray Merchant** off devotion. **Phyrexian Obliterator**: whatever damages it, that source's controller sacrifices that many permanents — and Tergrid takes the nontoken ones.

## Pilot

- **Opener you want:** two lands, two fast-mana pieces and one discard or protection card.
- **Strip, then land.** Grief or Thoughtseize their removal first, then cast Tergrid with Mithril Coat or a return spell held up.
- **Hold the edicts until she's on the battlefield** — before she resolves they steal nothing.
- **Smallpox and Braids, Cabal Minion hit you too.** Braids takes an artifact, creature or land: feed it Lotus Petal, a spent Chrome Mox or something you stole. Smallpox takes a creature, a land and a card from you as well, so cast it when you can spare all three.

**Mulligan** hands that can't cast her by turn 3 and have no tutor; keep a one-lander only with two fast-mana pieces and Dark Ritual.

## Traps
- **Mana Vault and Basalt Monolith don't untap in your untap step.** Mana Vault untaps only if you pay {4} in your upkeep; Basalt Monolith untaps for {3}.
- **Lightning Greaves is left out on purpose.** Shroud also blocks your Mithril Coat attach, Kaya's Ghostform, Feign Death and the other return spells.
- **Dauthi Voidwalker is left out on purpose.** It exiles every card that would go to an opponent's graveyard, and Tergrid returns cards from a graveyard — with Dauthi out she steals nothing.
- **Toxic Deluge kills her.** It is −X/−X, which indestructible does not stop. Cast it before she lands, or keep X at 4 or less.
- **Hexproof does not stop edicts or wraths; indestructible does not stop exile, −X/−X or an edict.** Kaya's Ghostform is the one piece that answers exile as well as dying.
- **When a return effect triggers, leave her where she went.** Kaya's Ghostform, Feign Death, Undying Evil and the rest return her from the graveyard (Ghostform also from exile). If you move her to the command zone instead, the trigger finds nothing. (That choice is a Commander rule, not card text — uncited here; rules.py can confirm it on your PC.)
- **Tergrid only takes nontoken permanents and permanent cards.** Sheoldred's Edict has a nontoken mode — use it. A discarded instant or sorcery gives her nothing.

## Numbers (computed 2026-10-11)

- **Field overlap:** 18/25 = 72% of Tergrid's top-25 nonland cards.
- **Roles (deckcore):** 30 lands · ramp 9 · draw 7 · removal 11 · wipes 1 · average MV 2.57 · resilience 5 protection · 6 recursion (counted from resilience_staples.csv).
- **Lands:** 30, and the app's Lands tile flags that as short — its template doesn't count fast mana. With 6 mana rocks (Sol Ring, Mana Vault, Basalt Monolith, Mind Stone, Arcane Signet, Fellwar Stone) this deck has 36 permanent mana sources, before Lotus Petal and the two rituals.
- **Goldfish (4,000 games, on the play):** Tergrid on the battlefield by turn 3 12%, turn 4 28%, turn 5 50%; mean turn 5.6. **Read these as a floor:** the simulator makes every mana rock produce from the turn after it resolves (a deliberate pessimism) and keeps only 2–5-land hands, while this deck's speed comes from 0- and 1-mana artifacts that tap the turn they land (Lotus Petal, Mana Vault, Sol Ring). Real play is faster; by how much is not measured.
- **Cost estimate:** ~$956 for all 82 non-basic cards, Tergrid included (Swamps not counted). **To buy: ~$895** for the 65 cards the collection snapshot doesn't have — they are this deck's buy list. You own the other 17. Free now: Archfiend of Depravity, Dark Ritual, Soul Shatter, Syphon Mind, Arcane Signet, Champion's Helm, Defense Grid. Already sleeved in another deck: Vito, Thorn of the Dusk Rose (yshtola-nights-blessed); Snuff Out (yshtola-nights-blessed); Grim Tutor (yshtola-nights-blessed); Toxic Deluge (dina-essence-brewer, yshtola-nights-blessed); Feed the Swarm (dina-essence-brewer); Sol Ring (beorn-the-fierce, captain-america-team-leader, cosmic-spider-man, dina-essence-brewer, kami-of-the-crescent-moon, the-ur-dragon, thorin-king-of-durins-folk, yshtola-nights-blessed); Mind Stone (kami-of-the-crescent-moon); Fellwar Stone (captain-america-team-leader, kami-of-the-crescent-moon, the-ur-dragon, yshtola-nights-blessed); Swiftfoot Boots (beorn-the-fierce, kami-of-the-crescent-moon); Bojuka Bog (dina-essence-brewer) — a second copy of those would add ~$49. Most expensive: Mana Vault ~$92, Urborg, Tomb of Yawgmoth ~$56, Vampiric Tutor ~$51, Cavern of Souls ~$48, Nykthos, Shrine to Nyx ~$45, Orcish Bowmasters ~$42, Exquisite Blood ~$39, Commander's Plate ~$38.

## Card roles (every nonland card is named here, so the optimizer leaves them alone)

- **Fast mana:** Sol Ring, Mana Vault, Basalt Monolith, Mind Stone, Lotus Petal, Dark Ritual, Cabal Ritual, Jet Medallion, Arcane Signet, Fellwar Stone
- **Tutors:** Demonic Tutor, Vampiric Tutor, Insatiable Avarice, Grim Tutor, Diabolic Intent, Beseech the Mirror
- **Card advantage:** Necropotence, Geth's Grimoire, Bolas's Citadel, Syphon Mind, Braids, Arisen Nightmare, Black Market Connections
- **Keep Tergrid on the battlefield:** Mithril Coat, Swiftfoot Boots, Champion's Helm, Commander's Plate, Defense Grid, Kaya's Ghostform, Feign Death, Undying Evil, Not Dead After All, Demonic Gifts, Malakir Rebirth
- **Discard that feeds her:** Grief, Thoughtseize, Unmask, Duress, Hymn to Tourach, Mind Twist, Burglar Rat, Elderfang Disciple, The Raven Man, Necrogen Mists, Bottomless Pit, Liliana of the Veil, Rankle, Master of Pranks
- **Sacrifice that feeds her:** Flare of Malice, Sheoldred's Edict, Liliana's Triumph, Soul Shatter, Plaguecrafter, Accursed Marauder, Archfiend of Depravity, Smallpox, Braids, Cabal Minion, Liliana, Dreadhorde General
- **Removal and disruption:** Snuff Out, Deadly Rollick, Fatal Push, Toxic Deluge, Feed the Swarm, Orcish Bowmasters, Opposition Agent
- **Win conditions:** Waste Not, Exquisite Blood, Vito, Thorn of the Dusk Rose, Torment of Hailfire, Gray Merchant of Asphodel, Phyrexian Obliterator
