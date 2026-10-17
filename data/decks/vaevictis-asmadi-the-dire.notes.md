# Vaevictis Asmadi, the Dire — "The Gamble and the Grave"

Built 2026-10-16 around **Avacyn, Angel of Horror**. The player: "I want to build a deck
with Avacyn the angel horror black card either as a commander or in the 99 … use this
video for inspiration. I'd be happy to use that dragon at the commander if nothing else I
own is better."

**A theory deck in the Lab** (moved 2026-10-17). The player: "Go ahead and make both decks
with vaevictis and tom bert and William as commander in the lab and let's see how they
compare."
- **Its twin** is Tom, Bert, and William, with the same Avacyn engine in black-green.
- **Both use free copies only,** so either can be made a real deck without taking a card from
  another deck.

## The engine

**Commander (verified):** Vaevictis Asmadi, the Dire — {3}{B}{R}{G}, Legendary Creature —
Elder Dragon. "Flying. Whenever Vaevictis Asmadi attacks, for each player, choose target
permanent that player controls. Those players sacrifice those permanents. Each player who
sacrificed a permanent this way reveals the top card of their library, then puts it onto
the battlefield if it's a permanent card."
- **Rulings (Scryfall):**
  - You must target one of your own permanents too.
  - The trigger resolves in the declare attackers step, before blockers.
  - If any player controls no permanents, the trigger does nothing.
  - A player whose targeted permanent isn't sacrificed (it gained hexproof, say) doesn't
    reveal either.

**The returner (verified):** Avacyn, Angel of Horror — {5}{B}{B}{B}. "Flying, deathtouch.
Whenever Avacyn or another nontoken creature you control dies, return that card to the
battlefield under your control at the beginning of the next end step."
- **Ruling:** if she dies with other creatures, each one triggers, so she brings herself back
  too.

**Why Vaevictis and not another commander.** A full scan found 161 legendary creatures with
black in their identity that the player owns, 123 of them free.
- **Tom, Bert, and William multiply Avacyn's loop best on their own text,** and they're in
  this 99.
- **Vaevictis's B/R/G identity is the only seat that holds all of it:**
  - Avacyn, Tom, Bert, and William, red's haste and wipes, and the dragon himself.
  - The deepest free pool: 1,534 nonland cards and 88 ramp, against 1,021 and 74 for
    black-green.
- **His attack is an engine of its own:** three targeted edicts on the table, a
  self-sacrifice that Avacyn turns into value, and a free permanent off the top.

## How it plays: three packages

### 1. Your sacrifice comes back
Every nontoken creature you sacrifice returns at the next end step, so each sacrifice is a
payment you get back.
- **Free outlets, at instant speed:** Carrion Feeder, Woe Strider, Yahenni.
- **{1} outlets:** Tom, Bert, and William (draw cards equal to the sacrificed creature's
  power), Unrooted Ancestor.
- **Others:** Deadly Dispute, Phyrexian Vault and Ghoulcaller Gisa.
- **Vaevictis's attack is an outlet too.** Pick your own nontoken creature as your
  sacrifice.
- **What comes back and fires again:**
  - Gray Merchant of Asphodel drains for your devotion to black.
  - Archon of Cruelty: an opponent sacrifices, discards and loses 3; you draw and gain 3.
  - Fleshbag Marauder: each player sacrifices; yours comes back.
  - Grave Titan makes two Zombies.
  - Sepulchral Primordial reanimates a creature from each opponent's graveyard.
  - God-Eternal Bontu sacrifices your board for cards, and the board comes back.
  - Junji, Eternal Witness and Gravedigger.
  - Kardur: until your next turn, every opposing creature must attack a player other than
    you, again on each return.
  - Ramp: Burnished Hart, Springbloom Druid, Wood Elves and Clifftop Lookout.
  - Curse-Marred Demon tutors.
  - Doctor Doom makes two Doombots.
- **Twilight Diviner** copies one returning creature a turn, because Avacyn returns them
  "from a graveyard". A returned Gray Merchant or Archon triggers twice.
- **Bone Shredder** is removal every turn. Don't pay its echo; it dies, returns at end step,
  destroys a creature, and its echo re-arms (CR 702.30a).
- **Payoffs for each death:** Midnight Reaper and Agent Venom draw, Massacre Girl pings, and
  Skullclamp draws two. Mazirek grows the team on every sacrifice, by anyone.
- **Each creature comes back once per end step,** so it can loop once on each player's turn.
  That's why the free instant-speed outlets matter.

### 2. Stack the top, then attack
Vaevictis's flip puts your top card onto the battlefield if it's a permanent, so set it
before attacking:
- Woe Strider's scry 1 on every sacrifice.
- Twilight Diviner's surveil 2 and Lys Alana Informant's surveil 1, again on each return.
- The scry lands, Temple of Malice and Temple of Abandon. Read the Bones doesn't count: you
  draw the two cards you scried, so it leaves nothing known on top.
- **Haunted Crossroads:** {B}: put a creature card from your graveyard on top. It turns any
  dead fatty, or Tom, Bert, and William's discard, into Vaevictis's next flip.

### 3. Lands come back
Undergrowth Recon returns a land from your graveyard every upkeep. With it out, you can give
Vaevictis a land as your sacrifice when no creature should go.

### One-sided wipes
With Avacyn out, a destroy or damage wipe kills everything, and only your nontoken creatures
return at end step.
- Blasphemous Act and Villainous Wrath.
- Whiptongue Hydra: fliers only. Avacyn and Vaevictis come back; theirs don't.

## Rules that decide games (CR retrieved 2026-10-16)
- **"Dies" means put into a graveyard from the battlefield (CR 700.4).**
  - Exile removal beats Avacyn: sacrifice the target in response, and it dies and comes
    back.
  - Woe Strider, Yahenni, Unrooted Ancestor and Tom, Bert, and William sacrifice only
    ANOTHER creature. If the exile spell targets the outlet itself, Carrion Feeder, Deadly
    Dispute or Phyrexian Vault has to do it.
  - Under Rest in Peace or Leyline of the Void nothing dies, so nothing returns.
- **A card that changes zones is a new object (CR 400.7).** If an opponent exiles your
  graveyard before the end step, Avacyn's return finds nothing. Bojuka Bog and Scavenger
  Grounds are the threats to watch.
- **Vaevictis can come back for free.** When he dies, moving him to the command zone is your
  choice (CR 903.9a). Leave him in the graveyard and Avacyn returns him at end step with no
  tax.
- **Order your own simultaneous triggers (CR 603.3b).**
- **A creature that dies during an end step waits a turn.** Its return is set up during that
  step, so it comes back at the next turn's end step (CR 513.2).
- **Tom, Bert, and William return themselves at once,** as an artifact that is no longer a
  creature, so Avacyn's later return finds nothing. They keep the {1} sacrifice outlet and
  dodge creature removal.
- **God-Eternal Bontu:** decline her "third from the top" option, and Avacyn returns her
  instead.

## Piloting
- **Before combat,** fix the top card (scry, surveil, Haunted Crossroads), then attack with
  Vaevictis.
  - Choose each opponent's best permanent.
  - For yours, choose a nontoken creature with Avacyn out, otherwise a token, Goat or
    Zombie, or a land with Undergrowth Recon out.
- **On opponents' turns,** sacrifice in response to removal. Every nontoken creature should
  die once per turn cycle if it has a trigger worth repeating.
- **Champion's Helm** gives Vaevictis hexproof without stopping him targeting your own
  permanents.

## Mulligan
- **Keep:** 3-4 lands with two of the three colours, plus a ramp piece. Ilysian Caryatid,
  Arcane Signet and Command Tower fix all three.
- **A hand with a free outlet and an early value creature is fine** even without Avacyn.
  The deck is an aristocrats deck before she arrives.

## Weaknesses to respect
- **Graveyard and exile hate:** Bojuka Bog, Rest in Peace, Swords to Plowshares.
- **Avacyn costs 8:**
  - The ramp creatures loop, but she is one card. Curse-Marred Demon can tutor her.
  - Haunted Crossroads plus a Vaevictis attack can cheat her in from the graveyard.
- **The flip is symmetric:** opponents put permanents onto the battlefield too. Aim their
  sacrifice at their best permanent so the trade favours you.

## Inspiration
- **The video:** Jurassic Magic, "This Commander Turns Every Attack Into Pure Chaos"
  (2026-10-16), deck "The Eater of Elders". Its 99 runs Avacyn, Angel of Horror.
- **The captions couldn't be fetched** (YouTube signs them per session), so this build reads
  the creator's list and description, not the commentary.
- **Taken from it, owned and free:** Avacyn, Haunted Crossroads, Undergrowth Recon, Junji,
  Sepulchral Primordial, Mazirek, Tom, Bert, and William, Wood Elves, Terminate, Heroic
  Intervention, Sol Ring, Arcane Signet, and its ramp spells.
- **Not owned (buylist):** Scroll Rack and Sensei's Divining Top, Wulfgar of Icewind Dale,
  Grave Betrayal and Etali.
- **What this build adds that the video doesn't:** the aristocrats engine (free outlets plus
  enter-trigger creatures), Twilight Diviner's copies and Bone Shredder's echo loop.

## Grounding
- **Field:** Vaevictis Asmadi, the Dire, 4,048 EDHREC decks (snapshot 2026-10-16). Avacyn,
  Angel of Horror is in 18% of them, Haunted Crossroads 48%.
- **Owned top-25 not in this list:** each one's copies are in another deck, and each is on
  the buylist or the ⚡ verdicts.
  - Lightning Greaves (Giada, Ur-Dragon, Y'shtola).
  - Rhythm of the Wild (Ur-Dragon).
  - Swiftfoot Boots (Beorn, Eriette, Giada, Kami).
  - Sakura-Tribe Elder (Dina).
  - Birds of Paradise (Ur-Dragon).
  - Woodland Cemetery (Dina).
  - Solemn Simulacrum (Y'shtola).
- **Orcish Bowmasters is deliberately out.** The player is re-reviewing where it goes.
- **Only one tutor finds Avacyn,** Curse-Marred Demon, again on each return. The three black
  tutors the player owns are all in sleeved decks: Grim Tutor (Ur-Dragon), Diabolic Tutor
  (Y'shtola), Final Parting (Bartolomé). In 4,000 goldfish games she was cast by turn 10 in
  only 4%.
- **Against Tom, Bert, and William on the same games,** Vaevictis is cast by turn 7 in 51%,
  where Tom, Bert, and William are on the battlefield by turn 7 in 68%.
- **Combos:** Commander Spellbook finds none present. The one-card-away lines all go
  infinite: Mazirek with Putrid Goblin or Scurry Oak and a free outlet. That would change
  the bracket, so they're not on the buylist.
- **Bracket:** no Game Changers, no combos, so it's detected 2. It plays above a precon.
- **Verified text:** every card was read from Scryfall's cache or `carddb.py --verify` on
  2026-10-16.

## Protected engine (don't cut)
- Avacyn, Angel of Horror
- Tom, Bert, and William
- Carrion Feeder
- Woe Strider
- Yahenni, Undying Partisan
- Gray Merchant of Asphodel
- Archon of Cruelty
- Fleshbag Marauder
- Bone Shredder
- God-Eternal Bontu
- Grave Titan
- Sepulchral Primordial
- Junji, the Midnight Sky
- Kardur, Doomscourge
- Mazirek, Kraul Death Priest
- Twilight Diviner
- Haunted Crossroads
- Undergrowth Recon
