"""carddb's offline bulk path against the shapes Scryfall has published.

By 2026-10 Scryfall's bulk-data catalog offers `jsonl_download_uri` (gzipped JSON
Lines) where it used to offer `download_uri` (one JSON array), and `download_bulk`
crashed on the missing key. Both shapes must keep working; everything is hermetic."""
import gzip
import json

import carddb

CARDS = [{"name": "Sol Ring", "type_line": "Artifact"},
         {"name": "Counterspell", "type_line": "Instant"},
         {"type_line": "nameless junk row"}]


def test_reads_a_json_array(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps(CARDS), encoding="utf-8")
    assert [c["name"] for c in carddb._rows_json(str(p))] == ["Sol Ring", "Counterspell"]


def test_reads_gzipped_json_lines(tmp_path):
    p = tmp_path / "b.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(c) for c in CARDS) + "\n")
    assert [c["name"] for c in carddb._rows_json(str(p))] == ["Sol Ring", "Counterspell"]


def test_reads_plain_json_lines_whatever_the_file_is_called(tmp_path):
    p = tmp_path / "misnamed.json"
    p.write_text("\n".join(json.dumps(c) for c in CARDS), encoding="utf-8")
    assert len(list(carddb._rows_json(str(p)))) == 2


def test_download_takes_the_jsonl_link_when_that_is_all_scryfall_offers(tmp_path,
                                                                        monkeypatch):
    catalog = {"data": [{"type": "oracle_cards", "name": "Oracle Cards",
                         "compressed_size": 10,
                         "jsonl_download_uri": "https://example.invalid/o.jsonl.gz"}]}
    monkeypatch.setattr(carddb, "_get", lambda url: json.dumps(catalog))
    body = gzip.compress(b'{"name": "Sol Ring"}\n')
    seen = {}

    class _Resp:
        def __init__(self):
            self.left = body

        def read(self, n):
            out, self.left = self.left[:n], self.left[n:]
            return out

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(carddb.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "scryfall-oracle_cards.jsonl.gz"
    got = carddb.download_bulk(dest=str(dest), force=True)
    assert seen["url"].endswith("o.jsonl.gz")
    assert [c["name"] for c in carddb._rows_json(got)] == ["Sol Ring"]
