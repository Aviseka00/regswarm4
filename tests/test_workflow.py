"""Trust boundaries and a complete offline review lifecycle."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from regswarm import db, intake, llm, pipeline, store, verifier


def package():
    # Test-only input; never inserted into the application's corpus or case store.
    return {"title": "Test procedure review", "observation": "Written production procedures shall be followed and deviations recorded and justified.",
            "site_name": "Unit test site", "product_class": "Drug product", "authority": "US FDA", "synthetic": False,
            "documents": [{"id": "SOP-PROC-01", "title": "Written production procedures", "version": "2", "date": "2026-09-20",
                           "status": "Effective", "group": "SOP", "source": "Unit test fixture",
                           "sections": [{"ref": "7.1", "text": "Written production procedures shall be followed. Deviations are recorded and justified."}]}]}


class FakeProvider:
    """Test double for provider I/O, not a runtime generation mode."""
    model = "test-provider"
    label = "Test provider"
    calls = []

    def call(self, role, context_):
        data = context_["input"]
        if role == "classify":
            return {"authority": "US FDA", "document_type": "Observation", "product_class": "Drug", "domains": [], "activate": []}
        if role == "decompose":
            return {"elements": [{"id": "E1", "text": package()["observation"]}], "doc_queries": {"E1": "written production procedures"}}
        if role == "map":
            self.ref = "21 CFR 211.100(b)" if "21 CFR 211.100(b)" in data["clause_library"] else next(iter(data["clause_library"]))
            return {"items": [{"element": "E1", "ref": self.ref, "rationale": "Procedure control"}]}
        if role == "frame":
            return {"sections": [{"id": "basis", "title": "Basis", "purpose": "Procedure review", "elements": ["E1"]}]}
        if role == "rca":
            return {"root_causes": [], "whys": [], "categories": {}}
        if role == "change_control":
            return {"items": []}
        if role == "capa":
            return {lane: [] for lane in ("correction", "corrective", "preventive", "effectiveness")}
        if role == "draft":
            return {"sections": [{"id": "basis", "title": "Basis", "claims": [
                {"id": "c1", "kind": "regulatory", "text": "Written procedures must be followed.", "cites": [{"ref": self.ref}], "elements": ["E1"]},
                {"id": "c2", "kind": "site_fact", "text": "The supplied procedure describes deviation recording.", "evidence": ["EV-SOP-PROC-01"], "elements": ["E1"]}]}]}
        if role == "redteam":
            return {"issues": []}
        if role == "revise":
            return {"replace": {}, "add": [], "resolves": []}
        raise AssertionError(role)


class OutputValidation(unittest.TestCase):
    def test_unknown_claim_kind_rejected(self):
        with self.assertRaises(ValueError):
            llm.validate("draft", {"sections": [{"id": "s", "title": "S", "claims": [
                {"id": "c", "text": "unsupported", "kind": "anything"}]}]})

    def test_duplicate_claim_ids_rejected(self):
        claim = {"id": "c", "text": "proposed", "kind": "action"}
        with self.assertRaises(ValueError):
            llm.validate("draft", {"sections": [{"id": "s", "title": "S", "claims": [claim, claim]}]})

    def test_case_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            pipeline.load_case("../data/corpus")

    def test_verifier_rejects_missing_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            con = db.connect(os.path.join(directory, "test.db"))
            try:
                result = verifier.verify_claim(con, {"id": "bad"}, set())
                self.assertEqual(result["status"], "removed")
            finally:
                con.close()


class Workflow(unittest.TestCase):
    def test_context_review_persistence_and_approval(self):
        corpus = os.path.join(db.ROOT, "data", "corpus.db")
        if not os.path.exists(corpus):
            self.skipTest("Full workflow requires installed demo corpus")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "run.db")
            target = sqlite3.connect(path)
            source = sqlite3.connect("file:" + corpus.replace("\\", "/") + "?mode=ro", uri=True)
            source.backup(target)
            source.close()
            target.close()
            case = intake.validate(package())
            run = pipeline.Run("TEST-CONTEXT", case, "live")
            with patch("regswarm.llm.make_llm", return_value=FakeProvider()):
                pipeline.execute(run, db.connect(path), speed=0)
            self.assertEqual(run.status, "awaiting_review", [e for e in run.events if e["type"] == "error"])
            self.assertTrue(run.review_packet["elements"][0]["passages"])
            self.assertTrue(run.review_packet["claims"])
            self.assertTrue(all(i["status"] == "review_required" for i in run.review_packet["issues"]))
            con = db.connect(path)
            try:
                restored = store.load(con, run.id)
                self.assertEqual(restored.document, run.document)
                self.assertEqual(restored.review_packet, run.review_packet)
                with self.assertRaises(ValueError):
                    pipeline.finalize(restored, con, "approve", "Reviewer", "", False)
                identity = {"username": "test-reviewer", "role": "reviewer"}
                pipeline.finalize(restored, con, "approve", "Reviewer", "Reviewed", True, identity=identity)
                self.assertEqual(store.load(con, run.id).status, "approved")
                with self.assertRaises(ValueError):
                    pipeline.finalize(restored, con, "approve", "Other", "", True)
            finally:
                con.close()
