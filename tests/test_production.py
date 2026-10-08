import base64
import copy
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from regswarm import auth, db, facilities, intake, llm, pipeline, roster, service, store
from test_workflow import package


class IntakeTests(unittest.TestCase):
    def test_synthetic_input_rejected(self):
        case = package()
        case["synthetic"] = True
        with self.assertRaises(ValueError):
            intake.validate(case)

    def test_duplicate_sources_rejected(self):
        case = package()
        case["documents"].append(copy.deepcopy(case["documents"][0]))
        with self.assertRaises(ValueError):
            intake.validate(case)

    def test_unsupported_authority_rejected(self):
        case = package()
        case["authority"] = "EMA"
        with self.assertRaises(ValueError):
            intake.validate(case)

    def test_scripted_provider_removed(self):
        with self.assertRaises(ValueError):
            llm.make_llm("scripted", {})

    def test_local_provider_completes_without_a_paid_call(self):
        model = llm.make_llm("live", {"provider": "local"})
        decomposed = model.call("decompose", {"input": {"observation": "Retained labels were found at line clearance.\nFill-weight checks were not recorded."}})
        self.assertEqual([item["id"] for item in decomposed["elements"]], ["E1", "E2"])
        draft = model.call("draft", {"input": {"elements": decomposed["elements"], "evidence": {"EV-SOP-1": {"label": "Cleaning SOP", "passages": [{"text": "Residue limits apply."}]}},
            "clause_library": {"21 CFR 211.192": "All drug product production and control records shall be reviewed."}}})
        kinds = [claim["kind"] for section in draft["sections"] for claim in section["claims"]]
        self.assertIn("site_fact", kinds)
        self.assertIn("regulatory", kinds)
        self.assertEqual([section["title"] for section in draft["sections"]], ["Query", "Response", "CAPA", "Risk assessment"])

    def test_the_report_states_the_query_without_the_index_preface(self):
        model = llm.make_llm("live", {"provider": "local"})
        observation = "Audit queries for Filling: The current version of 4 stored document(s) is indexed. Other facilities are included when they are the same product.\n1. Fill-weight checks were not recorded."
        draft = model.call("draft", {"input": {"observation": observation, "elements": [{"id": "E1", "text": "Fill-weight checks were not recorded."}], "evidence": {}}})
        self.assertEqual([section["title"] for section in draft["sections"]], ["Query", "Response", "CAPA", "Risk assessment"])
        query = " ".join(claim["text"] for claim in draft["sections"][0]["claims"])
        response = " ".join(claim["text"] for claim in draft["sections"][1]["claims"])
        self.assertIn("Fill-weight checks were not recorded.", query)
        self.assertNotIn("stored document", query)
        self.assertIn("This response is against the query above.", response)
        self.assertEqual(model.calls[0]["usage"]["output_tokens"], 0)

    def test_roster_lists_300_specialists(self):
        self.assertEqual(len(roster.ROSTER), 300)
        self.assertIn("T102", roster.BY_ID)
        self.assertIn("LIB01", roster.BY_ID)
        self.assertEqual(roster.BY_ID["I01"]["name"], "Line clearance")

    def test_line_clearance_query_raises_a_deviation_against_the_linked_record(self):
        model = llm.make_llm("live", {"provider": "local"})
        observation = "Retained labels were found at line clearance."
        classified = model.call("classify", {"input": {"observation": observation, "evidence": {}}})
        self.assertIn("I01", classified["activate"])
        self.assertIn("K01", classified["activate"])
        draft = model.call("draft", {"input": {
            "observation": observation,
            "elements": [{"id": "E1", "text": observation}],
            "evidence": {"EV-BMR-1": {"label": "Filling batch record", "kind": "BMR",
                "passages": [{"text": "Line clearance and the stopper lot are recorded before filling."}]}},
            "clause_library": {"21 CFR 211.192": "All drug product production and control records shall be reviewed."},
            "public_references": {"catalog": [{"body": "ICH", "title": "ICH quality guidelines", "url": "https://www.ich.org/page/quality-guidelines"}],
                                  "recalls": [{"recall_number": "D-0205-2024", "reason": "CGMP deviations including line clearance."}]}}})
        text = " ".join(claim["text"] for section in draft["sections"] for claim in section["claims"])
        self.assertIn("Raise a deviation", text)
        self.assertIn("Filling batch record", text)
        self.assertIn("root-cause analysis", text)
        self.assertIn("ICH quality guidelines", text)
        self.assertIn("D-0205-2024", text)
        self.assertIn("21 CFR 211.192", text)

    def test_oos_query_opens_a_laboratory_investigation(self):
        model = llm.make_llm("live", {"provider": "local"})
        draft = model.call("draft", {"input": {
            "observation": "The assay was out of specification and a retest was started before the method and sample preparation were checked.",
            "elements": [{"id": "E1", "text": "The assay was out of specification."}],
            "evidence": {"EV-OOS-1": {"label": "Assay OOS worksheet", "kind": "OOS", "passages": [{"text": "The assay result was recorded."}]}},
            "clause_library": {"21 CFR 211.160": "Laboratory controls shall include the establishment of scientifically sound specifications."}}})
        text = " ".join(claim["text"] for section in draft["sections"] for claim in section["claims"]).lower()
        self.assertIn("oos investigation", text)
        self.assertIn("assay oos worksheet", text)

    def test_change_control_names_the_procedure_that_omits_the_field(self):
        model = llm.make_llm("live", {"provider": "local"})
        observation = "Fill-weight checks were not recorded during line clearance."
        evidence = {
            "EV-SOP-9": {"label": "Line clearance SOP", "kind": "SOP",
                         "passages": [{"text": "Line clearance is completed before filling starts."}]},
            "EV-BMR-9": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": "Line clearance was signed before filling started."}]},
        }
        changes = model.call("change_control", {"input": {"observation": observation, "evidence": evidence, "elements": [{"id": "E1", "text": observation}]}})
        self.assertEqual(len(changes["items"]), 1)
        self.assertEqual(changes["items"][0]["targets"], ["SOP-9"])
        self.assertIn("fill", changes["items"][0]["title"].lower())
        draft = model.call("draft", {"input": {"observation": observation, "evidence": evidence, "elements": [{"id": "E1", "text": observation}]}})
        text = " ".join(claim["text"] for section in draft["sections"] for claim in section["claims"])
        self.assertIn("Line clearance SOP", text)
        self.assertIn("Filling batch record", text)
        self.assertIn("not a completed ICH Q9 score", text)

    def test_aligned_records_do_not_propose_a_change_or_capa(self):
        model = llm.make_llm("live", {"provider": "local"})
        observation = "Fill-weight checks were not recorded."
        evidence = {
            "EV-SOP-2": {"label": "Filling SOP", "kind": "SOP",
                         "passages": [{"text": "Fill-weight checks are recorded before the batch continues."}]},
            "EV-BMR-2": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": "Fill-weight checks are recorded on the filling batch record."}]},
        }
        changes = model.call("change_control", {"input": {"observation": observation, "evidence": evidence, "elements": [{"id": "E1", "text": observation}]}})
        self.assertEqual(changes["items"], [])
        draft = model.call("draft", {"input": {"observation": observation, "evidence": evidence, "elements": [{"id": "E1", "text": observation}]}})
        text = " ".join(claim["text"] for section in draft["sections"] for claim in section["claims"])
        self.assertIn("do not confirm the discrepancy", text)
        self.assertIn("not proposed", text.lower())

    def test_a_form_that_names_a_field_is_not_a_completed_entry(self):
        observation = "Fill-weight checks were not recorded during line clearance."
        finding = llm.discrepancy(observation, {
            "EV-BMR-02": {"label": "Executed batch record, filling", "kind": "BMR",
                          "passages": [{"text": "The filling batch record records line clearance, stopper lot, fill-weight checks, and the environmental monitoring session."}]},
            "EV-DEV-01": {"label": "Line clearance deviation", "kind": "Deviation",
                          "passages": [{"text": "Line clearance found retained labels from the previous lot."}]},
        })
        self.assertEqual(finding["stance"], "entry_not_shown")
        self.assertFalse(finding["propose_capa"])
        self.assertFalse(finding["propose_change"])
        self.assertIn("describes the form", finding["pair"])
        self.assertIn("not confirmed as a repeat", finding["occurrence"])
        self.assertIn("Related history only", finding["occurrence"])
        self.assertIn("Line clearance deviation", finding["occurrence"])

    def test_field_table_follows_the_batch_row(self):
        blank = llm.discrepancy("Fill-weight checks were not recorded.", {
            "EV-SOP-1": {"label": "Filling SOP", "kind": "SOP",
                         "passages": [{"text": "Fill-weight checks are required before the lot continues."}]},
            "EV-BMR-1": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": "Fill-weight | blank | 9.5-10.5 g |"}]},
        })
        self.assertTrue(blank["propose_capa"])
        self.assertFalse(blank["propose_change"])
        self.assertEqual(blank["fields"][0]["signoff"], "absent")
        self.assertIn("Blank", blank["fields"][0]["entry"])
        self.assertEqual(blank["fields"][0]["route"], "Propose a CAPA")
        done = llm.discrepancy("Fill-weight checks were not recorded.", {
            "EV-BMR-1": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": "Fill-weight | 10.2 g | 9.5-10.5 g | signed"}]},
        })
        self.assertFalse(done["propose_capa"])
        self.assertFalse(done["propose_change"])
        self.assertEqual(done["fields"][0]["route"], "Stop")
        self.assertEqual(done["fields"][0]["signoff"], "present")
        self.assertIn("do not confirm the discrepancy", done["pair"])

    def test_a_linked_record_is_not_scored_as_an_unresolved_defect(self):
        held = llm.local_answer("redteam", {"observation": "Fill-weight checks were not recorded.", "evidence": {
            "EV-BMR-1": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": "The filling batch record records fill-weight checks."}]}}})
        self.assertEqual(held["issues"], [])
        unsupported = llm.local_answer("redteam", {"observation": "Fill-weight checks were not recorded.", "evidence": {}})
        self.assertEqual(unsupported["issues"][0]["severity"], "high")

    def test_a_table_row_past_the_first_page_is_read(self):
        filler = "Line clearance was signed before filling started.\n" * 80
        finding = llm.discrepancy("Fill-weight checks were not recorded.", {
            "EV-SOP-1": {"label": "Filling SOP", "kind": "SOP",
                         "passages": [{"text": "Fill-weight checks are required before the lot continues."}]},
            "EV-BMR-1": {"label": "Filling batch record", "kind": "BMR",
                         "passages": [{"text": filler}, {"text": "Fill-weight | blank | 9.5-10.5 g |"}]},
        })
        self.assertTrue(finding["propose_capa"])
        self.assertIn("Blank", finding["fields"][0]["entry"])

    def test_occurrence_uses_another_retrieved_deviation(self):
        observation = "Retained labels were found at line clearance again."
        alone = llm.discrepancy(observation, {"EV-BMR-1": {"label": "Filling batch record", "kind": "BMR", "passages": [{"text": "Line clearance was signed."}]}})
        self.assertIn("not confirmed", alone["occurrence"])
        repeated = llm.discrepancy(observation, {
            "EV-BMR-1": {"label": "Filling batch record", "kind": "BMR", "passages": [{"text": "Line clearance was signed."}]},
            "EV-DEV-1": {"label": "Earlier line clearance deviation", "kind": "Deviation", "passages": [{"text": "Retained labels were found at line clearance on the previous lot."}]},
        })
        self.assertIn("Earlier line clearance deviation", repeated["occurrence"])

    def test_rejected_proposal_is_removed_from_the_response_text(self):
        draft = {"sections": [{"id": "risk", "claims": [{"id": "c-risk", "text": "Severity is Medium."}]}]}
        llm.stamp_proposal(draft, "risk", "reject")
        self.assertEqual(draft["sections"][0]["claims"][0]["text"], "QA rejected this proposal. It is not part of the approved response.")
        llm.stamp_proposal(draft, "risk", "confirm")
        self.assertIn("QA confirmed this proposal.", draft["sections"][0]["claims"][0]["text"])
        self.assertIn("Severity is Medium.", draft["sections"][0]["claims"][0]["text"])

    def test_ollama_provider_uses_the_local_model(self):
        payload = json.dumps({"message": {"content": json.dumps({"elements": [{"id": "E1", "text": "Labels remained at line clearance."}], "queries": [], "doc_queries": {}})},
                              "done": True, "done_reason": "stop", "prompt_eval_count": 12, "eval_count": 8}).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return payload

        with patch("regswarm.llm.ollama_models", return_value=["qwen2.5:1.5b"]), patch("urllib.request.urlopen", return_value=Response()):
            model = llm.make_llm("live", {"provider": "ollama"})
            result = model.call("decompose", {"input": {"observation": "Labels remained at line clearance."}})
        self.assertEqual(result["elements"][0]["id"], "E1")
        self.assertEqual(model.calls[0]["provider"], "ollama")

    def test_ollama_uses_the_model_for_mapping_only(self):
        class Marker:
            model_roles = llm.OllamaLLM.model_roles

        self.assertTrue(llm.model_needed(Marker(), "map"))
        self.assertFalse(llm.model_needed(Marker(), "draft"))
        self.assertFalse(llm.model_needed(Marker(), "redteam"))
        self.assertTrue(llm.model_needed(object(), "redteam"))

    def test_ollama_prompt_drops_the_long_case_context(self):
        huge = {"observation": "x" * 5000, "case_context": {"notes": "n" * 8000},
                "elements": [{"id": "E1", "text": "y" * 2000}],
                "clause_library": {f"21 CFR 211.{index}": "z" * 2000 for index in range(20)},
                "evidence": {f"EV-D{index}": {"label": "L" * 500, "passages": [{"text": "p" * 2000}]} for index in range(20)}}
        text = llm.ollama_prompt("draft", huge)
        self.assertLess(len(text), 5000)
        self.assertNotIn("case_context", text)
        self.assertIn("21 CFR 211.0", text)
        self.assertNotIn("21 CFR 211.8", text)

    def test_ollama_is_offered_when_a_model_is_installed(self):
        with patch("regswarm.llm.ollama_models", return_value=["qwen2.5:1.5b"]):
            status = llm.provider_status()
        self.assertEqual(status[0]["id"], "local")
        self.assertTrue(any(item["id"] == "ollama" and item["ready"] for item in status))

    def test_incomplete_model_json_rejected(self):
        with self.assertRaises(ValueError):
            llm.parse_output("draft", '{"sections":[')

    def test_restart_marks_running_job_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            con = db.connect(os.path.join(directory, "db.sqlite"))
            try:
                run = pipeline.Run("TEST-INTERRUPTED", intake.validate(package()), "live")
                store.save(con, run)
                store.recover_interrupted(con)
                self.assertEqual(store.load(con, run.id).status, "interrupted")
            finally:
                con.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patch = patch.object(db, "DB_PATH", os.path.join(self.directory.name, "service.db"))
        self.patch.start()
        self.providers = patch("regswarm.llm.provider_status", return_value=[{"id": "groq", "model": "test", "ready": True}])
        self.providers.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        con = db.connect()
        auth.provision(con, "reviewer-test", "Test Reviewer", "test-only-password-123")
        auth.provision(con, "analyst-test", "Test Analyst", "test-only-password-456", "analyst")
        con.close()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.providers.stop()
        self.patch.stop()
        self.directory.cleanup()
        with auth.LOCK:
            auth.SESSIONS.clear()
            auth.FAILURES.clear()
        service.RUNS.clear()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        all_headers = {"Content-Type": "application/json"}
        all_headers.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, all_headers)
        response = connection.getresponse()
        content = json.loads(response.read())
        result = response.status, content, dict(response.getheaders())
        connection.close()
        return result

    def login(self, analyst=False):
        username = "analyst-test" if analyst else "reviewer-test"
        password = "test-only-password-456" if analyst else "test-only-password-123"
        status, _, headers = self.request("POST", "/api/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";")[0]
        _, state, _ = self.request("GET", "/api/status", headers={"Cookie": cookie})
        return {"Cookie": cookie, "X-CSRF-Token": state["csrf"]}

    def test_private_api_requires_sign_in(self):
        self.assertEqual(self.request("GET", "/api/runs")[0], 401)

    def test_csrf_and_origin_enforced(self):
        headers = self.login()
        self.assertEqual(self.request("POST", "/api/cases", {"package": package()}, {"Cookie": headers["Cookie"]})[0], 403)
        headers["Origin"] = "https://other.example"
        self.assertEqual(self.request("POST", "/api/cases", {"package": package()}, headers)[0], 403)

    def test_authenticated_intake_and_no_demo_cases(self):
        headers = self.login()
        status, result, _ = self.request("POST", "/api/cases", {"package": package()}, headers)
        self.assertEqual(status, 201)
        _, state, _ = self.request("GET", "/api/status", headers=headers)
        self.assertEqual([c["id"] for c in state["cases"]], [result["case_id"]])
        self.assertFalse(state["cases"][0]["synthetic"])

    def test_analyst_cannot_approve(self):
        headers = self.login(analyst=True)
        self.assertEqual(self.request("POST", "/api/run/anything/decision", {}, headers)[0], 403)

    def test_several_audits_start_together(self):
        headers = self.login()
        identifiers = []
        for title in ("First audit", "Second audit"):
            pack = package()
            pack["title"] = title
            status, result, _ = self.request("POST", "/api/cases", {"package": pack}, headers)
            self.assertEqual(status, 201)
            identifiers.append(result["case_id"])
        started = []

        def finish(run, connection, speed=0):
            started.append(run.case["title"])
            run.status = "awaiting_review"
            connection.close()

        with patch("regswarm.db.corpus_stats", return_value={"sections": 1}), patch("regswarm.pipeline.execute", finish):
            status, result, _ = self.request("POST", "/api/run", {"cases": identifiers, "consent": True, "provider": "groq"}, headers)
            for _ in range(40):
                if len(started) >= 2:
                    break
                time.sleep(0.05)
        self.assertEqual(status, 202)
        self.assertEqual(result["count"], 2)
        self.assertEqual(sorted(item["title"] for item in result["runs"]), ["First audit", "Second audit"])
        self.assertEqual(sorted(started), ["First audit", "Second audit"])

    def test_scripted_run_and_unconsented_run_rejected(self):
        headers = self.login()
        self.assertEqual(self.request("POST", "/api/run", {"mode": "scripted", "consent": True}, headers)[0], 400)
        self.assertEqual(self.request("POST", "/api/run", {"provider": "groq"}, headers)[0], 400)


    def test_reviewer_cannot_manage_facility_library(self):
        headers = self.login()
        self.assertEqual(self.request("POST", "/api/facilities", {}, headers)[0],403)

    def test_admin_creates_facility_and_default_categories(self):
        con = db.connect()
        try:
            auth.provision(con,"admin-test","Test Administrator","test-admin-password-123","admin")
        finally:
            con.close()
        status,_,response = self.request("POST","/api/login",{"username":"admin-test","password":"test-admin-password-123"})
        self.assertEqual(status,200)
        headers = {"Cookie":response["Set-Cookie"].split(";")[0]}
        _,state,_ = self.request("GET","/api/status",headers=headers)
        headers["X-CSRF-Token"] = state["csrf"]
        status,result,_ = self.request("POST","/api/facilities",{},headers)
        self.assertEqual(status,201)
        status,library,_ = self.request("GET","/api/facilities/"+result["id"],headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(len(library["classes"]),8)

    def test_batch_submits_every_query(self):
        con = db.connect()
        try:
            auth.provision(con, "admin-test", "Test Administrator", "test-admin-password-123", "admin")
            first = facilities.create(con, {"name": "Filling"}, "admin-test")
            second = facilities.create(con, {"name": "Compression"}, "admin-test")
            for facility, document_id in ((first, "SOP-01"), (second, "BMR-01")):
                class_id = facilities.library(con, facility)["classes"][0]["id"]
                facilities.upload(con, facility, {"class_id": class_id, "document": {"id": document_id, "title": "Record", "version": "1", "date": "2026-10-01", "status": "Approved", "source": "DMS/01"}, "filename": "source.txt", "file": base64.b64encode(b"Line clearance and yield are recorded.").decode()}, "admin-test")
        finally:
            con.close()
        status, _, response = self.request("POST", "/api/login", {"username": "admin-test", "password": "test-admin-password-123"})
        self.assertEqual(status, 200)
        headers = {"Cookie": response["Set-Cookie"].split(";")[0]}
        _, state, _ = self.request("GET", "/api/status", headers=headers)
        headers["X-CSRF-Token"] = state["csrf"]
        started = []

        def finish(run, connection, speed=0):
            started.append(run.case["site_name"])
            run.status = "awaiting_review"
            connection.close()

        with patch("regswarm.db.corpus_stats", return_value={"sections": 1}), patch("regswarm.pipeline.execute", finish):
            status, result, _ = self.request("POST", "/api/audits", {"consent": True, "provider": "groq", "items": [
                {"facility_id": first, "query": "Retained labels were found at line clearance.", "product_class": "Sterile drug product"},
                {"facility_id": second, "query": "The batch record did not show the yield.", "product_class": "Oral solid dosage"},
            ]}, headers)
            for _ in range(40):
                if len(started) >= 2:
                    break
                time.sleep(0.05)
        self.assertEqual(status, 201)
        self.assertEqual(result["count"], 2)
        self.assertEqual(sorted(item["facility"] for item in result["runs"]), ["Compression", "Filling"])
        self.assertEqual(sorted(started), ["Compression", "Filling"])
