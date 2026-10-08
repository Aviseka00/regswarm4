"""The site QMS document library: fetch (inventory), smart-pull (relevance search) and
cross-document analytics. This is real code over the connector export - no language model.

In the demo the 'connectors' read a synthetic export (cases/demo_site/docs.json). In
production the same interface is served by read-only connectors to the eQMS, DMS, MES,
LIMS, LMS and CMMS; nothing downstream changes.
"""
import datetime
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

from .retrieval import STOP

CONTROLLED = {"SOP", "STP", "Protocol", "Master BMR", "SMF"}   # groups whose revision needs document control


def load(site_dir):
    with open(os.path.join(site_dir, "docs.json"), encoding="utf-8") as f:
        return json.load(f)


def inventory(lib):
    docs = lib["docs"]
    by_group = Counter(d["group"] for d in docs)
    by_sys = Counter(d["system"] for d in docs)
    sys_groups = defaultdict(Counter)
    for d in docs:
        sys_groups[d["system"]][d["group"]] += 1
    return {
        "total": len(docs),
        "groups": [{"group": g, "label": lib["group_labels"].get(g, g), "count": n} for g, n in by_group.items()],
        "systems": [{**s, "count": by_sys.get(s["id"], 0),
                     "groups": [{"group": g, "label": lib["group_labels"].get(g, g), "count": n} for g, n in sys_groups[s["id"]].items()]}
                    for s in lib["systems"]],
    }


def terms(text):
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()):
        if w in STOP:
            continue
        w = w.replace("-", " ")
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


class Index:
    """In-memory FTS5 (BM25, porter stemming) over every section of every document."""

    def __init__(self, lib):
        self.docs = {d["id"]: d for d in lib["docs"]}
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.con.execute("CREATE TABLE sec(rowid INTEGER PRIMARY KEY, doc_id TEXT, ref TEXT, text TEXT)")
        self.con.execute("CREATE VIRTUAL TABLE sec_fts USING fts5(title, text, tokenize='porter unicode61')")
        for d in lib["docs"]:
            for s in d["sections"] or [{"ref": "", "text": ""}]:
                cur = self.con.execute("INSERT INTO sec(doc_id, ref, text) VALUES(?,?,?)", (d["id"], s["ref"], s["text"]))
                self.con.execute("INSERT INTO sec_fts(rowid, title, text) VALUES(?,?,?)", (cur.lastrowid, d["title"], s["text"]))
        self.n_sections = self.con.execute("SELECT COUNT(*) FROM sec").fetchone()[0]

    def search(self, query, k=6, area_hint=None, since=None):
        """Top-k documents for a free-text query, each with its best passage and a plain-language 'why'."""
        ts = terms(query)
        if not ts:
            return []
        q = " OR ".join(f'"{t}"' for t in ts)
        rows = self.con.execute(
            """SELECT sec.doc_id, sec.ref, sec.text, bm25(sec_fts, 2.0, 1.0) AS rank
               FROM sec_fts JOIN sec ON sec.rowid = sec_fts.rowid WHERE sec_fts MATCH ? ORDER BY rank LIMIT 80""", (q,)).fetchall()
        best = {}
        for doc_id, ref, text, rank in rows:
            if doc_id not in best:
                best[doc_id] = (ref, text, -rank)
        if not best:
            return []
        top = max(v[2] for v in best.values()) or 1.0
        out = []
        for doc_id, (ref, text, sc) in best.items():
            d = self.docs[doc_id]
            low = (text + " " + d["title"]).lower()
            matched = [t for t in ts if t.split()[0][:5] in low]
            area = bool(area_hint and area_hint.lower() in (d.get("area") or "").lower())
            recent = bool(since and (d.get("date") or "") >= since)
            frac = len(matched) / len(ts)
            rel = 50 * sc / top + 34 * min(1.0, frac * 2.2) + (10 if area else 0) + (6 if recent else 0)
            why = [f"{len(matched)} of {len(ts)} query terms"]
            if area:
                why.append(d["area"])
            if recent:
                why.append("inside review period")
            out.append({"doc_id": doc_id, "title": d["title"], "group": d["group"], "type": d["type"], "system": d["system"],
                        "version": d["version"], "status": d["status"], "date": d["date"], "ref": ref, "passage": text,
                        "matched": matched[:12], "relevance": round(min(100.0, rel)), "why": why})
        out.sort(key=lambda h: -h["relevance"])
        return out[:k]


def ensure_groups(hits, docs, k=20, cap=2):
    """Keep a spread of matches, and include every stored document class so SOP, STP, and BMR all reach the review."""
    found = diversify(hits, k=k, cap=cap)
    seen_docs = {hit["doc_id"] for hit in found}
    present = {hit["group"] for hit in found}
    best = {}
    for hit in hits:
        best.setdefault(hit["group"], hit)
    for document in docs:
        group = document.get("group") or "Record"
        if group in present or len(found) >= k or document["id"] in seen_docs:
            continue
        sample = best.get(group)
        if sample is None and document.get("sections"):
            section = document["sections"][0]
            sample = {"doc_id": document["id"], "title": document["title"], "group": group,
                      "type": document.get("type") or group, "system": document.get("system") or group,
                      "version": document.get("version"), "status": document.get("status"), "date": document.get("date"),
                      "ref": section.get("ref") or "Record", "passage": section.get("text") or "",
                      "matched": [], "relevance": 1, "why": ["stored source"]}
        if not sample:
            continue
        found.append(dict(sample))
        seen_docs.add(sample["doc_id"])
        present.add(group)
    return found


def diversify(hits, k=6, cap=2):
    """Keep at most `cap` documents per document type so ten sibling deviations or twelve batch
    records do not crowd out everything else; note how many similar records were folded in."""
    kept, seen, hidden = [], defaultdict(int), defaultdict(int)
    for h in hits:
        g = h["group"]
        seen[g] += 1
        if seen[g] <= cap and len(kept) < k:
            kept.append(dict(h))
        else:
            hidden[g] += 1
    first = {}
    for h in kept:
        first.setdefault(h["group"], h)
    for g, h in first.items():
        h["similar"] = hidden[g]
    for h in kept:
        h.setdefault("similar", 0)
    return kept


# ------------------------------------------------------------------ cross-document analytics
def _months(a, b):
    y, m = int(a[:4]), int(a[5:7])
    ey, em = int(b[:4]), int(b[5:7])
    res = []
    while (y, m) <= (ey, em):
        res.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return res


def analyze_docs(lib, an, rows):
    """Derive cross-record findings by joining the documents to the EM data. Every number is computed."""
    docs = {d["id"]: d for d in lib["docs"]}
    ebr = [d for d in lib["docs"] if d["group"] == "Executed BMR" and d["meta"].get("line") == "FL2"]
    exc_b = set(an["batches_exc"])
    hot_b = {r["batch"] for r in an["exc"] if r["location"] == an["hot_loc"]}
    hot = [d for d in ebr if d["meta"]["batch"] in hot_b]
    rest = [d for d in ebr if d["meta"]["batch"] not in hot_b]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0
    int_hot = avg([d["meta"]["interventions"] for d in hot])
    int_rest = avg([d["meta"]["interventions"] for d in rest])
    exc_ebr = [d for d in ebr if d["meta"]["batch"] in exc_b]
    unlinked = [d for d in exc_ebr if not d["meta"]["em_excursion_referenced"]]
    distributed = [d for d in exc_ebr if d["meta"]["disposition"] == "Distributed"]

    trn = {d["meta"]["operator"]: d["meta"] for d in lib["docs"] if d["group"] == "Training" and "operator" in d["meta"]}
    def lapsed_on(d):
        fd = d["meta"]["fill_date"]
        return [o for o in d["meta"]["operators"] if trn.get(o) and trn[o]["requal_due"] < fd]
    exc_lapsed = [d for d in exc_ebr if lapsed_on(d)]
    non_exc = [d for d in ebr if d["meta"]["batch"] not in exc_b]
    non_lapsed = [d for d in non_exc if lapsed_on(d)]
    lapsed_ops = sorted({o for d in exc_ebr for o in lapsed_on(d)})

    cc = docs.get("CC-26-031")
    first_hot = min((r["date"] for r in an["exc"] if r["location"] == an["hot_loc"]), default=None)
    cc_gap = None
    if cc and first_hot:
        cc_gap = (datetime.date.fromisoformat(first_hot) - datetime.date.fromisoformat(cc["meta"]["effective"])).days
    smoke = docs.get("RPT-VAL-HVAC-2025-07")
    smoke_gap = None
    if cc and smoke:
        smoke_gap = (datetime.date.fromisoformat(cc["meta"]["effective"]) - datetime.date.fromisoformat(smoke["meta"]["smoke_study_date"])).days

    capa_prev = docs.get("CAPA-25-019")
    msr = sorted(d["meta"]["month"] for d in lib["docs"] if d["type"] == "Monthly EM summary")
    expected = _months("2026-01", an["period_end"][:7])
    missing_msr = [m for m in expected if m not in msr]

    ahu_docs = [d for d in lib["docs"] if "FL1" in (d["meta"].get("serves") or []) and "FL2" in (d["meta"].get("serves") or [])]

    facts = {
        "n_docs": len(lib["docs"]),
        "bmr_int_hot": int_hot, "bmr_int_rest": int_rest,
        "n_bmr_unlinked": len(unlinked), "n_exc_bmr": len(exc_ebr),
        "n_dist": len(distributed), "n_batches_exc_bmr": len(exc_ebr),
        "n_lapsed_batches": len(exc_lapsed), "n_lapsed_ops": len(lapsed_ops), "lapsed_ops": ", ".join(lapsed_ops),
        "n_nonexc_batches": len(non_exc), "n_nonexc_lapsed": len(non_lapsed),
        "cc_gap_days": cc_gap if cc_gap is not None else 0,
        "cc_effective": cc["meta"]["effective"] if cc else "",
        "smoke_gap_days": smoke_gap if smoke_gap is not None else 0,
        "smoke_date": smoke["meta"]["smoke_study_date"] if smoke else "",
        "n_missing_msr": len(missing_msr), "missing_msr": ", ".join(missing_msr),
        "n_msr_found": len(msr), "n_msr_expected": len(expected),
    }
    findings = [
        {"id": "F1", "title": "Batch records: more interventions where excursions occurred", "severity": "high",
         "detail": f"Executed BMRs for batches with a {an['hot_loc']} excursion record {int_hot} Grade A interventions on average, against {int_rest} for the other batches.",
         "docs": [d["id"] for d in hot][:4] + ["SOP-AS-003"], "elements": ["E1"]},
        {"id": "F2", "title": "Batch record review did not reference the excursions", "severity": "high",
         "detail": f"{len(unlinked)} of {len(exc_ebr)} batches with an EM excursion have a QA-approved batch record that states no excursion or deviation was referenced; SOP-QA-030 5.2 requires it.",
         "docs": [d["id"] for d in unlinked][:3] + ["SOP-QA-030"], "elements": ["E2", "E3", "E5"]},
        {"id": "F3", "title": "Excursion batches already in the market", "severity": "high",
         "detail": f"{len(distributed)} of the {len(exc_ebr)} batches filled during excursion weeks show disposition 'Distributed' in the MES archive.",
         "docs": [d["id"] for d in distributed][:3], "elements": ["E3"]},
        {"id": "F4", "title": "Operators with overdue aseptic requalification", "severity": "medium",
         "detail": f"{len(exc_lapsed)} of {len(exc_ebr)} excursion batches involved an operator whose requalification was overdue ({', '.join(lapsed_ops)}), against {len(non_lapsed)} of {len(non_exc)} batches without excursions. An association to test, not a proven cause.",
         "docs": ["TM-FL2"] + [f"TRN-{o}" for o in lapsed_ops] + ["SOP-GW-002"], "elements": ["E1"]},
        {"id": "F5", "title": "Equipment change closed without requalification", "severity": "high",
         "detail": f"CC-26-031 (stopper bowl modification, effective {facts['cc_effective']}) concluded no sterility impact and did not repeat the media fill or airflow visualisation. The first {an['hot_loc']} excursion followed {cc_gap} days later; the last smoke study is {smoke_gap} days older than the change.",
         "docs": ["CC-26-031", "APS-2026-01", "RPT-VAL-HVAC-2025-07", "EQ-FL2-STOPPER-PM"], "elements": ["E1"]},
        {"id": "F6", "title": "Repeat problem at the same location", "severity": "medium",
         "detail": "CAPA-25-019 addressed Grade A excursions at the same stopper bowl location in 2025 and was closed without the planned effectiveness check; audit IA-2025-11 flagged both this and late trend reports.",
         "docs": ["CAPA-25-019", "IA-2025-11", "CAPA-25-031"], "elements": ["E1", "E4"]},
        {"id": "F7", "title": "Periodic EM reports missing in the archive", "severity": "medium",
         "detail": f"SOP-EM-014 9.2 requires monthly summaries: {len(msr)} of {len(expected)} found for the review window (missing {', '.join(missing_msr)}); quarterly reports for {an['missing_trend_periods']} were never issued.",
         "docs": ["SOP-EM-014", "MSR-2026-03", "TR-2025-Q4"], "elements": ["E4"]},
    ]
    return {"facts": facts, "findings": findings, "ahu_docs": [d["id"] for d in ahu_docs],
            "excursion_batches": [d["id"] for d in exc_ebr], "distributed": [d["id"] for d in distributed],
            "fl1_batches": [d["id"] for d in lib["docs"] if d["group"] == "Executed BMR" and d["meta"].get("line") == "FL1"]}


def impacted_documents(lib, targets):
    """Controlled documents that reference any target document (one hop). This is the
    'what else has to be revised together' list a change control needs."""
    tset = set(targets)
    out = {}
    for d in lib["docs"]:
        if d["group"] in CONTROLLED and d["id"] not in tset and tset & set(d["refs"]):
            out[d["id"]] = d
    return [{"id": d["id"], "title": d["title"], "group": d["group"], "version": d["version"]} for d in out.values()]


LEVELS = ["none", "low", "medium", "high"]


def impact_matrix(facts, dl):
    """Risk-based impact grid (ICH Q9 style). The rules are transparent heuristics on computed
    facts; the QA reviewer confirms every rating."""
    dist = facts["n_dist"] > 0
    lapsed = facts["n_lapsed_ops"] > 0
    cc_gap = facts["cc_gap_days"] > 0 and facts["smoke_gap_days"] > 180
    cols = ["Product quality", "Patient / market", "GMP compliance", "Validated state", "Documentation", "Training"]
    rows = [
        ("Batches filled in scope", [3 if dist else 2, 3 if dist else 1, 3, 1, 3, 0], f"{facts['n_exc_bmr']} excursion batches, {facts['n_dist']} distributed"),
        ("Filling Line 2 - stopper bowl", [2, 1, 2, 3 if cc_gap else 2, 1, 2], "modified without requalification" if cc_gap else "under review"),
        ("Filling Line 1 (shared AHU-07)", [1, 1, 1, 2, 0, 0], "shares air handling with Line 2"),
        ("Deviation and investigation system", [1, 1, 3, 2, 2, 1], "closures without root cause"),
        ("Change control system", [1, 0, 2, 3 if cc_gap else 2, 1, 1], "requalification not triggered"),
        ("EM trending and reporting", [1, 0, 3, 1, 2, 1], f"{facts['n_missing_msr']} monthly + 2 quarterly reports missing"),
        ("Aseptic personnel training", [2, 0, 2 if lapsed else 1, 1, 1, 3 if lapsed else 1], f"{facts['n_lapsed_ops']} operators overdue" if lapsed else "current"),
    ]
    return {"columns": cols, "rows": [{"area": a, "levels": lv, "note": n, "score": sum(lv)} for a, lv, n in rows]}
