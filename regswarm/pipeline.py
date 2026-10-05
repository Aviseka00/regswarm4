"""Live evidence workflow with deterministic retrieval, verification and audit.
Model output remains subject to an authenticated human review gate.
"""
import datetime
import hashlib
import json
import os
import re
import threading
import time

from . import audit, production, roster, store, verifier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "cases")


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class Run:
    def __init__(self, run_id, case, mode):
        self.id, self.case, self.mode = run_id, case, mode
        self.events, self.cond = [], threading.Condition()
        self.status = "running"
        self.draft = None
        self.version = "v0.1"
        self.claim_res = {}
        self.score = None
        self.document = None
        self.signature = None
        self.edges_seen = set()
        self.nodes_seen = {}
        self.t0 = time.time()
        self.case_context = {}
        self.review_packet = {}
        self.metrics = {"stages": [], "llm_calls": []}
        self.decision_lock = threading.Lock()

    def emit(self, type_, **data):
        with self.cond:
            ev = {**data, "i": len(self.events), "t": round(time.time() - self.t0, 2), "type": type_}
            self.events.append(ev)
            self.cond.notify_all()
        return ev


def load_case(case_id):
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", case_id):
        raise ValueError("Invalid case identifier")
    path = os.path.join(CASES, f"{case_id}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- helpers
class Ctx:
    def __init__(self, run, con, speed):
        self.run, self.con, self.speed = run, con, speed

    def wait(self, s):
        if self.speed > 0:
            time.sleep(s * self.speed)

    def log(self, agent, tag, text, wait=0.35):
        self.run.emit("log", agent=agent, tag=tag, text=text)
        self.wait(wait)

    def on(self, agent, label, wait=0.4):
        self.run.emit("agent_state", agent=agent, state="active", label=label)
        audit.append(self.con, self.run.id, agent, "activated", {"label": label})
        self.wait(wait)

    def off(self, agent, state="done"):
        self.run.emit("agent_state", agent=agent, state=state)

    def audit(self, actor, action, detail):
        audit.append(self.con, self.run.id, actor, action, detail)

    def stage(self, i):
        now = time.monotonic()
        if self.run.metrics["stages"]:
            self.run.metrics["stages"][-1]["seconds"] = round(now - self.stage_started, 3)
        self.stage_started = now
        name, sub = STAGES[i]
        self.run.metrics["stages"].append({"name": name, "seconds": None})
        self.run.emit("stage", n=i, name=name, sub=sub)
        audit.append(self.con, self.run.id, "system", "stage", {"i": i, "name": name})
        self.wait(0.25)

    def node(self, id_, label, cluster, kind, size=1, status=None, **extra):
        r = self.run
        if id_ in r.nodes_seen:
            return
        n = {"id": id_, "label": label, "cluster": cluster, "kind": kind, "size": size, "status": status, **extra}
        r.nodes_seen[id_] = n
        r.emit("graph_add", nodes=[n], edges=[])

    def nodes(self, items):
        r, fresh = self.run, []
        for n in items:
            if n["id"] not in r.nodes_seen:
                r.nodes_seen[n["id"]] = n
                fresh.append(n)
        if fresh:
            r.emit("graph_add", nodes=fresh, edges=[])
        return fresh

    def edge(self, s, t, kind, label=""):
        key = (s, t, kind)
        r = self.run
        if key in r.edges_seen or s not in r.nodes_seen or t not in r.nodes_seen:
            return
        r.edges_seen.add(key)
        r.emit("graph_add", nodes=[], edges=[{"s": s, "t": t, "kind": kind, "label": label}])

    def status(self, id_, status):
        if id_ in self.run.nodes_seen:
            self.run.nodes_seen[id_]["status"] = status
            self.run.emit("graph_status", id=id_, status=status)


def short_ref(ref):
    return ref.replace("21 CFR ", "")


def canon(ref):
    """Canonical form '21 CFR 211.42(c)(10)(iv)' so the same clause is one graph node."""
    p = verifier.parse_ref(ref)
    if not p:
        return ref
    sid, path = p
    return sid + "".join(f"({x})" for x in path.split("/")) if path else sid


# ---------------------------------------------------------------- main
def execute(run, con, speed=1.0):
    c = Ctx(run, con, 0)
    case = run.case
    try:
        if run.mode != "live":
            raise ValueError("Only live processing is supported")
        production.execute(run, c, case)
    except Exception as e:  # surface failures in the UI instead of hanging
        run.status = "error"
        run.emit("error", message=f"{type(e).__name__}: {e}")
    finally:
        if run.metrics["stages"]:
            run.metrics["stages"][-1]["seconds"] = round(time.monotonic() - c.stage_started, 3)
        run.metrics["elapsed_seconds"] = round(time.time() - run.t0, 3)
        store.save(con, run)
        con.close()


STAGES = [
    ("Upload", "Observation received, hashed and parsed."),
    ("Classify", "Routing by authority, document type and product class."),
    ("Decompose", "Splitting the observation into compliance elements."),
    ("Evidence sources", "Checking imported source metadata and document versions."),
    ("Index documents", "Indexing the documents supplied with this case."),
    ("Smart pull", "Ranking every document, extracting the relevant passages."),
    ("Regulations", "Retrieving and mapping clauses from the dated corpus."),
    ("Evidence context", "Linking selected passages to the observation elements."),
    ("Frame & RCA", "Building the response frame and the root-cause analysis."),
    ("Change control", "Proposing change controls and the documents they touch."),
    ("CAPA", "Correction, corrective, preventive and effectiveness plan."),
    ("Review scope", "Checking the proposed actions against supplied evidence."),
    ("Draft", "Drafting the response (v0.1) from the frame."),
    ("Verify", "Checking every citation against the corpus, by code."),
    ("Red-team", "Attacking the draft, revising to v0.2, re-verifying."),
    ("Review gate", "Evidence checks and unresolved findings, then a human decides."),
]

NODE_KIND = {"SOP": "sop", "Deviation": "deviation"}


def doc_kind(d):
    if d["type"] == "Trend report":
        return "trend"
    if d["id"].startswith("APS-"):
        return "aps"
    return NODE_KIND.get(d["group"], "doc")


def parse_observation(text):
    """Real extraction of the entities the swarm will route on (regex, not a model)."""
    ents, seen = [], set()

    def add(kind, val):
        if (kind, val) not in seen:
            seen.add((kind, val))
            ents.append({"kind": kind, "value": val})
    for m in re.finditer(r"SOP-[A-Z]{2}-\d{3}", text):
        add("Procedure", m.group())
    for m in re.finditer(r"Grade [A-D](?: \(ISO \d\))?", text):
        add("Grade", m.group())
    for m in re.finditer(r"Filling Line \d", text):
        add("Line", m.group())
    for m in re.finditer(r"stopper bowl", text, re.I):
        add("Location", "stopper bowl")
    for m in re.finditer(r"(?:first and second|first|second|third|fourth) quarters? of \d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)(?: and (?:January|February|March|April|May|June|July|August|September|October|November|December))? \d{4}|between \w+ and \w+ \d{4}", text):
        add("Period", m.group())
    for kw in ("environmental monitoring", "root cause", "no product impact", "trend report", "action limit", "batches"):
        if kw in text.lower():
            add("Topic", kw)
    return ents


def _day(due):
    m = re.search(r"(\d+)", str(due or ""))
    return int(m.group(1)) if m else 0


def apply_patch(draft, rev):
    existing = {cl["id"] for s in draft["sections"] for cl in s["claims"]}
    sections = {s["id"] for s in draft["sections"]}
    if set(rev.get("replace", {})) - existing:
        raise ValueError("Revision references an unknown claim")
    for addition in rev.get("add", []):
        if addition["section"] not in sections or addition["claim"]["id"] in existing:
            raise ValueError("Revision contains an unknown section or duplicate claim")
        existing.add(addition["claim"]["id"])
    rep = rev.get("replace", {})
    for s in draft["sections"]:
        s["claims"] = [rep.get(cl["id"], cl) for cl in s["claims"]]
    for a in rev.get("add", []):
        for s in draft["sections"]:
            if s["id"] == a["section"]:
                s["claims"].append(a["claim"])
                break


def link_and_verify(c, run, evidence, version, initial):
    """Citation & Evidence Linker (T305) then Citation Verifier (T401)."""
    con = c.con
    c.on("T305", f"Linking claims to clauses and evidence ({version})")
    for s in run.draft["sections"]:
        for cl in s["claims"]:
            cid = cl["id"]
            c.node(cid, cid, "RSP", "claim", size=1, title=cl["text"][:140], status="draft")
            for ct in cl.get("cites", []):
                ref = canon(ct["ref"])
                c.node(ref, short_ref(ref), "REG", "clause", size=1, status="cited")
                c.edge(cid, ref, "cites")
            for ev in cl.get("evidence", []):
                if ev in run.nodes_seen:
                    c.edge(cid, ev, "supports")
            for e in cl.get("elements", []):
                c.edge(cid, e, "addresses")
    c.log("T305", "EDGE", f"{len(run.edges_seen)} edges in the traceability graph", wait=0.4)
    c.off("T305")

    c.on("T401", f"Verifying every citation ({version})")
    total_cites = ok_cites = 0
    results = {}
    for s in run.draft["sections"]:
        for cl in s["claims"]:
            res = verifier.verify_claim(con, cl, set(evidence))
            results[cl["id"]] = res
            for ct in res["cites"]:
                total_cites += 1
                ok_cites += ct["status"] == "verified"
                tag = "PASS" if ct["status"] == "verified" else "FAIL"
                c.log("T401", tag, f"{ct['ref']} " + ("verified against corpus" if tag == "PASS" else f"REJECTED · {ct['reason']}"), wait=0.28 if tag == "PASS" else 0.7)
                if ct["status"] != "verified":
                    c.status(canon(ct["ref"]), "failed")
            if res["status"] == "removed":
                c.status(cl["id"], "failed")
                c.log("T401", "FAIL", f"{cl['id']} removed from draft · {res['reason']}", wait=0.5)
            else:
                c.status(cl["id"], "verified")
    run.claim_res = results
    run.emit("verify", version=version, results=results, total_cites=total_cites, ok_cites=ok_cites,
             removed=[k for k, v in results.items() if v["status"] == "removed"])
    c.audit("T401", "verified", {"version": version, "total": total_cites, "ok": ok_cites,
                                 "removed": [k for k, v in results.items() if v["status"] == "removed"]})
    c.off("T401")
    return {"total": total_cites, "ok": ok_cites}


def score(run, elements, issues, rev, first, final):
    all_claims = [cl for s in run.draft["sections"] for cl in s["claims"]]
    res = run.claim_res
    cite_total = final["total"] or 1
    cite_int = 100 * final["ok"] / cite_total
    addressed = {e for cl in all_claims if res[cl["id"]]["status"] != "removed" for e in cl.get("elements", [])}
    coverage = 100 * len([e for e in elements if e["id"] in addressed]) / max(1, len(elements))
    sf = [cl for cl in all_claims if cl.get("kind") == "site_fact"]
    ev_link = 100 * sum(1 for cl in sf if res[cl["id"]]["status"] == "verified") / max(1, len(sf))
    w = {"high": 3, "medium": 2, "low": 1}
    # A model's proposed fix is not an independently confirmed resolution.
    resolved = set()
    tot_w = sum(w.get(i["severity"], 1) for i in issues) or 1
    rt = 100 * sum(w.get(i["severity"], 1) for i in issues if i["id"] in resolved) / tot_w if issues else 100
    comps = [
        {"name": "Citation integrity", "value": round(cite_int), "weight": 35,
         "note": f"{final['ok']}/{final['total']} citations verified in v0.2 (first pass {first['ok']}/{first['total']})"},
        {"name": "Element coverage", "value": round(coverage), "weight": 25,
         "note": f"{len([e for e in elements if e['id'] in addressed])}/{len(elements)} observation elements answered"},
        {"name": "Evidence linkage", "value": round(ev_link), "weight": 20,
         "note": f"{sum(1 for cl in sf if res[cl['id']]['status'] == 'verified')}/{len(sf)} site facts tied to records"},
        {"name": "Red-team resolution", "value": round(rt), "weight": 20,
         "note": f"{len(resolved & {i['id'] for i in issues})}/{len(issues)} issues resolved (severity-weighted)"},
    ]
    comp = round(sum(x["value"] * x["weight"] for x in comps) / 100)
    open_items = []
    for i in issues:
        if i["id"] not in resolved:
            open_items.append(f"Red-team {i['id']} ({i['severity']}): {i['fix']}")
    removed = [k for k, v in res.items() if v["status"] == "removed"]
    for k in removed:
        open_items.append(f"Claim {k} still unverified and was removed from the document")
    for packet in run.review_packet.get("elements", []):
        open_items.extend(f"{packet['id']}: {gap}" for gap in packet["gaps"])
    stale = [ct for result in res.values() for ct in result["cites"] if any(c["advisory"] and not c["ok"] for c in ct["checks"])]
    if stale:
        open_items.append(f"{len(stale)} citation(s) have unconfirmed corpus currency")
    open_items.append("All CAPA commitments, owners and due dates need management confirmation before submission")
    rag, verdict = "green", "Ready for QA review"
    if comp < 90 or removed or any(i["severity"] == "high" and i["id"] not in resolved for i in issues):
        rag, verdict = "amber", "Review with care - open items"
    if comp < 75:
        rag, verdict = "red", "Escalate to subject-matter expert"
    return {"components": comps, "composite": comp, "rag": rag, "verdict": verdict, "open_items": open_items,
            "first_pass": first, "final": final}


def assemble(run, case):
    sections = []
    for s in run.draft["sections"]:
        claims = []
        for cl in s["claims"]:
            r = run.claim_res.get(cl["id"], {"status": "verified"})
            if r["status"] == "removed":
                continue
            claims.append({"id": cl["id"], "kind": cl.get("kind"), "text": cl["text"], "cites": cl.get("cites", []),
                           "evidence": cl.get("evidence", []),
                           "verified": [ct["ref"] for ct in r.get("cites", []) if ct["status"] == "verified"]})
        sections.append({"id": s["id"], "title": s["title"], "claims": claims})
    return {"case_id": case["id"], "title": case["title"], "version": run.version, "synthetic": case.get("synthetic", True),
            "observation": case["observation"], "sections": sections}


def finalize(run, con, decision, name, comment, acknowledge=False, identity=None):
    with run.decision_lock:
        return _finalize(run, con, decision, name, comment, acknowledge, identity)


def _finalize(run, con, decision, name, comment, acknowledge, identity):
    """Human decision. Approval locks the document with a SHA-256 and records an
    e-signature manifestation (who, when, meaning) in the audit chain."""
    if run.status != "awaiting_review":
        raise ValueError("Case is not awaiting review")
    if decision not in ("approve", "changes", "reject"):
        raise ValueError("Unknown decision")
    if not identity or identity.get("role") != "reviewer":
        raise ValueError("Authenticated reviewer identity required")
    if run.case.get("synthetic") is not False or run.mode != "live":
        raise ValueError("Synthetic and scripted runs cannot be approved")
    if not audit.verify_chain(con)[0]:
        raise ValueError("Audit integrity check failed; decision blocked")
    if decision == "approve" and run.score.get("open_items") and not acknowledge:
        raise ValueError("Review the evidence packet and explicitly acknowledge open items before approving")
    if decision == "approve":
        if not run.document or not any(s["claims"] for s in run.document["sections"]):
            raise ValueError("Cannot approve an empty response")
        if any(r["status"] == "removed" for r in run.claim_res.values()):
            raise ValueError("Blocked claims must be corrected in a new run before approval")
        if run.review_packet.get("summary", {}).get("evidence_gaps"):
            raise ValueError("Missing evidence or regulatory mappings must be supplied before approval")
        if any(not check["ok"] for result in run.claim_res.values() for cite in result["cites"] for check in cite["checks"]):
            raise ValueError("All citation checks, including corpus currency, must pass before approval")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if decision == "approve":
        run.version = "v1.0"
        run.document["version"] = "v1.0"
        digest = sha(run.document)
        run.signature = {"name": name, "meaning": "Reviewed and approved for submission", "timestamp": ts, "doc_sha256": digest, "comment": comment,
                         "open_items_acknowledged": acknowledge, "identity_assurance": "Authenticated local reviewer account",
                         "username": identity["username"]}
        run.status = "approved"
        audit.append(con, run.id, name, "approved_locked", run.signature)
    else:
        run.status = "returned" if decision == "changes" else "rejected"
        run.signature = {"name": name, "meaning": "Returned for changes" if decision == "changes" else "Rejected", "timestamp": ts, "comment": comment}
        audit.append(con, run.id, name, decision, run.signature)
    ok, n, _ = audit.verify_chain(con)
    event = run.emit("decision", status=run.status, signature=run.signature, version=run.version, audit={"entries": n, "intact": ok})
    store.save(con, run)
    return event
