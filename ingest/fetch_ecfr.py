"""Fetch real CFR text from the official eCFR API and build the local corpus.

    python ingest\\fetch_ecfr.py                 # default parts (see DEFAULT_PARTS)
    python ingest\\fetch_ecfr.py --parts 211 610  # only some parts
    python ingest\\fetch_ecfr.py --xml part211.xml --part 211   # from a downloaded XML file

Source: https://www.ecfr.gov/developers/documentation/api/v1  (US Government
work, free, no key). Every section is stored with the date the text was current
as of, so the swarm can state which version it cited and never cite stale text.

Standard library only - no pip install required.
"""
import argparse
import datetime
import gzip
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from parse_ecfr import parse_xml  # noqa: E402
from regswarm import db  # noqa: E402

BASE = "https://www.ecfr.gov/api/versioner/v1"
TITLE = 21
DEFAULT_PARTS = [11, 210, 211, 600, 610, 1271]
PART_NAMES = {
    11: "Electronic Records; Electronic Signatures",
    210: "Current Good Manufacturing Practice in Manufacturing, Processing, Packing, or Holding of Drugs; General",
    211: "Current Good Manufacturing Practice for Finished Pharmaceuticals",
    600: "Biological Products: General",
    610: "General Biological Products Standards",
    1271: "Human Cells, Tissues, and Cellular and Tissue-Based Products",
}
# eCFR sits behind a gateway that can answer 406 to requests without a normal
# Accept header, so try a few ordinary header sets (first one that works wins).
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# The eCFR "full" endpoint REQUIRES compression ("Send an Accept-Encoding header that
# permits compression") - that was the 406. So every request asks for gzip.
GZ = {"Accept-Encoding": "gzip"}
HEADER_SETS = [
    {**GZ, "User-Agent": BROWSER_UA, "Accept": "application/xml, text/xml, application/json;q=0.9, */*;q=0.8"},
    {**GZ, "User-Agent": BROWSER_UA, "Accept": "application/xml"},
    {**GZ, "User-Agent": "RegSwarm-MVP/0.1 (regulatory research prototype)", "Accept": "*/*"},
]


def _inflate(data):
    """Bodies come back gzip-compressed; decompress when the gzip magic bytes are present."""
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


def http_get(url, tries=1, timeout=120):
    last = None
    for hdrs in HEADER_SETS:
        for i in range(tries):
            try:
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return _inflate(r.read())
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (404, 400):   # wrong date/part - a different header set will not help
                    raise SystemExit(f"Could not fetch {url}\n  {e}")
                break                      # 406/403/etc: try next header set
            except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
                last = e
                time.sleep(2)
    # Last resorts: the tools Windows itself ships (curl.exe, PowerShell) - their requests
    # look like ordinary browser/OS traffic to the eCFR gateway.
    for cmd in (["curl", "-sSL", "--fail", "--compressed", "-A", BROWSER_UA, "-H", "Accept: application/xml", url],):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
            last = f"{cmd[0]}: {(r.stderr or b'').decode('utf-8', 'ignore').strip()[:200] or 'exit ' + str(r.returncode)}"
        except (OSError, subprocess.SubprocessError) as e:
            last = f"{cmd[0]}: {e}"
    raise SystemExit(f"Could not fetch {url}\n  {last}\n"
                     "Check your internet connection, or download the part XML by hand (see MANUAL FALLBACK).")


def title_dates():
    """Candidate currency dates for Title 21, best first (what eCFR says the text is up to date as of)."""
    out = []
    try:
        data = json.loads(http_get(f"{BASE}/titles.json"))
        for t in data.get("titles", []):
            if t.get("number") == TITLE:
                for k in ("up_to_date_as_of", "latest_issue_date", "latest_amended_on"):
                    if t.get(k) and t[k] not in out:
                        out.append(t[k])
    except (Exception, SystemExit) as e:  # http_get exits on failure - fall through to date guesses
        print("  (could not read titles.json:", e, ")")
    today = datetime.date.today()
    for d in (3, 7, 14):
        out.append((today - datetime.timedelta(days=d)).isoformat())
    return out


def local_xml(part):
    """A part XML saved by hand in data/xml/part<N>.xml (fallback when the API cannot be reached)."""
    p = os.path.join(os.path.dirname(HERE), "data", "xml", f"part{part}.xml")
    return p if os.path.exists(p) else None


def manual_url(part, dates):
    return f"{BASE}/full/{dates[0]}/title-{TITLE}.xml?part={part}"


def fetch_part(part, dates):
    """Try each candidate date until eCFR returns parseable sections. Returns (sections, as_of, url)."""
    last = ""
    lp = local_xml(part)
    if lp:
        secs = parse_xml(open(lp, "rb").read())
        if secs:
            # A filesystem timestamp is not the regulation's currency date.
            as_of = "unknown"
            return secs, as_of, "file:" + lp
    for as_of in dates:
        url = f"{BASE}/full/{as_of}/title-{TITLE}.xml?part={part}"
        try:
            raw = http_get(url)
        except (Exception, SystemExit) as e:
            last = str(e)
            continue
        secs = parse_xml(raw)
        if secs:
            return secs, as_of, url
        last = "no <SECTION> elements found; response began: " + raw[:200].decode("utf-8", "ignore")
    raise SystemExit(f"Part {part}: could not load from eCFR. Last problem: {last}\n\n"
                     "MANUAL FALLBACK: open this address in your browser, save the page as\n"
                     f"    data\\xml\\part{part}.xml\n"
                     f"  {manual_url(part, dates)}\n"
                     "then run setup.bat again.")


def load(con, part, sections, as_of, url):
    doc_id = f"21 CFR Part {part}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM paras_fts WHERE section_id LIKE ?", (f"21 CFR {part}.%",))
    con.execute("DELETE FROM paras WHERE section_id LIKE ?", (f"21 CFR {part}.%",))
    con.execute("DELETE FROM sections WHERE doc_id=?", (doc_id,))
    con.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?)",
                (doc_id, "US FDA", PART_NAMES.get(part, f"Part {part}"), as_of, now, url))
    n_par = 0
    for s in sections:
        sid = f"21 CFR {s['section']}"
        full = "\n".join(t for _, t in s["paras"])
        sec_url = f"https://www.ecfr.gov/current/title-{TITLE}/section-{s['section']}"
        con.execute("INSERT OR REPLACE INTO sections VALUES(?,?,?,?,?,?,?,?,?)",
                    (sid, doc_id, s["section"], s["heading"], s["status"], s["cita"],
                     as_of, sec_url, full))
        for i, (path, text) in enumerate(s["paras"]):
            cur = con.execute("INSERT INTO paras(section_id, ord, path, text) VALUES(?,?,?,?)",
                              (sid, i, path, text))
            con.execute("INSERT INTO paras_fts(rowid, text, heading, section_id, path) VALUES(?,?,?,?,?)",
                        (cur.lastrowid, text, s["heading"], sid, path))
            n_par += 1
    con.commit()
    return len(sections), n_par


def self_check(con):
    """Print a few facts so you can eyeball that parsing worked."""
    print("\nSelf-check")
    for sid in ("21 CFR 211.22", "21 CFR 211.42", "21 CFR 211.113", "21 CFR 211.192"):
        row = con.execute("SELECT heading, status FROM sections WHERE id=?", (sid,)).fetchone()
        paths = [r[0] for r in con.execute("SELECT path FROM paras WHERE section_id=? ORDER BY ord", (sid,))]
        print(f"  {sid}: {'MISSING' if not row else row['heading']!r} "
              f"({len(paths)} paragraphs){'  path c/10/iv present' if 'c/10/iv' in paths else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", nargs="*", type=int, default=DEFAULT_PARTS)
    ap.add_argument("--xml", help="use a downloaded eCFR part XML file instead of the API")
    ap.add_argument("--part", type=int, help="part number for --xml")
    ap.add_argument("--as-of", help="currency date to record with --xml (YYYY-MM-DD)")
    a = ap.parse_args()

    con = db.connect()
    if a.xml:
        if not a.part:
            raise SystemExit("--xml needs --part")
        secs = parse_xml(open(a.xml, "rb").read())
        n, p = load(con, a.part, secs, a.as_of or "unknown", "file:" + a.xml)
        print(f"Part {a.part}: {n} sections, {p} paragraphs (from file)")
    else:
        dates = title_dates()
        print(f"Title {TITLE} currency date candidates: {', '.join(dates[:3])}")
        for part in a.parts:
            print(f"Fetching 21 CFR Part {part} ...", end=" ", flush=True)
            secs, as_of, url = fetch_part(part, dates)
            n, p = load(con, part, secs, as_of, url)
            print(f"{n} sections, {p} paragraphs (as of {as_of})")
    st = db.corpus_stats(con)
    print(f"\nCorpus: {st['documents']} documents, {st['sections']} active sections, "
          f"{st['paragraphs']} paragraphs -> {db.DB_PATH}")
    self_check(con)


if __name__ == "__main__":
    main()
