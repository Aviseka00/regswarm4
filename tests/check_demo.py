"""python tests/check_demo.py  - verify the demo case against the loaded regulation corpus."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from regswarm import db, pipeline, preflight

con = db.connect()
r = preflight.check(con, pipeline.load_case(sys.argv[1] if len(sys.argv) > 1 else "demo_em_483"))
if r["corpus_sections"] == 0:
    print("Corpus is empty - run setup.bat (python ingest/fetch_ecfr.py) first."); sys.exit(2)
print(f"Demo self-check: {r['checked']} citations checked against {r['corpus_sections']} loaded sections")
print("Seeded defects correctly caught:", ", ".join(r["seeded_caught"]) or "none")
if r["ok"]:
    print("PASS - every non-seeded citation matches the real regulation text."); sys.exit(0)
print("PROBLEMS - these citations do not match the loaded text (send this output to be fixed):")
for p in r["problems"]:
    print(f"  {p['version']:5} {p['claim']:4} {p['ref']}  ->  {p['reason']}")
sys.exit(1)
