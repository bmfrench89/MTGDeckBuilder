# Giada, Font of Hope — "Choir of Wings"

Built 2026-10-15 by a session at the player's request ("Build the best Giada … I want to
compare what you come up with versus what I have … carefully comb through my collection").
The starting point was an auto_build draft over the free pool. A hand pass then made 30 cuts
and 30 adds, each read against the engine below. Every card is a free copy. Where Giada
and one of the session's own decks (Tifa, Sephiroth) wanted the same single copy, Giada
kept it.

## The engine

**Verified commander text** (Scryfall, 2026-10-15):

> Giada, Font of Hope — {1}{W} — Legendary Creature — Angel
> Flying, vigilance
> Each other Angel you control enters with an additional +1/+1 counter on it for each Angel
> you already control.
> {T}: Add {W}. Spend this mana only to cast an Angel spell.

**A two-drop that grows every Angel after her and pays for them.** 32 Angels, and Angel
*tokens* count too: each one enters with Giada's counters.

- **Life gain turns into Angels.**
  - Bishop of Wings: every Angel entering gains 4 life, and every Angel that dies leaves a
    1/1 flier.
  - Four cards then turn that life into Angel tokens:
    - Angelic Accord: 4+ life in a turn, a 4/4 Angel at each end step.
    - Valkyrie Harbinger: 4+ life, a 4/4 Angel with vigilance.
    - The Book of Exalted Deeds: 3+ life, a 3/3 Angel at your end step.
    - Ob Nixilis, the Ascended: if you gained any life, a 4/4 Angel at *each* end step,
      opponents' turns included.
  - Each new token is an Angel entering, so Bishop gains 4 more. **It doesn't loop:** the
    tokens arrive during the end step, after Accord, Harbinger, the Book and Ob Nixilis
    have already checked (CR 603.4, and the Accord and Harbinger rulings: life gained
    during the end step doesn't count). That life moves you toward 47 and 55 instead.
- **More life:**
  - Righteous Valkyrie: life equal to each entering Angel's toughness, and +2/+2 to the
    team at 47+ life.
  - Seraph Sanctuary, Authority of the Consuls and Sigarda's Splendor.
  - **Shattered Angel works on opponents' turns:** "Whenever a land an opponent controls
    enters, you may gain 3 life." With Angel of Vitality (+1) that's 4 per land drop, and
    Accord, Harbinger and Ob Nixilis check at *each* end step. So an opponent's land drop
    gives you a 4/4 Angel at the end of their turn. (Added 2026-10-15 on an engine read;
    EDHREC lists it at 20%.)
  - Lifelink: Lyra, Gisela, Angel of Indemnity, Valkyrie Harbinger, Serra Ascendant.
  - **The Wind Crystal doubles all of it** (and cuts white spells by {1}).
- **Monarch and walkers:**
  - Court of Grace: a 4/4 Angel every upkeep while you're the monarch.
  - Serra the Benevolent −3: a 4/4 Angel with vigilance.
- **Two other ways to win:**
  - Angel of Destiny (double strike): at your end step with 55+ life (15 over the starting
    40), every player it attacked this turn loses.
  - The Book of Exalted Deeds' exile ability: an Angel with "You can't lose the game and
    your opponents can't win the game."
- **Enlightened Tutor** (the one Game Changer, and the player's own copy) puts the missing
  artifact or enchantment on top: The Wind Crystal, Angelic Accord, Court of Grace or The
  Book of Exalted Deeds.

## Protected engine (don't cut; several sit under 20% on EDHREC)
- Bishop of Wings
- Angelic Accord
- Valkyrie Harbinger
- Ob Nixilis, the Ascended
- The Book of Exalted Deeds
- The Wind Crystal
- Righteous Valkyrie
- Angel of Destiny
- Court of Grace
- Serra the Benevolent
- Enlightened Tutor
- Sigarda's Splendor
- Seraph Sanctuary
- Shattered Angel
- Angel of Vitality

## Protection and interaction
- **Protection:**
  - Flawless Maneuver: free with a commander out.
  - Flare of Fortitude: free by sacrificing a nontoken white creature. Your life total
    can't change, and your permanents gain hexproof and indestructible. **Angel of
    Jubilation turns off that free cost** ("players can't … sacrifice creatures to cast
    spells"), so with Jubilation out, Flare costs {2}{W}{W}.
  - Lightning Greaves, Swiftfoot Boots.
  - Avacyn, Angel of Hope: your permanents are indestructible.
  - Serra's Emissary: name "creature" and you and your creatures have protection from
    creatures.
- **Removal:**
  - Swords to Plowshares, Path to Exile, Generous Gift, Destroy Evil, Disenchant, Reprieve.
  - Heliod's Intervention: destroy X artifacts and/or enchantments, or gain twice X life.
    It can't save creatures from a wrath.
  - Angel of the Ruins exiles two artifacts or enchantments.
  - Austere Command.
  - Ob Nixilis, the Ascended destroys every *tapped* creature your opponents control. Cast
    it after they attack.
- **Taxes:** Ghostly Prison, Archangel of Tithes, Linvala (no activated abilities for
  their creatures).

## Pilot notes
- Giada on turn 2 (goldfish: 84% by turn 2). Then sequence Angels cheapest first: every
  later Angel enters bigger.
- Bishop of Wings or Righteous Valkyrie before the token-makers. 4 life from one Angel
  turns on Accord and Harbinger by itself.
- Hold Flawless Maneuver or Flare of Fortitude for the wrath, or have Avacyn out; the
  board is the win.

## The numbers (2026-10-15)
- **Bracket 3** (detected and declared). One Game Changer (Enlightened Tutor), no infinite
  combos (Commander Spellbook: 0).
- **Field:** 19 of EDHREC's top 25 for Giada (37,497 decks). None of the other 6 are owned:
  Herald of War, Starnheim Aspirant, Resplendent Angel, Archangel of Thune, Herald's Horn,
  Emeria Shepherd. They're the buy list.
- **Optimizer read:** it proposed Ghostly Prison → Akroma's Will (held by Tifa), and
  Mistveil Plains and Windbrisk Heights → Plains. All rejected: Ghostly Prison is the tax
  piece, and both lands do work in a 22-Plains deck.
- **Mana:** 36 lands (22 Plains), 28 W sources, keepable 79%. Giada herself taps for Angels.
- **Goldfish:** combat-only lethal median turn 9. It models no tokens, no life gain and
  no Angel of Destiny, so read it as a floor.

## Angel audit (2026-10-15, on the player's ask)
- **The pool:** the collection holds 41 white or colourless Angels, all with type data
  (`analyze_collection --query "t:angel id<=w"`, 0 skipped). **32 are in this deck.**
  Battle Angels of Tyr, Lyra, Baneslayer, Avacyn, Sephara and Angel of Destiny are all here.
- **The 9 left out:**
  - Shepherd of the Cosmos: Bartolomé's only copy.
  - Starfield Shepherd: a 5-mana 3/2 that fetches a Plains or a 1-drop.
  - Darksteel Angel: 9 mana.
  - Angelic Curator, Voice of Truth, Voice of Grace, Vanguard Seraph, Sustainer of the
    Realm: 2/2 and 3/3 fliers with no engine text.
  - Herald of Serra: swapped out for Shattered Angel. It's a vanilla 3/4 you pay for twice
    (echo).
- **Field Angels the deck lacks are all unowned:** Herald of War, Starnheim Aspirant,
  Resplendent Angel, Archangel of Thune, Emeria Shepherd, Lyra Archangel of Dawn, Segovian
  Angel, Dazzling Angel, Sunblast Angel, Speaker of the Heavens, Angelic Skirmisher, Herald
  of Eternal Dawn, Steel Seraph.
- **Owned field staples held elsewhere, not taken:** Folk Hero and Archaeomancer's Map
  (Captain America and Y'shtola, the player's decks), Akroma's Will and Stroke of Midnight
  (Tifa).
- **Not owned in white at all:** the collection's other Angels are Akroma, Angel of Fury (R)
  and Avacyn, Angel of Horror and Fallen Angel (B), none of which Giada can play.
