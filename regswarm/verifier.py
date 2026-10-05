"""Deterministic citation verifier - the hallucination firewall.

No language model is involved. For every citation a draft makes we check, against
the versioned corpus:

  1. the section exists
  2. the section is active (not [Reserved] / removed)
  3. the cited paragraph path exists (e.g. (c)(10)(iv))
  4. any quoted text appears VERBATIM in that paragraph (paraphrase belongs in the
     claim, not in quotation marks)
  5. the corpus text is current (as-of date recorded and not stale)

A claim that asserts a regulatory requirement and has no fully verified citation
is removed from the draft. This mirrors the blueprint rule: no citation = claim deleted.
"""
import datetime
import difflib
import re

CITE_RE = re.compile(r"21\s*CFR\s*(?:§+\s*)?(\d{1,4}\.\d{1,4})((?:\s*\([A-Za-z0-9]{1,5}\))*)")
STALE_DAYS = 45


def norm(s):
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def parse_ref(ref):
    """'21 CFR 211.42(c)(10)(iv)' -> ('21 CFR 211.42', 'c/10/iv') or None."""
    m = CITE_RE.search(ref or "")
    if not m:
        return None
    marks = re.findall(r"\(([A-Za-z0-9]{1,5})\)", m.group(2) or "")
    return f"21 CFR {m.group(1)}", "/".join(marks)


def _path_text(con, section_id, path):
    """Text of a paragraph plus all its descendants."""
    if path == "":
        rows = con.execute("SELECT text FROM paras WHERE section_id=? ORDER BY ord", (section_id,)).fetchall()
    else:
        rows = con.execute(
            "SELECT text FROM paras WHERE section_id=? AND (path=? OR path LIKE ?) ORDER BY ord",
            (section_id, path, path + "/%")).fetchall()
    return " ".join(r["text"] for r in rows)


def verify_citation(con, ref, quote=None, today=None):
    """Return {ref, status: verified|failed, checks:[{name, ok, detail}], reason, url, as_of}."""
    checks = []
    out = {"ref": ref, "quote": quote, "status": "failed", "checks": checks,
           "reason": "", "url": None, "as_of": None}

    def add(name, ok, detail="", advisory=False):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "advisory": advisory})
        return ok

    parsed = parse_ref(ref)
    if not add("Reference is well-formed", parsed, "" if parsed else "could not parse the reference"):
        out["reason"] = "Malformed reference"
        return out
    section_id, path = parsed

    sec = con.execute("SELECT * FROM sections WHERE id=?", (section_id,)).fetchone()
    if not add("Section exists in corpus", sec, section_id):
        out["reason"] = f"{section_id} does not exist in the corpus"
        return out
    out["url"], out["as_of"] = sec["url"], sec["as_of"]

    if not add("Section is in force (not reserved/removed)", sec["status"] == "active", sec["status"]):
        out["reason"] = f"{section_id} is {sec['status']}"
        return out

    if path:
        exists = con.execute("SELECT 1 FROM paras WHERE section_id=? AND (path=? OR path LIKE ?) LIMIT 1",
                             (section_id, path, path + "/%")).fetchone()
        shown = "".join(f"({p})" for p in path.split("/"))
        if not add("Paragraph exists", exists, f"{section_id}{shown}"):
            out["reason"] = f"Paragraph {shown} does not exist in {section_id}"
            return out

    if quote:
        target = norm(_path_text(con, section_id, path))
        segs = [norm(x) for x in re.split(r"…|\.\.\.", quote) if norm(x)]
        ok = all(sg in target for sg in segs)
        if not ok:
            whole = norm(_path_text(con, section_id, ""))
            if all(sg in whole for sg in segs):
                add("Quote appears verbatim in cited paragraph", False,
                    "quote exists in the section but NOT in the cited paragraph")
                out["reason"] = "Quote is in the section but not in the cited paragraph"
            else:
                best = difflib.SequenceMatcher(None, norm(quote), target).ratio() if target else 0
                add("Quote appears verbatim in cited paragraph", False,
                    f"no verbatim match (closest similarity {best:.0%})")
                out["reason"] = "Quoted text not found - possible misquotation"
            return out
        add("Quote appears verbatim in cited paragraph", True)

    try:
        age = ((today or datetime.date.today()) - datetime.date.fromisoformat(sec["as_of"])).days
        add("Corpus text is current", age <= STALE_DAYS, f"as of {sec['as_of']} ({age} days old)", True)
    except Exception:
        add("Corpus text is current", False, "no as-of date recorded", True)

    out["status"] = "verified" if all(c["ok"] for c in checks if not c["advisory"]) else "failed"
    if out["status"] == "failed":
        out["reason"] = "Failed a required check"
    return out


def verify_claim(con, claim, evidence_ids, today=None):
    """Verify one draft claim. Returns dict(status, cites, reason)."""
    kind = claim.get("kind")
    cites = [verify_citation(con, c["ref"], c.get("quote"), today) for c in claim.get("cites", [])]
    res = {"claim_id": claim["id"], "kind": kind, "cites": cites, "status": "verified", "reason": ""}
    res["support_status"] = "interpretation_review_required"
    if kind not in ("regulatory", "site_fact", "action"):
        res["status"], res["reason"] = "removed", "Unknown or missing claim kind"
        return res
    if kind == "action":
        res["support_status"] = "proposed_commitment"
        if any(c["status"] != "verified" for c in cites):
            res["status"], res["reason"] = "removed", "Proposed action contains an invalid citation"

    if kind == "regulatory":
        good = [c for c in cites if c["status"] == "verified"]
        bad = [c for c in cites if c["status"] != "verified"]
        if not cites:
            res["status"], res["reason"] = "removed", "Regulatory claim with no citation"
        elif bad:
            res["status"] = "removed"
            res["reason"] = "; ".join(f"{b['ref']}: {b['reason']}" for b in bad)
        elif not good:
            res["status"], res["reason"] = "removed", "No verified citation"
    elif kind == "site_fact":
        ev = claim.get("evidence", [])
        missing = [e for e in ev if e not in evidence_ids]
        if not ev:
            res["status"], res["reason"] = "removed", "Site fact with no evidence reference"
        elif missing:
            res["status"], res["reason"] = "removed", "Evidence not found: " + ", ".join(missing)
    return res
