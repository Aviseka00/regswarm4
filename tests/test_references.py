import json
import unittest
from unittest.mock import patch
from regswarm import references


class ReferenceTests(unittest.TestCase):
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
