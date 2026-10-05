"""Offline unit tests. They use an invented 'Part 999' fixture (not real regulation text),
so they run anywhere with no corpus and no network:   python -m unittest discover -s tests -v
"""
import datetime, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "ingest"))
from parse_ecfr import parse_xml
from regswarm import analytics, audit, db, export, retrieval, verifier
import fetch_ecfr

FIX = os.path.join(ROOT, "tests", "fixture_part999.xml")
TODAY = datetime.date(2026, 9, 20)


def make_db():
    d = tempfile.mkdtemp()
    con = db.connect(os.path.join(d, "t.db"))
    fetch_ecfr.load(con, 999, parse_xml(open(FIX, "rb").read()), "2026-09-01", "file:fixture")
    return con


class Parser(unittest.TestCase):
    def test_paragraph_paths(self):
        secs = {s["section"]: s for s in parse_xml(open(FIX, "rb").read())}
        paths = [p for p, _ in secs["999.20"]["paras"]]
        self.assertIn("b/2/i", paths); self.assertIn("b/2/iii", paths); self.assertIn("c", paths)
        self.assertEqual(secs["999.30"]["status"], "reserved")
        self.assertTrue(secs["999.10"]["cita"].startswith("[1 FR 1"))


class Verifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.con = make_db()

    def v(self, ref, quote=None): return verifier.verify_citation(self.con, ref, quote, TODAY)

    def test_good_citation_with_quote(self):
        r = self.v("21 CFR 999.20(b)(2)(i)", "A system for monitoring environmental conditions in the fixture area")
        self.assertEqual(r["status"], "verified")
    def test_unknown_section(self):
        self.assertEqual(self.v("21 CFR 999.99(a)")["reason"], "21 CFR 999.99 does not exist in the corpus")
    def test_reserved_section_rejected(self):
        self.assertEqual(self.v("21 CFR 999.30")["status"], "failed")
    def test_missing_paragraph(self):
        r = self.v("21 CFR 999.10(z)"); self.assertEqual(r["status"], "failed"); self.assertIn("does not exist", r["reason"])
    def test_misquote_rejected(self):
        r = self.v("21 CFR 999.10(b)", "shall be followed within 30 days"); self.assertEqual(r["status"], "failed")
    def test_quote_in_section_but_wrong_paragraph(self):
        r = self.v("21 CFR 999.10(a)", "Fixture procedures shall be in writing")
        self.assertEqual(r["status"], "failed"); self.assertIn("not in the cited paragraph", r["reason"])
    def test_ellipsis_segments(self):
        self.assertEqual(self.v("21 CFR 999.40", "Any unexplained discrepancy ... whether or not the fixture batch has been distributed")["status"], "verified")
    def test_stale_corpus_is_advisory_not_fatal(self):
        r = verifier.verify_citation(self.con, "21 CFR 999.10(a)", None, datetime.date(2027, 6, 1))
        self.assertEqual(r["status"], "verified"); self.assertFalse(r["checks"][-1]["ok"])
    def test_claim_rules(self):
        reg = {"id": "c", "kind": "regulatory", "cites": []}
        self.assertEqual(verifier.verify_claim(self.con, reg, set(), TODAY)["status"], "removed")
        fact = {"id": "f", "kind": "site_fact", "evidence": ["EV-X"]}
        self.assertEqual(verifier.verify_claim(self.con, fact, {"EV-X"}, TODAY)["status"], "verified")
        self.assertEqual(verifier.verify_claim(self.con, fact, set(), TODAY)["status"], "removed")


class Retrieval(unittest.TestCase):
    def test_search_and_lookup(self):
        con = make_db()
        hits = retrieval.search(con, "monitoring environmental conditions fixture area", k=3)
        self.assertEqual(hits[0]["ref"], "21 CFR 999.20(b)(2)(i)")
        self.assertIsNone(retrieval.lookup(con, "21 CFR 999.30"))
        self.assertIn("999.40(a)", retrieval.lookup(con, "21 CFR 999.40(a)")["ref"])


class Audit(unittest.TestCase):
    def test_chain_detects_tampering(self):
        con = make_db()
        for i in range(5): audit.append(con, "C1", "agent", "act", {"i": i})
        self.assertEqual(audit.verify_chain(con)[:2], (True, 5))
        con.execute("UPDATE audit_log SET detail='{\"i\": 99}' WHERE seq=3"); con.commit()
        ok, n, bad = audit.verify_chain(con)
        self.assertFalse(ok); self.assertEqual(bad, 3)


class SiteAnalytics(unittest.TestCase):
    def test_numbers_are_computed_from_data(self):
        rows, site = analytics.load_site(os.path.join(ROOT, "cases", "demo_site"))
        an = analytics.analyze(rows, site)
        self.assertEqual((an["n_exc"], an["hot_loc"], an["hot_n"]), (10, "FL2-A1", 7))
        self.assertEqual(an["n_closed_no_rc"], 9)
        self.assertEqual(an["human_flora_pct"], 90)


class Export(unittest.TestCase):
    def test_docx_is_valid_zip(self):
        import io, zipfile
        doc = {"case_id": "X", "title": "T", "version": "v0.2", "synthetic": True, "observation": "obs",
               "sections": [{"id": "s", "title": "S", "claims": [{"id": "c1", "kind": "regulatory", "text": "a < b & c",
                             "cites": [{"ref": "21 CFR 999.10(a)", "quote": "q"}], "evidence": []}]}]}
        z = zipfile.ZipFile(io.BytesIO(export.build_docx(doc)))
        self.assertIn("a &lt; b &amp; c", z.read("word/document.xml").decode())


class SiteDocs(unittest.TestCase):
    """The synthetic QMS library: inventory, retrieval and cross-record findings are computed from the documents."""

    @classmethod
    def setUpClass(cls):
        from regswarm import sitedocs
        cls.sd = sitedocs
        cls.lib = sitedocs.load(os.path.join(ROOT, "cases", "demo_site"))
        rows, site = analytics.load_site(os.path.join(ROOT, "cases", "demo_site"))
        cls.an = analytics.analyze(rows, site)
        cls.rows = rows

    def test_inventory_counts_add_up(self):
        inv = self.sd.inventory(self.lib)
        self.assertEqual(inv["total"], len(self.lib["docs"]))
        self.assertEqual(sum(s["count"] for s in inv["systems"]), inv["total"])
        self.assertEqual(len({d["id"] for d in self.lib["docs"]}), inv["total"], "document ids must be unique")

    def test_search_finds_the_governing_procedure(self):
        idx = self.sd.Index(self.lib)
        hits = idx.search("environmental monitoring trend report monthly quarterly summary", 8)
        self.assertIn("SOP-EM-014", [h["doc_id"] for h in hits[:5]])
        self.assertTrue(all(0 <= h["relevance"] <= 100 for h in hits))

    def test_findings_are_derived_not_scripted(self):
        res = self.sd.analyze_docs(self.lib, self.an, self.rows)
        f = res["facts"]
        self.assertEqual(f["n_exc_bmr"], 9)
        self.assertEqual(f["n_dist"], 8)
        self.assertEqual(f["n_nonexc_lapsed"], 0)
        self.assertGreater(f["bmr_int_hot"], f["bmr_int_rest"])
        self.assertGreaterEqual(len(res["findings"]), 6)
        m = self.sd.impact_matrix(f, self.lib)
        self.assertEqual(len(m["columns"]), len(m["rows"][0]["levels"]))


class EventStream(unittest.TestCase):
    def test_payload_cannot_clobber_event_index(self):
        """Regression: a payload key named 'i' once overwrote the event index, so the SSE stream replayed forever."""
        from regswarm import pipeline
        run = pipeline.Run("T-IDX", pipeline.load_case("demo_em_483"), "scripted")
        run.emit("a"); run.emit("stage", n=5, i=99); run.emit("b")
        self.assertEqual([e["i"] for e in run.events], [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
