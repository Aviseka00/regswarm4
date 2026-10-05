"""Case-scoped evidence packets. Source linkage is not semantic proof."""
def build(case, entities, analysis, library):
    observation = case["observation"]
    locations = sorted({e.get("text", e.get("value", "")) for e in entities if "location" in e.get("kind", "").lower()})
    return {
        "case_id": case["id"], "observation": observation,
        "synthetic": case.get("synthetic", True), "site_export": case["site_dir"],
        "scope": "Aseptic environmental monitoring; synthetic site export",
        "entities": entities, "locations": locations,
        "record_period": {"start": analysis["period_start"], "end": analysis["period_end"]},
        "document_count": len(library["docs"]),
        "limitations": ["Site analytics currently support the aseptic EM case family.",
                        "Record linkage and citation matching do not establish claim interpretation.",
                        "Root causes remain hypotheses until confirmed by investigation."],
    }


def packets(elements, hits, mappings, clauses):
    result = []
    for element in elements:
        refs = [m["ref"] for m in mappings if m["element"] == element["id"]]
        passages = [{k: h[k] for k in ("doc_id", "title", "version", "status", "date", "ref", "passage", "relevance")}
                    for h in hits.get(element["id"], [])]
        regulations = [{"ref": ref, "text": clauses[ref]["text"], "as_of": clauses[ref]["as_of"], "url": clauses[ref]["url"]}
                       for ref in refs if ref in clauses]
        gaps = []
        if not passages:
            gaps.append("No matching site passage retrieved")
        if not regulations:
            gaps.append("No regulatory clause mapped")
        result.append({**element, "passages": passages, "regulations": regulations, "gaps": gaps})
    return result


def enrich(evidence, library, site, rows, analysis):
    for document in library["docs"]:
        key = "EV-" + document["id"]
        evidence[key] = {**evidence.get(key, {}), "label": document["title"], "kind": document["group"],
                         "version": document["version"], "date": document["date"], "status": document["status"],
                         "passages": document["sections"], "metadata": document.get("meta", {})}
    for record in site.get("deviations", []) + site.get("trend_register", []) + site.get("aps", []):
        key = "EV-" + record["id"]
        if key in evidence:
            evidence[key]["record"] = record
    evidence["EV-EM-DATA"]["computed_facts"] = {k: v for k, v in analysis.items() if isinstance(v, (int, float, str))}
    evidence["EV-EM-DATA"]["source_rows"] = len(rows)
    return evidence


def review_packet(run, evidence, packets_, issues, revision):
    claimed = set(revision.get("resolves", []))
    reviews = []
    for issue in issues:
        reviews.append({**issue, "status": "review_required",
                        "proposed_resolution": issue["id"] in claimed,
                        "reason": "A proposed fix requires independent reviewer confirmation."})
    claims = []
    for section in run.draft["sections"]:
        for claim in section["claims"]:
            checks = run.claim_res[claim["id"]]
            claims.append({**claim, "section": section["title"], "checks": checks,
                           "support_status": "blocked" if checks["status"] == "removed" else
                           ("proposed_commitment" if claim["kind"] == "action" else "interpretation_review_required"),
                           "sources": [{"id": key, **evidence[key]} for key in claim.get("evidence", []) if key in evidence]})
    return {"case": run.case_context, "elements": packets_, "claims": claims, "issues": reviews,
            "summary": {"claims": len(claims), "blocked": sum(c["support_status"] == "blocked" for c in claims),
                        "interpretations": sum(c["support_status"] == "interpretation_review_required" for c in claims),
                        "evidence_gaps": sum(len(p["gaps"]) for p in packets_), "issues_to_review": len(reviews)}}
