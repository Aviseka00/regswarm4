"""Authenticated, loopback-only live analysis service."""
import argparse
import hmac
import json
import os
import threading
import uuid
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from . import auth, audit, db, export, facilities, intake, llm, pipeline, roster, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = {}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "RegSwarm/1.0"

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def _json(self, obj, code=200, cookie=None):
        payload = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def _token(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            return cookies["regswarm_session"].value if "regswarm_session" in cookies else ""
        except Exception:
            return ""

    def _body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 5000000:
            raise ValueError("Invalid request size")
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("application/json required")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def _boundary(self, mutation=False):
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in hosts:
            self._json({"error": "Unrecognized host"}, 403)
            return False
        if mutation and (self.headers.get("Origin") not in (None, "http://" + host) or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self._json({"error": "Cross-origin request rejected"}, 403)
            return False
        return True

    def _run(self, identifier):
        with LOCK:
            run = RUNS.get(identifier)
            if not run:
                con = db.connect()
                try:
                    run = store.load(con, identifier)
                finally:
                    con.close()
                if run:
                    RUNS[identifier] = run
        if not run or run.mode != "live" or run.case.get("synthetic") is not False:
            self._json({"error": "Unknown production run"}, 404)
            return None
        return run

    def do_GET(self):
        if not self._boundary():
            return
        url = urlparse(self.path)
        path = url.path
        if path in ("/", "/index.html", "/facilities"):
            filename = "facilities.html" if path == "/facilities" else "index.html"
            with open(os.path.join(ROOT, "static", filename), "rb") as source:
                payload = source.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        session = auth.resolve(self._token())
        if path == "/api/status":
            con = db.connect()
            try:
                account_ready = auth.configured(con)
                corpus = db.corpus_stats(con) if session else {"sections": 0}
                cases = intake.recent(con) if session else []
            finally:
                con.close()
            providers = llm.provider_status()
            return self._json({"authenticated": bool(session), "account_ready": account_ready,
                "user": {k: session[k] for k in ("username", "name", "role")} if session else None,
                "csrf": session["csrf"] if session else None, "corpus": corpus, "corpus_ready": corpus["sections"] > 0,
                "cases": cases, "providers": providers, "live_available": any(p["ready"] for p in providers),
                "roster": [a for a in roster.ROSTER if a["implemented"]], "clusters": [{"key": k, "label": label, "tier": tier} for k, label, tier in roster.CLUSTERS]})
        if not session:
            return self._json({"error": "Sign in required"}, 401)
        if path == "/api/facilities" or path.startswith("/api/facilities/"):
            con = db.connect()
            try:
                parts = path.strip("/").split("/")
                if len(parts) == 2:
                    return self._json({"facilities": facilities.listing(con)})
                if len(parts) == 3:
                    return self._json(facilities.library(con, parts[2]))
                if len(parts) == 4 and parts[3] == "search":
                    args = parse_qs(url.query)
                    return self._json(facilities.search(con, parts[2], args.get("q", [""])[0], args.get("class_id", [None])[0]))
                return self._json({"error": "Not found"}, 404)
            except ValueError as error:
                return self._json({"error": str(error)}, 400)
            finally:
                con.close()
        if path == "/api/runs":
            con = db.connect()
            try:
                return self._json({"runs": store.recent(con, production_only=True)})
            finally:
                con.close()
        pieces = path.strip("/").split("/")
        if len(pieces) != 4 or pieces[:2] != ["api", "run"]:
            return self._json({"error": "Not found"}, 404)
        run = self._run(pieces[2])
        if not run:
            return
        operation = pieces[3]
        if operation == "events":
            try:
                cursor = int(parse_qs(url.query).get("since", [self.headers.get("Last-Event-ID", "0")])[0])
                if not 0 <= cursor <= len(run.events):
                    raise ValueError()
            except ValueError:
                return self._json({"error": "Invalid event cursor"}, 400)
            return self._sse(run, cursor, self._token())
        if operation == "state":
            return self._json({"status": run.status, "version": run.version, "score": run.score, "signature": run.signature})
        if operation == "review":
            return self._json({"packet": run.review_packet, "metrics": run.metrics, "status": run.status,
                               "doc_sha256": pipeline.sha(run.document) if run.document else None})
        if operation == "audit":
            con = db.connect()
            try:
                intact, total, _ = audit.verify_chain(con)
                return self._json({"intact": intact, "total_entries": total, "entries": audit.entries(con, run.id)})
            finally:
                con.close()
        if operation == "export.docx":
            if not run.document:
                return self._json({"error": "No document available"}, 409)
            if run.signature and run.signature.get("doc_sha256") and run.signature["doc_sha256"] != pipeline.sha(run.document):
                return self._json({"error": "Signed document integrity check failed"}, 409)
            payload = export.build_docx(run.document, run.signature, "Sources and versions are recorded in the evidence review packet.")
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition", f'attachment; filename="{run.id}_{run.version}.docx"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._json({"error": "Not found"}, 404)

    def _sse(self, run, cursor, token):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            while auth.resolve(token):
                with run.cond:
                    if cursor >= len(run.events):
                        if any(e["type"] in ("done", "error") for e in run.events):
                            return
                        run.cond.wait(timeout=10)
                    batch = run.events[cursor:]
                if not batch:
                    self.wfile.write(b": keepalive\n\n")
                for event in batch:
                    self.wfile.write(f"id: {event['i'] + 1}\n".encode() + b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n")
                    cursor = event["i"] + 1
                self.wfile.flush()
                if any(e["type"] in ("done", "error") for e in batch) and cursor >= len(run.events):
                    return
        except (BrokenPipeError, ConnectionError, OSError):
            return

    def do_POST(self):
        if not self._boundary(mutation=True):
            return
        try:
            body = self._body()
        except (ValueError, TypeError):
            return self._json({"error": "Invalid JSON body or content type"}, 400)
        path = urlparse(self.path).path
        if path == "/api/login":
            if not isinstance(body.get("username"), str) or not isinstance(body.get("password"), str) or len(body["password"]) > 200:
                return self._json({"error": "Username and password required"}, 400)
            con = db.connect()
            try:
                token, session = auth.login(con, body["username"], body["password"], self.client_address[0])
                audit.append(con, "AUTH", session["username"], "signed_in")
                return self._json({"ok": True}, cookie=f"regswarm_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800")
            except ValueError as error:
                return self._json({"error": str(error)}, 401)
            finally:
                con.close()
        session = auth.resolve(self._token())
        if not session:
            return self._json({"error": "Sign in required"}, 401)
        if not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            return self._json({"error": "Invalid request token"}, 403)
        if path == "/api/logout":
            auth.logout(self._token())
            return self._json({"ok": True}, cookie="regswarm_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if path == "/api/facilities" or path.startswith("/api/facilities/"):
            parts = path.strip("/").split("/")
            if not (len(parts) == 4 and parts[3] == "cases") and session["role"] != "admin":
                return self._json({"error": "Administrator role required to manage facilities and documents"}, 403)
            con = db.connect()
            try:
                if len(parts) == 2:
                    identifier = facilities.create(con, body, session["username"])
                    action = "facility_created"
                elif len(parts) == 4 and parts[3] == "classes":
                    identifier = facilities.category(con, parts[2], body)
                    action = "category_created"
                elif len(parts) == 4 and parts[3] == "documents":
                    identifier, digest = facilities.upload(con, parts[2], body, session["username"])
                    action = "document_uploaded"
                elif len(parts) == 4 and parts[3] == "cases":
                    case, digest = facilities.case(con, parts[2], body, session["username"])
                    identifier = case["id"]
                    action = "facility_case_created"
                else:
                    return self._json({"error":"Not found"},404)
                audit.append(con, identifier, session["username"], action, {"facility": parts[2] if len(parts)>2 else identifier})
                return self._json({"id":identifier},201)
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                return self._json({"error":str(error)},400)
            finally:
                con.close()
        if path == "/api/cases":
            con = db.connect()
            try:
                case, digest = intake.save(con, body.get("package"), session["username"])
                audit.append(con, case["id"], session["username"], "case_imported", {"sha256": digest})
                return self._json({"case_id": case["id"]}, 201)
            except ValueError as error:
                return self._json({"error": str(error)}, 400)
            finally:
                con.close()
        if path == "/api/run":
            if body.get("consent") is not True:
                return self._json({"error": "Confirm transmission of this case to the selected AI provider"}, 400)
            if body.get("mode", "live") != "live":
                return self._json({"error": "Scripted processing is unavailable"}, 400)
            provider = body.get("provider", "anthropic")
            if not any(p["id"] == provider and p["ready"] for p in llm.provider_status()):
                return self._json({"error": "Configure a live provider and supported model first"}, 409)
            if not isinstance(body.get("case"), str):
                return self._json({"error": "Select an imported case"}, 400)
            con = db.connect()
            try:
                if db.corpus_stats(con)["sections"] == 0:
                    return self._json({"error": "Load the regulatory corpus first"}, 409)
                case = intake.load(con, body["case"])
                case.update(provider=provider, initiated_by=session["username"])
                run = pipeline.Run("RUN-" + uuid.uuid4().hex, case, "live")
                with LOCK:
                    if sum(r.status == "running" for r in RUNS.values()) >= 2:
                        return self._json({"error": "Processing capacity reached"}, 429)
                    RUNS[run.id] = run
                    store.save(con, run)
                audit.append(con, run.id, session["username"], "run_requested", {"case": case["id"], "provider": provider, "provider_transmission_confirmed": True})
            except ValueError as error:
                return self._json({"error": str(error)}, 400)
            finally:
                con.close()
            threading.Thread(target=lambda: pipeline.execute(run, db.connect(), 0), daemon=True).start()
            return self._json({"run_id": run.id}, 202)
        pieces = path.strip("/").split("/")
        if len(pieces) == 4 and pieces[:2] == ["api", "run"] and pieces[3] == "decision":
            if session["role"] != "reviewer":
                return self._json({"error": "Reviewer role required"}, 403)
            run = self._run(pieces[2])
            if not run:
                return
            con = db.connect()
            try:
                if not isinstance(body.get("comment", ""), str):
                    raise ValueError("Comment must be text")
                if body.get("doc_sha256") != pipeline.sha(run.document):
                    raise ValueError("Document changed or was not reviewed; reopen Evidence review")
                if body.get("decision") == "approve":
                    claims = body.get("reviewed_claims", [])
                    issues = body.get("reviewed_issues", [])
                    if not isinstance(claims, list) or not all(isinstance(x, str) for x in claims) or not isinstance(issues, list) or not all(isinstance(x, str) for x in issues):
                        raise ValueError("Review confirmations must be arrays of identifiers")
                    required = {c["id"] for c in run.review_packet["claims"] if c["support_status"] == "interpretation_review_required"}
                    required_issues = {i["id"] for i in run.review_packet["issues"]}
                    if set(claims) != required or set(issues) != required_issues:
                        raise ValueError("Confirm every claim interpretation and critique finding in Evidence review before approval")
                    if required_issues and len(body.get("comment", "").strip()) < 20:
                        raise ValueError("Record a substantive review comment explaining the disposition of critique findings")
                    run.review_packet["review_confirmation"] = {"username": session["username"], "claim_ids": sorted(required), "issue_ids": sorted(required_issues)}
                event = pipeline.finalize(run, con, body.get("decision"), session["name"], body.get("comment", ""),
                                          body.get("acknowledge") is True, identity=session)
                return self._json(event)
            except ValueError as error:
                return self._json({"error": str(error)}, 409)
            finally:
                con.close()
        self._json({"error": "Not found"}, 404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"])
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    con = db.connect()
    try:
        store.recover_interrupted(con)
        print("RegSwarm · live evidence analysis")
        print("  reviewer accounts:", "configured" if auth.configured(con) else "setup required (see README.md)")
        print("  corpus sections:", db.corpus_stats(con)["sections"])
    finally:
        con.close()
    print("  providers:", ", ".join(p["id"] + (" ready" if p["ready"] else " setup required") for p in llm.provider_status()))
    url = f"http://127.0.0.1:{args.port}/"
    print("  open", url)
    try:
        service = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError:
        raise SystemExit("Port is occupied. Choose a different --port.")
    service.daemon_threads = True
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        service.server_close()


if __name__ == "__main__":
    main()
