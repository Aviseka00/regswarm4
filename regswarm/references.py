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


def _plain_query(query):
    kept = []
    for line in (query or "").splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("audit queries for ") or stripped.startswith("the current version of "):
            continue
        kept.append(line)
    return "\n".join(kept).strip() or (query or "")


def _matches(text, triggers):
    low = (text or "").lower()
    return any(all(term in low for term in group) for group in triggers)


# Public guideline titles and official pages. These notes name the subject the
# publication covers. They are not quotations from WHO, EMA, or ICH text.
TOPICS = (
    {"meaning": "CO2 incubator qualification",
     "triggers": (("co2", "incubator"), ("carbon dioxide", "incubator"), ("incubator", "qualif")),
     "why": "The query is about qualifying a CO2 incubator.",
     "guidelines": ("equipment",)},
    {"meaning": "Equipment qualification",
     "triggers": (("equipment", "qualif"), ("installation qualification",), ("operational qualification",), ("performance qualification",)),
     "why": "The query is about equipment qualification.",
     "guidelines": ("equipment",)},
    {"meaning": "Line clearance",
     "triggers": (("line clearance",), ("retained", "label")),
     "why": "The query is about line clearance or retained labels.",
     "guidelines": ("line",)},
    {"meaning": "Out-of-specification result",
     "triggers": (("out of specification",), ("out-of-specification",), ("oos",)),
     "why": "The query is about an out-of-specification result.",
     "guidelines": ("oos",)},
    {"meaning": "Fill-weight check",
     "triggers": (("fill-weight",), ("fill weight",), ("weight", "recorded")),
     "why": "The query is about a fill-weight check.",
     "guidelines": ("weight",)},
    {"meaning": "Environmental monitoring",
     "triggers": (("environmental monitoring",), ("grade a",), ("aseptic",)),
     "why": "The query is about environmental or aseptic control.",
     "guidelines": ("environment",)},
    {"meaning": "Cleaning",
     "triggers": (("cleaning",), ("residue",)),
     "why": "The query is about cleaning or residue.",
     "guidelines": ("cleaning",)},
)

GUIDELINES = {
    "equipment": (
        {"id": "fda-211-63", "body": "US FDA", "cfr": "21 CFR 211.63",
         "title": "21 CFR 211.63 Equipment design, size, and location",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.63",
         "note": "Associated because this section covers the design of equipment used in manufacture."},
        {"id": "fda-211-68", "body": "US FDA", "cfr": "21 CFR 211.68",
         "title": "21 CFR 211.68 Automatic, mechanical, and electronic equipment",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.68",
         "note": "Associated because this section covers controls and calibration of automated equipment."},
        {"id": "ich-q7-equipment", "body": "ICH",
         "title": "ICH Q7, Equipment",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers equipment used in manufacture, including qualification. This is the publication, not a copied passage."},
        {"id": "ema-annex15", "body": "EMA",
         "title": "EU GMP Annex 15, Qualification and validation",
         "url": "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en",
         "note": "Associated because Annex 15 covers qualifying equipment before it is used. This is the publication, not a copied passage."},
        {"id": "who-equipment", "body": "WHO",
         "title": "WHO GMP, premises and equipment",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers premises and equipment used in production. This is the publication, not a copied passage."},
    ),
    "line": (
        {"id": "fda-211-130", "body": "US FDA", "cfr": "21 CFR 211.130",
         "title": "21 CFR 211.130 Packaging and labeling operations",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.130",
         "note": "Associated because this section covers examination of packaging and labeling facilities before use."},
        {"id": "ich-q7-line", "body": "ICH", "title": "ICH Q7, Production and process controls",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers controls during production. This is the publication, not a copied passage."},
        {"id": "ema-line", "body": "EMA", "title": "EU GMP, production",
         "url": "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en",
         "note": "Associated because EU GMP production text covers line clearance. This is the publication, not a copied passage."},
        {"id": "who-line", "body": "WHO", "title": "WHO GMP, production",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers controls during production. This is the publication, not a copied passage."},
    ),
    "oos": (
        {"id": "fda-211-192", "body": "US FDA", "cfr": "21 CFR 211.192",
         "title": "21 CFR 211.192 Production record review",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.192",
         "note": "Associated because this section covers investigation of unexplained discrepancies and out-of-specification results."},
        {"id": "fda-oos", "body": "US FDA", "title": "FDA Investigating Out-of-Specification Test Results",
         "url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/investigating-out-specification-oos-test-results-pharmaceutical-production",
         "note": "Associated because this FDA guidance covers laboratory out-of-specification investigations."},
        {"id": "ich-q7-lab", "body": "ICH", "title": "ICH Q7, Laboratory controls",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers laboratory investigations. This is the publication, not a copied passage."},
        {"id": "who-lab", "body": "WHO", "title": "WHO GMP, quality control",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers out-of-specification investigations. This is the publication, not a copied passage."},
    ),
    "weight": (
        {"id": "fda-211-110", "body": "US FDA", "cfr": "21 CFR 211.110",
         "title": "21 CFR 211.110 Sampling and testing of in-process materials",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.110",
         "note": "Associated because this section covers in-process tests and controls."},
        {"id": "ich-q7-weight", "body": "ICH", "title": "ICH Q7, Production and in-process controls",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers in-process controls. This is the publication, not a copied passage."},
        {"id": "ema-weight", "body": "EMA", "title": "EU GMP, production and in-process controls",
         "url": "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en",
         "note": "Associated because EU GMP covers in-process checks. This is the publication, not a copied passage."},
        {"id": "who-weight", "body": "WHO", "title": "WHO GMP, production",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers in-process controls. This is the publication, not a copied passage."},
    ),
    "environment": (
        {"id": "fda-211-42", "body": "US FDA", "cfr": "21 CFR 211.42",
         "title": "21 CFR 211.42 Design and construction features",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.42",
         "note": "Associated because this section covers control of air and environmental conditions."},
        {"id": "fda-211-46", "body": "US FDA", "cfr": "21 CFR 211.46",
         "title": "21 CFR 211.46 Ventilation, air filtration, air heating and cooling",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.46",
         "note": "Associated because this section covers air supplied to production areas."},
        {"id": "ema-annex1", "body": "EMA", "title": "EU GMP Annex 1, Manufacture of sterile products",
         "url": "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en",
         "note": "Associated because Annex 1 covers environmental monitoring for sterile manufacture. This is the publication, not a copied passage."},
        {"id": "who-hvac", "body": "WHO", "title": "WHO GMP, heating, ventilation, and air-conditioning",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers environmental control. This is the publication, not a copied passage."},
        {"id": "ich-q7-facilities", "body": "ICH", "title": "ICH Q7, Buildings and facilities",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers facilities and utilities. This is the publication, not a copied passage."},
    ),
    "cleaning": (
        {"id": "fda-211-67", "body": "US FDA", "cfr": "21 CFR 211.67",
         "title": "21 CFR 211.67 Equipment cleaning and maintenance",
         "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/section-211.67",
         "note": "Associated because this section covers cleaning of equipment."},
        {"id": "ich-q7-clean", "body": "ICH", "title": "ICH Q7, Equipment cleaning",
         "url": "https://database.ich.org/sites/default/files/Q7_Guideline.pdf",
         "note": "Associated because ICH Q7 covers equipment cleaning. This is the publication, not a copied passage."},
        {"id": "ema-annex15-clean", "body": "EMA", "title": "EU GMP Annex 15, cleaning validation",
         "url": "https://health.ec.europa.eu/medicinal-products/eudralex/eudralex-volume-4_en",
         "note": "Associated because Annex 15 covers cleaning validation. This is the publication, not a copied passage."},
        {"id": "who-clean", "body": "WHO", "title": "WHO GMP, sanitation and hygiene",
         "url": "https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications/norms-and-standards-for-pharmaceuticals/guidelines/production",
         "note": "Associated because WHO GMP covers cleaning. This is the publication, not a copied passage."},
    ),
}

BODY_COLOR = {"US FDA": "#1239b8", "ICH": "#a13de0", "EMA": "#3d7dff", "WHO": "#0e8f9a"}


def subject(query):
    """The meaning of the audit query and the guidelines that cover that subject."""
    text = _plain_query(query)
    for topic in TOPICS:
        if _matches(text, topic["triggers"]):
            guides = []
            for key in topic["guidelines"]:
                for item in GUIDELINES[key]:
                    guides.append(dict(item))
            return {"meaning": topic["meaning"], "why": topic["why"], "guidelines": guides}
    sentence = " ".join(text.split())
    meaning = (sentence[:120] + ("…" if len(sentence) > 120 else "")) if sentence else "Audit query"
    return {"meaning": meaning, "why": "The query did not match a guideline subject on file.", "guidelines": []}


GENERIC = {"qualification", "qualify", "qualified", "process", "procedure", "recorded", "checks", "check",
            "issue", "issues", "incomplete", "during", "equipment", "control", "controls", "manufacturing",
            "facility", "document", "record", "records", "batch", "deviation", "impact", "impacted",
            "query", "audit", "product", "class", "vaccine", "plant", "about", "which", "there", "their",
            "where", "after", "before", "shall", "should", "found", "using", "used", "from", "with",
            "this", "that", "were", "been", "have", "into"}


def _specific_terms(query):
    text = _plain_query(query).lower()
    words = re.findall(r"[a-z0-9][a-z0-9-]{2,}", text)
    seen, specific = set(), []
    for word in words:
        if word in seen or word in GENERIC or (len(word) < 4 and word not in {"co2", "iq", "oq", "pq", "hvac"}):
            continue
        seen.add(word)
        specific.append(word)
    return specific


def impact(query, passage, same_facility):
    """Direct impact is this facility. Distant impact is the same instrument or process at another facility."""
    terms = _specific_terms(query)
    low = (passage or "").lower()
    shared = [term for term in terms if term in low]
    if same_facility and shared:
        return {"kind": "direct", "shared": shared,
                "why": "Direct impact. This facility's record names " + ", ".join(shared[:4]) + "."}
    if shared and not same_facility:
        return {"kind": "distant", "shared": shared,
                "why": "Distant impact. Another facility follows a similar instrument or process (" + ", ".join(shared[:4]) + "), so the correction from this query can apply there."}
    return {"kind": "none", "shared": [], "why": "The record does not describe the instrument or process in the query."}


def _code(value):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def document_references(text, catalog):
    """Document IDs named inside a BMR, MFR, SOP, STP, or other stored file."""
    raw = text or ""
    known = []
    for item in catalog or []:
        if isinstance(item, str):
            ident = item
        elif isinstance(item, dict):
            ident = item.get("id") or ""
        else:
            continue
        code = _code(ident)
        if ident and code:
            known.append((ident, code))
    found = []
    for ident, code in known:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(ident) + r"(?![A-Za-z0-9])", raw, re.I):
            found.append(ident)
    for token in re.findall(r"\b(?:SOP|STP|BMR|MFR|Protocol|Deviation|OOS|Qualification)[-\s_/]?[A-Za-z0-9][A-Za-z0-9._/-]{0,24}", raw, re.I):
        code = _code(token)
        if not re.search(r"\d", code):
            continue
        for ident, ident_code in known:
            if ident_code == code or ident_code.endswith(code):
                found.append(ident)
    ordered = []
    for ident in found:
        if ident not in ordered:
            ordered.append(ident)
    return ordered


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
