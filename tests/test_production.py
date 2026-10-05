import copy
import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from regswarm import auth, db, intake, llm, pipeline, service, store
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
