"""Official publication links plus a live openFDA recall lookup.

The response may quote only the 21 CFR text loaded on this computer. Recall reports
and guideline pages are context for the reviewer. USP, the European Pharmacopoeia,
and the Indian Pharmacopoeia do not publish a public full-text API.
"""
import json
import re
import urllib.parse
import urllib.request

CATALOG = (
    {"body": "21 CFR", "use": "Quote this in the response",
     "title": "21 CFR Part 211, current electronic text",
     "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211"},
    {"body": "FDA", "use": "Regulation index",
     "title": "FDA current good manufacturing practice regulations",
     "url": "https://www.fda.gov/drugs/pharmaceutical-quality-resources/current-good-manufacturing-practice-cgmp-regulations"},
    {"body": "openFDA", "use": "Related public recall reports",
     "title": "openFDA drug enforcement reports",
     "url": "https://open.fda.gov/apis/drug/enforcement/"},
    {"body": "WHO", "use": "Official publication, no query API",
     "title": "WHO GMP guidelines, including Technical Report Series annexes",
     "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production"},
    {"body": "EMA", "use": "Official publication, no query API",
     "title": "EMA quality scientific guidelines",
     "url": "https://www.ema.europa.eu/en/human-regulatory-overview/research-and-development/scientific-guidelines/quality-guidelines"},
    {"body": "ICH", "use": "Official publication, no query API",
     "title": "ICH quality guidelines",
     "url": "https://www.ich.org/page/quality-guidelines"},
    {"body": "USP", "use": "Licensed text, no public monograph API",
     "title": "United States Pharmacopeia",
     "url": "https://www.usp.org/"},
    {"body": "EP", "use": "Licensed text, no public monograph API",
     "title": "European Pharmacopoeia",
     "url": "https://www.edqm.eu/en/european-pharmacopoeia"},
    {"body": "IP", "use": "Licensed text, no public monograph API",
     "title": "Indian Pharmacopoeia",
     "url": "https://ipc.gov.in/"},
)

RECOMMENDATION = {
    "best_for_the_response": "21 CFR text already loaded in RegSwarm",
    "best_public_api": "openFDA drug enforcement",
    "reason": (
        "A 483 response can quote 21 CFR because that text is on this computer and each quotation is checked. "
        "openFDA is the public API that returns structured recall reasons for the same kind of observation. "
        "WHO TRS, EMA, and ICH publish guidance documents and do not offer a query API. "
        "USP, the European Pharmacopoeia, and the Indian Pharmacopoeia do not offer a public full-text API."
    ),
}


def search_term(query):
    stop = {"audit", "query", "during", "found", "which", "their", "there", "where", "about", "after",
            "before", "product", "facility", "shall", "should", "record", "records", "batch"}
    words = [word.lower() for word in re.findall(r"[A-Za-z]{5,}", query or "") if word.lower() not in stop]
    if not words:
        return "manufacturing"
    return max(words, key=len)[:40]


def _recalls(query):
    term = search_term(query)
    target = "https://api.fda.gov/drug/enforcement.json?" + urllib.parse.urlencode(
        {"search": f"reason_for_recall:{term}", "limit": 3})
    request = urllib.request.Request(target, headers={"User-Agent": "RegSwarm/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.loads(response.read(500000))
    found = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        reason = item.get("reason_for_recall")
        if not isinstance(reason, str) or not reason.strip():
            continue
        found.append({
            "body": "openFDA",
            "recall_number": item.get("recall_number") if isinstance(item.get("recall_number"), str) else "",
            "classification": item.get("classification") if isinstance(item.get("classification"), str) else "",
            "status": item.get("status") if isinstance(item.get("status"), str) else "",
            "firm": item.get("recalling_firm") if isinstance(item.get("recalling_firm"), str) else "",
            "reason": reason.strip()[:400],
        })
    return found[:3]


def lookup(query):
    """Catalog always returns. A network or empty openFDA result leaves the live list empty."""
    live, note = [], ""
    try:
        live = _recalls(query)
        if not live:
            note = "openFDA returned no recall report for this query."
    except Exception:
        note = "openFDA could not be reached. The publication list is still available."
    return {"catalog": [dict(item) for item in CATALOG], "recalls": live, "note": note,
            "recommendation": dict(RECOMMENDATION), "term": search_term(query)}
