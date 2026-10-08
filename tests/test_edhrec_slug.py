"""EDHREC slugs must match the URLs EDHREC actually serves."""
import edhrec


def test_slug_folds_accents_instead_of_dropping_them():
    # "bartolom-del-presidio" is not an EDHREC page; the deck ran with 0 field cards.
    assert edhrec.slugify("Bartolomé del Presidio") == "bartolome-del-presidio"


def test_slug_keeps_the_existing_rules():
    assert edhrec.slugify("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"
    assert edhrec.slugify("Beorn the Fierce") == "beorn-the-fierce"
    assert edhrec.slugify("Bruce Banner // The Incredible Hulk") == "bruce-banner"
