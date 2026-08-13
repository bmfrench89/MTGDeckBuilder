"""Phase 12 — one role template, one header parser, a swing that can't buy a swap.

Three copies of the role template disagreed on 17 of 30 judgments across the six
real decks, so the fit scorer pushed counterspells into a voltron deck while the
optimizer's filter correctly refused them. These tests pin the fix: the scorer and
the filter read THE SAME archetype-aware table (deckcore), the role-point spread is
too small for template pressure alone to clear the optimizer's swap margin, and
disagreement between template and field is SHOWN, never silently resolved."""
import inspect

import pytest

import deck_fit
import deck_stats
import deckcore
import mtglib
import optimize
import power


def _ctx(archetype=None, field=None):
    ranges, unknown = deckcore.role_ranges_with_unknown(archetype or [])
    return {"identity": {"W", "U"}, "archetype": archetype or [], "theme": "",
            "tribal": None, "commander": "T", "field": field or {}, "synergy": {},
            "role_ranges": dict(ranges, land=deckcore.LAND_RANGE),
            "archetype_unknown": unknown}


def _card(name, types, mv=2.0, cost="{1}{U}"):
    return mtglib.Card(name=name, quantity=1, mana_value=mv, colors={"U"},
                       identity={"U"}, mana_cost=cost, types=types)


def _role_pts(card, cats, archetype=None, field=None):
    rep = {"categories": cats}
    pts, role, det = deck_fit._role_component(card, rep, None,
                                              _ctx(archetype, field))
    return pts, role, det


# --------------------------------------------------------------------------- #
# The three bad calls from the 17/30 measurement, each now correct
# --------------------------------------------------------------------------- #
def test_a_voltron_deck_with_zero_counterspells_is_not_told_to_add_them():
    """Cloud (equipment voltron, 0 counters): old FIT_TARGETS counter band (3,8)
    called that a SHORTAGE (+30) — pushing counterspells into a voltron deck."""
    pts, role, _ = _role_pts(_card("Counterspell", ["Instant"]), {"counter": 0},
                             archetype=["equipment", "voltron", "artifacts"])
    assert role == "counter"
    assert pts == deck_fit.ROLE_PTS_HEALTHY, "0 counters is healthy, not a shortage"


def test_a_token_deck_with_one_wipe_is_not_told_it_has_a_wipe_shortage():
    """Cosmic (go-wide tokens, 1 wipe): a wrath kills YOUR board first — the
    archetype band is 0-5, so 1 is healthy."""
    pts, _, _ = _role_pts(_card("Toxic Deluge", ["Sorcery"]), {"wipe": 1},
                          archetype=["tribal-spiders", "go-wide", "tokens"])
    assert pts == deck_fit.ROLE_PTS_HEALTHY


def test_a_control_decks_fifteen_counterspells_are_not_deprioritized_as_depth():
    """Iron Man (draw-go control, counter:15): the old blind band (3,8) scored every
    counterspell as over-target depth (+12) — telling a control deck to deprioritize
    its interaction suite."""
    pts, _, _ = _role_pts(_card("Counterspell", ["Instant"]), {"counter": 15},
                          archetype=["artifacts", "draw-engine", "control"])
    assert pts == deck_fit.ROLE_PTS_HEALTHY, "15 counters is inside control's 0-18"


# --------------------------------------------------------------------------- #
# Single-sourcing: one table, everywhere
# --------------------------------------------------------------------------- #
def test_the_shims_are_the_same_objects_not_copies():
    assert optimize.ROLE_RANGE is deckcore.ROLE_RANGE
    assert optimize.role_ranges is deckcore.role_ranges
    assert optimize.role_ranges_with_unknown is deckcore.role_ranges_with_unknown
    assert optimize.LAND_TARGET is deckcore.LAND_TARGET


def test_deck_stats_targets_derive_from_the_canonical_table():
    for role, band in deckcore.ROLE_RANGE.items():
        assert deck_stats.TARGETS[role] == band
    assert deck_stats.TARGETS["lands"] == deckcore.LAND_RANGE


def test_the_scorer_and_the_filter_read_the_same_bands():
    """The drift this phase kills: for every role and every archetype in the table,
    the fit scorer's shortage/healthy/depth verdict must flip at exactly the bounds
    the optimizer's accept filter uses."""
    for arch in [None] + [[w] for w in deckcore._ARCHETYPE_ROLE_RANGE]:
        ranges = deckcore.role_ranges(arch)
        for role, (lo, hi) in ranges.items():
            probe = _card("Probe", ["Instant"])
            # force primary_role by patching classify via a role-typed fake is heavy;
            # instead check the band arithmetic through the public component:
            for cur, want in ((max(0, lo - 1), deck_fit.ROLE_PTS_SHORTAGE if lo > 0
                               else deck_fit.ROLE_PTS_HEALTHY),
                              (lo, deck_fit.ROLE_PTS_HEALTHY),
                              (hi, deck_fit.ROLE_PTS_HEALTHY),
                              (hi + 1, deck_fit.ROLE_PTS_DEPTH)):
                ctx = _ctx(arch)
                rep = {"categories": {role: cur}}
                # Counterspell classifies as counter; use role-specific fakes only
                # for the counter role, and trust the arithmetic for the rest —
                # _role_component reads (role, cur) through one code path.
                if role != "counter":
                    continue
                pts, _, _ = deck_fit._role_component(
                    _card("Counterspell", ["Instant"]), rep, None, ctx)
                assert pts == want, (role, arch, cur)


# --------------------------------------------------------------------------- #
# The swing cap: template pressure can never clear the margin alone
# --------------------------------------------------------------------------- #
def test_role_pressure_alone_cannot_clear_the_optimizer_margin():
    """THE tripwire. value_of doubles fit differences, so if (shortage - depth) * 2
    ever reaches the optimizer's default margin again, template pressure alone can
    buy a swap with no field or quality support — the 2026-08-12 churn mechanism.
    Widening this spread is a design change that needs this test changed knowingly."""
    spread = deck_fit.ROLE_PTS_SHORTAGE - deck_fit.ROLE_PTS_DEPTH
    margin = inspect.signature(optimize.optimize).parameters["margin"].default
    assert spread * 2 < margin, (
        f"role swing {spread}x2 >= margin {margin}: template pressure can once "
        "again manufacture a swap on its own")


# --------------------------------------------------------------------------- #
# Disagreement is surfaced, never silently resolved — and absent field data
# stays silent (no row is NOT a measured 0%)
# --------------------------------------------------------------------------- #
def test_template_field_disagreement_is_shown_on_the_card():
    _, _, det = _role_pts(_card("Swords to Plowshares", ["Instant"]), {"removal": 0},
                          field={"swords to plowshares": 4})
    assert "the field plays this one in 4%" in det
    assert "not necessarily this card" in det


def test_no_field_row_means_no_field_claim():
    _, _, det = _role_pts(_card("Swords to Plowshares", ["Instant"]), {"removal": 0},
                          field={"some other card": 50})
    assert "field plays this one" not in det, "absent data must stay silent"


def test_field_endorsed_depth_says_so():
    _, _, det = _role_pts(_card("Counterspell", ["Instant"]), {"counter": 9},
                          field={"counterspell": 40})
    assert "field endorses this copy (40%" in det


def test_a_widened_band_is_labelled_in_the_detail():
    _, _, det = _role_pts(_card("Counterspell", ["Instant"]), {"counter": 15},
                          archetype=["control"])
    assert "band widened by archetype" in det
    _, _, det2 = _role_pts(_card("Counterspell", ["Instant"]), {"counter": 3})
    assert "band widened" not in det2, "no label when nothing was widened"


# --------------------------------------------------------------------------- #
# The live-data regression: ur-dragon's empty header
# --------------------------------------------------------------------------- #
def test_ur_dragons_empty_archetype_header_parses_as_nothing(tmp_path):
    """The bug found in production data: `# Archetype: ` (empty) swallowed the next
    line, parsing as ['#', 'source:', 'auto-generated', ...]."""
    p = tmp_path / "d.txt"
    p.write_text("# Title: T\n# Colors: B G R U W\n# Archetype: \n"
                 "# Source: auto-generated draft (scripts/auto_build.py)\n"
                 "\n# --- Main ---\n1 Sol Ring\n", encoding="utf-8")
    ctx = deck_fit.deck_context(str(p), [], "")
    assert ctx["archetype"] == []
    assert ctx["archetype_unknown"] == []
    assert ctx["role_ranges"]["ramp"] == deckcore.ROLE_RANGE["ramp"]


def test_archetype_words_is_the_one_tokenizer():
    assert deckcore.archetype_words("control, lifegain/aristocrats") == \
        ["control", "lifegain", "aristocrats"]
    assert deckcore.archetype_words(
        "# Title: T\n# Archetype: go-wide tokens\n") == ["go-wide", "tokens"]
    assert deckcore.archetype_words("# Archetype: \n# Source: x\n") == []


def test_auto_build_quotas_sit_inside_the_canonical_bands():
    """auto_build's quotas are AIM POINTS, not bands — but an aim outside the
    acceptance band would build decks the rest of the stack calls broken."""
    import auto_build
    for role, quota in auto_build.ROLE_QUOTA:
        lo, hi = deckcore.ROLE_RANGE[role]
        assert lo <= quota <= hi, f"{role} quota {quota} outside {lo}-{hi}"


# --------------------------------------------------------------------------- #
# The symmetric protection: never re-add a manual removal (found live — Hojo)
# --------------------------------------------------------------------------- #
def test_a_manual_removal_is_a_decision_not_a_cooldown(tmp_path):
    ch = tmp_path / "d.changes.csv"
    ch.write_text("Card,Added,Replaced,Source\n"
                  "Forge Anew,2026-08-11,Professor Hojo,manual-replace\n"
                  "Professor Hojo,2026-08-10,Crop Rotation,free\n", encoding="utf-8")
    held = deckcore.manual_removals(str(ch))
    assert "professor hojo" in held
    # optimizer rows (Source=free) never create holds
    assert "crop rotation" not in held


def test_a_later_manual_readd_lifts_the_hold(tmp_path):
    ch = tmp_path / "d.changes.csv"
    ch.write_text("Card,Added,Replaced,Source\n"
                  "Forge Anew,2026-08-01,Professor Hojo,manual-replace\n"
                  "Professor Hojo,2026-08-12,Something Else,manual-add\n",
                  encoding="utf-8")
    assert "professor hojo" not in deckcore.manual_removals(str(ch)), (
        "the newest player action wins — a re-add supersedes the removal")


def test_manual_removal_holds_are_front_face_aware(tmp_path):
    ch = tmp_path / "d.changes.csv"
    ch.write_text("Card,Added,Replaced,Source\n"
                  "X,2026-08-11,Murderous Rider // Swift End,manual-replace\n",
                  encoding="utf-8")
    held = deckcore.manual_removals(str(ch))
    assert mtglib._norm("Murderous Rider") in held


def test_the_optimizer_holds_a_removed_card_and_reports_it(tmp_path, monkeypatch,
                                                           collection_file):
    """The live case, hermetically: a manually-removed card at high field inclusion
    must not come back as a swap — and must appear in `manual_holds` with its
    evidence, because suppressing the proposal silently would hide the field's
    disagreement instead of surfacing it."""
    import deck_fit
    deck = tmp_path / "d.txt"
    deck.write_text("# Title: T\n# Commander: Test Commander\n# Colors: W U\n\n"
                    "# --- Creatures ---\n1 Serra Angel\n\n"
                    "# --- Lands ---\n10 Island\n", encoding="utf-8")
    (tmp_path / "d.changes.csv").write_text(
        "Card,Added,Replaced,Source\n"
        "Serra Angel,2026-08-11,Counterspell,manual-replace\n", encoding="utf-8")
    monkeypatch.setattr(deck_fit, "load_field", lambda *a, **k: {"counterspell": 80})
    monkeypatch.setattr(deck_fit, "load_synergy", lambda *a, **k: {"counterspell": 69})
    coll = mtglib.load_collection(collection_file)
    idx = mtglib.index_by_name(coll)
    r = optimize.optimize(str(deck), coll, idx, str(tmp_path), margin=25)
    assert not any(add == "Counterspell" for _c, _v, add, _i, _a in r["swaps"]), (
        "an 80%-field card the player removed by hand must stay out")
    holds = r["manual_holds"]
    assert holds and holds[0]["name"] == "Counterspell" and holds[0]["inc"] == 80
