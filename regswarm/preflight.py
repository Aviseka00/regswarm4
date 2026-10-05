"""Self-check: do the demo case's citations match the regulation text that is actually
loaded? Run automatically at server start, in setup.bat, and by tests/check_demo.py.

Every citation in the scripted case is verified EXCEPT the deliberately seeded defects,
which must FAIL (that is the demo). Any other failure means the loaded corpus differs
from what the case was written against - the report says exactly which citation."""
from . import retrieval, verifier


def check(con, case):
    script = case.get("script", {})
    seeded = set(case.get("seeded_defects", []))
    problems, checked, seeded_ok = [], 0, {}

    def claims():
        for s in script.get("draft", {}).get("sections", []):
            for c in s["claims"]:
                yield "v0.1", c
        rev = script.get("revise", {})
        for cid, c in rev.get("replace", {}).items():
            yield "v0.2", c
        for a in rev.get("add", []):
            yield "v0.2", a["claim"]

    for ver, c in claims():
        for ct in c.get("cites", []):
            r = verifier.verify_citation(con, ct["ref"], ct.get("quote"))
            if ver == "v0.1" and c["id"] in seeded:
                seeded_ok[c["id"]] = r["status"] == "failed"
                continue
            checked += 1
            if r["status"] != "verified":
                problems.append({"claim": c["id"], "version": ver, "ref": ct["ref"], "reason": r["reason"]})
    for m in script.get("map", {}).get("items", []):
        checked += 1
        if not retrieval.lookup(con, m["ref"]):
            problems.append({"claim": m["element"], "version": "map", "ref": m["ref"], "reason": "clause not found in corpus"})
    for cid in seeded:
        if not seeded_ok.get(cid):
            problems.append({"claim": cid, "version": "v0.1", "ref": "(seeded)", "reason": "seeded defect unexpectedly verified - it would not demonstrate the firewall"})
    n_sections = con.execute("SELECT COUNT(*) FROM sections WHERE status='active'").fetchone()[0]
    return {"ok": not problems and n_sections > 0, "checked": checked, "problems": problems,
            "corpus_sections": n_sections, "seeded_caught": sorted(k for k, v in seeded_ok.items() if v)}
