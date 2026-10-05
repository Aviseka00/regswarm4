"""Real (not scripted) analytics over the site's environmental-monitoring data.

This is the 'pull the dataset, derive findings' step: it reads the raw EM results
and deviation records and computes the numbers the response relies on. Nothing
here is invented by a language model.
"""
import csv
import json
import os
from collections import Counter, defaultdict

HUMAN_FLORA = ("staphylococcus", "micrococcus", "corynebacterium", "cutibacterium", "kocuria")


def load_site(site_dir):
    with open(os.path.join(site_dir, "em_data.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(site_dir, "site.json"), encoding="utf-8") as f:
        site = json.load(f)
    for r in rows:
        r["cfu"] = int(r["cfu"])
        r["week"] = int(r["week"])
        r["action_limit"] = int(r["action_limit"])
    return rows, site


def _slope(ys):
    """Least-squares slope of ys against 0..n-1."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def analyze(rows, site):
    a_rows = [r for r in rows if r["grade"] == "A"]
    exc = [r for r in a_rows if r["cfu"] >= r["action_limit"]]
    b_alerts = [r for r in rows if r["grade"] == "B" and r["alert_limit"] != "" and r["cfu"] >= int(r["alert_limit"])]
    weeks = sorted({r["week"] for r in rows})
    weekly = []
    for w in weeks:
        ex = [r for r in exc if r["week"] == w]
        weekly.append({"week": w, "excursions": len(ex), "cfu": sum(r["cfu"] for r in ex)})
    by_loc = Counter(r["location"] for r in exc)
    hot_loc, hot_n = by_loc.most_common(1)[0] if by_loc else ("", 0)
    loc_desc = {r["location"]: r["location_desc"] for r in rows}
    org = Counter(r["organism"] for r in exc if r["organism"])
    human = sum(n for o, n in org.items() if o.lower().startswith(HUMAN_FLORA))
    n_samples_a = len(a_rows)

    devs = site["deviations"]
    by_sample = {d["sample_id"]: d for d in devs}
    closed_no_rc = [d for d in devs if d["status"] == "Closed" and d["root_cause"] == "Not determined"]
    no_batch = [d for d in devs if not d["batch_impact_assessed"]]
    batches_exc = sorted({r["batch"] for r in exc})
    first, last = min(r["date"] for r in a_rows), max(r["date"] for r in a_rows)
    trends = site["trend_register"]
    missing_trend = [t for t in trends if t["status"] == "Not issued"]

    return {
        "period_start": first, "period_end": last, "n_weeks": len(weeks),
        "n_samples_total": len(rows), "n_samples_a": n_samples_a,
        "n_exc": len(exc), "exc": exc,
        "exc_rate_pct": round(100 * len(exc) / n_samples_a, 1) if n_samples_a else 0,
        "by_loc": dict(by_loc), "hot_loc": hot_loc, "hot_n": hot_n,
        "hot_desc": loc_desc.get(hot_loc, ""), "hot_share_pct": round(100 * hot_n / len(exc)) if exc else 0,
        "organisms": dict(org), "human_flora_n": human,
        "human_flora_pct": round(100 * human / len(exc)) if exc else 0,
        "weekly": weekly,
        "slope_exc_per_week": round(_slope([w["excursions"] for w in weekly]), 3),
        "slope_cfu_per_week": round(_slope([w["cfu"] for w in weekly]), 3),
        "b_alerts": len(b_alerts),
        "n_devs": len(devs), "n_closed_no_rc": len(closed_no_rc), "n_no_batch": len(no_batch),
        "n_open": sum(1 for d in devs if d["status"] == "Open"),
        "batches_exc": batches_exc, "n_batches_exc": len(batches_exc),
        "n_missing_trend": len(missing_trend),
        "missing_trend_periods": ", ".join(t["period"] for t in missing_trend),
        "dev_ids_closed": [d["id"] for d in closed_no_rc],
        "dev_by_sample": {k: v["id"] for k, v in by_sample.items()},
    }


def evidence_index(rows, site, an):
    """Every record a claim may cite, keyed by evidence id."""
    ev = {"EV-EM-DATA": {"kind": "dataset", "label": "EM results, Filling Suite 2",
                          "detail": f"{an['n_samples_total']} samples, {an['period_start']} to {an['period_end']}"}}
    for s in site["sops"]:
        ev[f"EV-{s['id']}"] = {"kind": "sop", "label": f"{s['id']} v{s['version']}", "detail": s["title"]}
    for d in site["deviations"]:
        ev[f"EV-{d['id']}"] = {"kind": "deviation", "label": d["id"],
                               "detail": f"{d['status']}; root cause: {d['root_cause']}"}
    for t in site["trend_register"]:
        ev[f"EV-{t['id']}"] = {"kind": "trend", "label": t["id"], "detail": t["status"]}
    for p in site["aps"]:
        ev[f"EV-{p['id']}"] = {"kind": "aps", "label": p["id"], "detail": p["result"]}
    return ev
