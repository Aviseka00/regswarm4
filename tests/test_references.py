import json
import unittest
from unittest.mock import patch
from regswarm import references


class ReferenceTests(unittest.TestCase):
    def test_incubator_qualification_links_the_guideline_bodies(self):
        found = references.subject("CO2 incubator qualification issue: the IQ OQ PQ was incomplete.")
        self.assertIn("incubator", found["meaning"].lower())
        bodies = {item["body"] for item in found["guidelines"]}
        self.assertTrue({"US FDA", "WHO", "EMA", "ICH"} <= bodies)
        self.assertTrue(any(item.get("cfr") == "21 CFR 211.63" for item in found["guidelines"]))
        self.assertNotIn("quotation", " ".join(item["note"] for item in found["guidelines"] if item["body"] != "US FDA").lower())
        home = references.impact("CO2 incubator qualification was incomplete.", "The CO2 incubator IQ protocol for this suite.", True)
        other = references.impact("CO2 incubator qualification was incomplete.", "Formulation suite. The CO2 incubator OQ is filed here.", False)
        unrelated = references.impact("CO2 incubator qualification was incomplete.", "Tablet compression yield was recorded.", False)
        self.assertEqual(home["kind"], "direct")
        self.assertEqual(other["kind"], "distant")
        self.assertIn("similar instrument or process", other["why"])
        self.assertEqual(unrelated["kind"], "none")
        cited = references.document_references(
            "Filling batch record. Perform the check per SOP-01 and STP-02. Master formula MFR-04 is attached.",
            [{"id": "FIL-SOP-01"}, {"id": "FIL-STP-02"}, {"id": "QC-MFR-04"}, {"id": "FIL-BMR-09"}])
        self.assertEqual(cited, ["FIL-SOP-01", "FIL-STP-02", "QC-MFR-04"])
    def test_catalog_names_the_bodies_and_the_best_api(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            result = references.lookup("")
        bodies = {item["body"] for item in result["catalog"]}
        self.assertTrue({"21 CFR", "WHO", "EMA", "ICH", "USP", "EP", "IP", "openFDA"} <= bodies)
        self.assertEqual(result["recommendation"]["best_public_api"], "openFDA drug enforcement")
        self.assertEqual(result["recommendation"]["best_for_the_response"], "21 CFR text already loaded in RegSwarm")

    def test_openfda_recall_is_context_and_a_failure_keeps_the_catalog(self):
        payload = json.dumps({"results": [{"reason_for_recall": "Labels from the prior lot remained.",
                                            "recall_number": "D-0001-2026", "classification": "Class II",
                                            "status": "Ongoing", "recalling_firm": "Example Labs"}]}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return payload

        with patch("urllib.request.urlopen", return_value=Response()):
            result = references.lookup("Retained labels were found at line clearance")
        self.assertEqual(result["recalls"][0]["recall_number"], "D-0001-2026")
        self.assertIn("clearance", result["term"])
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            failed = references.lookup("line clearance")
        self.assertEqual(failed["recalls"], [])
        self.assertGreaterEqual(len(failed["catalog"]), 8)
