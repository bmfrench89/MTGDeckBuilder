# The Lab: a place for theory decks (2026-10-16)

**Status:** SHIPPED, v1.
**Asked for by the player**, after a theory build (Witherbloom, Bracket 4) that counted
every owned card, even ones sleeved in other decks: "maybe we update the deck page UI
and allow another way to view brainstormed decks? Think about how this could look and
let's implement it."

## The problem
A theory deck is a study copy (`# Study: yes`): it may use any card you own, and it
claims no copies (`deck_conflicts.is_study_deck`). The Decks page mixed it in with the
sleeved decks under a small "Study copy" tag, and every number on its card answered
the wrong question:
- **"Ready to sleeve" and "contested"** mean nothing for a deck that holds nothing.
- **The deck page's Shared Across Decks panel** read "fully self-contained", which is
  false. A theory deck's cards usually live in other decks; that's the point.

## What a theory deck needs to answer
*What would building it for real take, and from which decks?*
`deck_conflicts.lab_sources` puts every non-basic card in one of three groups:
- **held:** every copy is in another real deck, and those decks are named;
- **free:** a spare copy is in the collection;
- **missing:** not owned.

## The design
- **Decks page, two tabs** (the Collection's sub-tab pattern; each tab is a URL, so
  Back and bookmarks work):
  - **Your decks** (`/`): sleeved decks only, unchanged.
  - **Lab** (`/lab`): theory decks.

  Each tab shows a neutral count; the current tab's count is amber.
- **A Lab card** has a dashed edge and a **Theory** tag. Its status line is
  "44 from other decks · 42 free · N to buy", then the top three donors by title:
  "From Dina 27 · Y'shtola 9 · The Ur-Dragon 7 · +9 more". There are no "ready" or
  "attention" chips in the Lab.
- **An empty Lab** says what a theory deck is and how to make one.
- **Moving a deck** is one menu item each way:
  - **Move to the Lab** on a real deck. It keeps the list, notes and history, stops
    claiming copies, and drops its pins, as Delete does.
  - **Make it a real deck** on a theory deck. The confirm and the message after it say
    how many of its cards would turn contested.
  - The only edit is the `# Study: yes` header line (`deck_conflicts.set_study`), so
    a deck moved in and back is byte for byte what it was.
- **A theory deck's page** (the dashboard) opens on a **Lab** tab:
  - the summary;
  - the cards grouped "From <deck>", then "Spare copies", then "Not owned". Every name
    opens the card panel;
  - on the app surface, a Make it a real deck button.

  The header carries a "Theory deck · in the Lab · claims no copies" tag, and the
  breadcrumb leads back to the Lab. The false Shared Across Decks panel is gone for
  theory decks. A downloaded dashboard keeps the Lab tab, without the dead button.

## Fixed on the way
**Every confirm on the deck menu now passes its text through `tojson`.** A title with
an apostrophe (Y'shtola, Night's Blessed) broke the inline `confirm('…')` string, and a
handler that doesn't compile submits without asking: Delete on Y'shtola ran with no
confirmation. `test_lab` parses every handler's message as JSON.

## Tests and UAT
- **tests/test_lab.py:**
  - the three groups, and that one theory deck never holds a card from another;
  - the header flip, byte for byte, for LF, CRLF and header-only files;
  - the two views and their counts;
  - the Lab card's line;
  - the empty Lab;
  - the apostrophe confirms;
  - the move route both ways, with pins dropped, and its 400 and 404;
  - the contested count after making a deck real;
  - the Lab tab first, the breadcrumb, no false shared claim, and no dead button
    offline.
- **webapp/uat/sweep.js** photographs `/lab` and a theory deck's page at every size.
- **webapp/uat/flows.js F15:**
  1. Move to the Lab from the phone menu. The file changes by one line.
  2. Find the deck in the Lab, open it on the Lab tab, and make it real again. The
     file comes back byte for byte.

## Next (not built)
- **Import a list straight into the Lab:** a "theory deck" checkbox on /decks/import.
- **Compare a theory deck with the deck it would break down,** side by side.
- **A Lab-wide view of which real decks the theory decks lean on most.**
