"""Headless run of a case: python tests/run_case.py [case_id] [--speed 0]. Prints a compact trace."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from regswarm import db, pipeline

ap = argparse.ArgumentParser()
ap.add_argument("case", nargs="?", default="demo_em_483")
ap.add_argument("--mode", default="scripted")
ap.add_argument("--speed", type=float, default=0)
a = ap.parse_args()
con = db.connect()
run = pipeline.Run("TEST-" + a.case, pipeline.load_case(a.case), a.mode)
pipeline.execute(run, con, a.speed)
for e in run.events:
    t = e["type"]
    if t == "log":
        print(f"  {e['tag']:7} {e['agent']:5} {e['text'][:110]}")
    elif t in ("verify",):
        print(f"* verify {e['version']}: {e['ok_cites']}/{e['total_cites']} citations ok; removed={e['removed']}")
    elif t == "score":
        print("* score", e["composite"], e["rag"], [(c['name'], c['value']) for c in e["components"]])
        print("  open:", *e["open_items"], sep="\n   - ")
    elif t in ("error", "gate", "done"):
        print("*", t, {k: v for k, v in e.items() if k not in ("i", "t", "type")} if t != "gate" else e["state"])
print("status:", run.status, "| events:", len(run.events), "| nodes:", len(run.nodes_seen), "| edges:", len(run.edges_seen))
