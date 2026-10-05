"""Generate the SYNTHETIC demo site data (EM results, SOP extracts, deviations).
Deterministic: same output every run. Nothing here is real site data."""
import csv, datetime, json, os, random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_site")
rng = random.Random(2026)
START = datetime.date(2026, 4, 6)        # Monday, week 1
GRADE_A = [("FL2-A1", "Stopper bowl, Line 2"), ("FL2-A2", "Filling needle 3, Line 2"),
           ("FL2-A3", "Conveyor infeed, Line 2"), ("FL2-A4", "Vial transfer star wheel, Line 2")]
GRADE_B = [("FL2-B1", "Background, north wall"), ("FL2-B2", "Background, south wall"),
           ("FL2-B3", "Airlock exit"), ("FL2-B4", "Operator pass-through")]
# (week, location, cfu, organism) - planted Grade A excursions
EXC = [(2, "FL2-A1", 1, "Micrococcus luteus"), (3, "FL2-A1", 1, "Staphylococcus epidermidis"),
       (5, "FL2-A2", 1, "Staphylococcus hominis"), (6, "FL2-A1", 2, "Staphylococcus epidermidis"),
       (7, "FL2-A1", 1, "Micrococcus luteus"), (8, "FL2-A3", 1, "Bacillus sp."),
       (9, "FL2-A1", 2, "Staphylococcus epidermidis"), (10, "FL2-A1", 3, "Staphylococcus hominis"),
       (10, "FL2-A2", 1, "Staphylococcus epidermidis"), (12, "FL2-A1", 2, "Staphylococcus epidermidis")]
exc_map = {(w, l): (c, o) for w, l, c, o in EXC}

rows, n = [], 0
for wk in range(1, 13):
    monday = START + datetime.timedelta(days=7 * (wk - 1))
    batch = f"FL2-B26-{100 + wk}"
    for loc, desc in GRADE_A:
        for s in range(2):
            n += 1
            date = monday + datetime.timedelta(days=1 + 2 * s)
            cfu, org = 0, ""
            if s == 0 and (wk, loc) in exc_map:
                cfu, org = exc_map[(wk, loc)]
            rows.append([f"EM-{n:04d}", date.isoformat(), wk, "Filling Suite 2", loc, desc, "A",
                         "Settle plate (4 h)", cfu, "", 1, org, batch])
    for loc, desc in GRADE_B:
        n += 1
        date = monday + datetime.timedelta(days=2)
        cfu = rng.choice([0, 0, 0, 1, 1, 2, 3])
        org = "" if cfu == 0 else rng.choice(["Micrococcus luteus", "Staphylococcus epidermidis", "Bacillus sp.", "Corynebacterium sp."])
        rows.append([f"EM-{n:04d}", date.isoformat(), wk, "Filling Suite 2", loc, desc, "B",
                     "Settle plate (4 h)", cfu, 3, 5, org, batch])

with open(os.path.join(OUT, "em_data.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sample_id", "date", "week", "room", "location", "location_desc", "grade", "method",
                "cfu", "alert_limit", "action_limit", "organism", "batch"])
    w.writerows(rows)

# Deviations: 9 of 10 excursions closed "no product impact" without root cause; last still open
sid_by_key = {}
for r in rows:
    if r[6] == "A" and r[8] > 0:
        sid_by_key[(r[2], r[4])] = r
devs, k = [], 400
for i, (wk, loc, cfu, org) in enumerate(EXC):
    r = sid_by_key[(wk, loc)]
    k += 7
    opened = datetime.date.fromisoformat(r[1]) + datetime.timedelta(days=1)
    last = i == len(EXC) - 1
    devs.append({
        "id": f"DEV-26-{k:04d}", "sample_id": r[0], "batch": r[12], "opened": opened.isoformat(),
        "status": "Open" if last else "Closed",
        "closed": None if last else (opened + datetime.timedelta(days=2 + i % 2)).isoformat(),
        "root_cause": "Under investigation" if last else "Not determined",
        "batch_impact_assessed": False,
        "closure_statement": None if last else "No product impact - isolated event. Area cleaned and re-sampled with no growth.",
        "other_batches_reviewed": False,
    })

site = {
    "site": "DEMO SITE (SYNTHETIC)",
    "sops": [
        {"id": "SOP-EM-014", "title": "Environmental Monitoring Program - Aseptic Areas", "version": "6.0",
         "effective": "2025-03-01",
         "clauses": [
             {"ref": "7.2", "text": "Any Grade A action-limit result shall be investigated to root cause within 10 working days, including review of aseptic interventions, personnel monitoring, equipment and cleaning records, and an assessment of every batch filled in the affected period."},
             {"ref": "9.1", "text": "EM data shall be trended monthly by Microbiology and reviewed by QA; a quarterly trend report shall be approved by the Head of Quality."}]},
        {"id": "SOP-QA-022", "title": "Deviation Management", "version": "9.0", "effective": "2025-06-15",
         "clauses": [{"ref": "5.4", "text": "Closure of a deviation as 'no product impact' requires documented justification and a QA batch-impact assessment."}]},
        {"id": "SOP-AS-003", "title": "Aseptic Behaviour and Interventions", "version": "4.0", "effective": "2024-11-01",
         "clauses": [{"ref": "6.1", "text": "Interventions in the Grade A zone shall be recorded, and repeated interventions at one location shall be evaluated."}]},
    ],
    "trend_register": [
        {"id": "TR-2025-Q4", "period": "2025-Q4", "status": "Approved 2026-01-19"},
        {"id": "TR-2026-Q1", "period": "2026-Q1", "status": "Not issued"},
        {"id": "TR-2026-Q2", "period": "2026-Q2", "status": "Not issued"},
    ],
    "aps": [{"id": "APS-2026-01", "date": "2026-01-14", "result": "3 runs, 0 contaminated units",
             "note": "Line 2 media fill; next due 2026-07"}],
    "deviations": devs,
}
json.dump(site, open(os.path.join(OUT, "site.json"), "w"), indent=1)
print("rows", len(rows), "grade A excursions", len(EXC), "deviations", len(devs))
