"""Live evidence-driven workflow without seeded facts or scripted responses."""
from . import audit, context, llm, retrieval, roster, sitedocs, store


def check_claim_scope(draft, evidence_ids, clause_refs, element_ids):
    llm.validate("draft", draft)
    for section in draft["sections"]:
        for claim in section["claims"]:
            if set(claim.get("evidence", [])) - evidence_ids:
                raise ValueError("Model cited evidence outside this case's retrieved context")
            if any(citation["ref"] not in clause_refs for citation in claim.get("cites", [])):
                raise ValueError("Model cited a clause outside the supplied clause library")
            if set(claim.get("elements", [])) - element_ids:
                raise ValueError("Model referenced an unknown observation element")


def execute(run, c, case):
    from . import pipeline
    if case.get("synthetic") is not False or "documents" not in case:
        raise ValueError("Only imported real-evidence case packages can be processed")
    model = llm.make_llm("live", case)
    documents = case["documents"]
    system = {"id": "DMS", "name": "Imported source documents", "short": "DMS", "kind": "Validated JSON export",
              "protocol": "Local import", "count": len(documents)}
    library = {"docs": documents, "systems": [system], "group_labels": {d["group"]: d["group"] for d in documents}}
    con = c.con
    sources = [dict(row) for row in con.execute("SELECT doc_id,as_of FROM sources ORDER BY doc_id")]
    currency = min((s["as_of"] for s in sources), default="unknown")
    run.case_context = {"case_id": case["id"], "observation": case["observation"], "synthetic": False,
        "site_export": case["site_name"], "scope": f"{case['authority']} · {case['product_class']}",
        "record_period": {"start": min(d["date"] for d in documents), "end": max(d["date"] for d in documents)},
        "document_count": len(documents), "entities": pipeline.parse_observation(case["observation"]),
        "limitations": ["Uploaded source authenticity must be assessed by the reviewer.",
                        "Retrieval and citation matching do not establish semantic support.",
                        "No site metrics are inferred from the former demonstration dataset."]}
    run.emit("case_start", case_id=case["id"], title=case["title"], mode="live", mode_label=model.label,
        synthetic=False, notes=run.case_context["limitations"], observation=case["observation"],
        corpus={"sources": sources, "as_of": currency}, stages=[{"name": n, "sub": s} for n, s in pipeline.STAGES],
        n_agents=sum(a["implemented"] for a in roster.ROSTER), n_docs=len(documents), systems=[system])
    c.audit("system", "case_opened", {"case": case["id"], "mode": "live", "obs_sha256": pipeline.sha(case["observation"])})
    c.stage(0)
    run.emit("upload", state="received", name=case["title"], chars=len(case["observation"]),
             words=len(case["observation"].split()), sha256=pipeline.sha(case["observation"]))
    run.emit("upload", state="parsed", entities=run.case_context["entities"], lines=[case["observation"]])
    run.emit("case_context", **run.case_context)

    def call(role, inputs):
        actors = {"classify": "T102", "decompose": "T103", "map": "A01", "frame": "T303", "rca": "T301",
                  "change_control": "F03", "capa": "T302", "draft": "T303", "redteam": "T403", "revise": "T303"}
        c.on(actors[role], f"Live {role}", wait=0)
        c.log("T303", "SYS", f"Live analysis: {role}", wait=0)
        result = model.call(role, {"facts": {}, "input": inputs})
        run.metrics["llm_calls"] = model.calls
        c.audit("model", role, {"output_sha256": pipeline.sha(result), "model": model.model})
        store.save(con, run)
        c.off(actors[role])
        return result

    base = {"observation": case["observation"], "authority": case["authority"], "product_class": case["product_class"]}
    c.stage(1)
    classification = call("classify", {**base, "roster": [{"id": a["id"], "name": a["name"]} for a in roster.ROSTER if a["implemented"]]})
    run.emit("classification", **{k: classification.get(k) for k in ("authority", "document_type", "product_class", "domains", "confidence")})
    c.stage(2)
    decomposition = call("decompose", base)
    elements = decomposition["elements"]
    element_ids = {e["id"] for e in elements}
    run.emit("elements", elements=elements)
    c.node("OBS", "Observation", "OBS", "observation", size=3)
    for element in elements:
        c.node(element["id"], element["id"], "OBS", "element", title=element["text"])
        c.edge("OBS", element["id"], "part")
    c.stage(3)
    run.emit("qms_system", state="connected", **system)
    c.log("F10", "SYS", "Analyzing the imported evidence export; no live QMS connector is configured", wait=0)
    c.stage(4)
    for offset in range(0, len(documents), 20):
        batch = documents[offset:offset + 20]
        run.emit("doc_batch", system="DMS", fetched=offset + len(batch), total=len(documents),
                 items=[{k: d[k] for k in ("id", "title", "group", "version", "status", "date")} for d in batch])
    run.emit("inventory", **sitedocs.inventory(library))
    c.stage(5)
    index = sitedocs.Index(library)
    hits, selected = {}, {}
    try:
        for element in elements:
            query = decomposition.get("doc_queries", {}).get(element["id"], element["text"])
            found = sitedocs.diversify(index.search(query, k=50), k=6, cap=2)
            hits[element["id"]] = found
            for hit in found:
                selected.setdefault(hit["doc_id"], []).append({"ref": hit["ref"], "text": hit["passage"]})
                c.node("EV-" + hit["doc_id"], hit["doc_id"], "EVI", "document", title=hit["title"])
                c.edge("EV-" + hit["doc_id"], element["id"], "evidences")
            run.emit("pull_element", element=element["id"], text=element["text"], query=query,
                     scanned=len(documents), matched=len(found), hits=found)
    finally:
        index.con.close()
    run.emit("pull_findings", findings=[])
    run.emit("pull_done", funnel=[{"label": "Imported documents", "value": len(documents)},
                                  {"label": "Retrieved documents", "value": len(selected)}])
    evidence = {}
    for document in documents:
        if document["id"] in selected:
            evidence["EV-" + document["id"]] = {"kind": document["group"], "label": document["title"],
                "detail": document["source"], "version": document["version"], "date": document["date"],
                "status": document["status"], "sha256": document["sha256"], "passages": selected[document["id"]]}
    c.stage(6)
    clauses = {}
    for element in elements:
        for hit in retrieval.search(con, element["text"], k=5, doc_prefix="21 CFR 21"):
            clauses[hit["ref"]] = hit
    mapped = call("map", {"elements": elements, "clause_library": {k: v["text"] for k, v in clauses.items()}})["items"]
    for mapping in mapped:
        if mapping["ref"] not in clauses or mapping["element"] not in element_ids:
            raise ValueError("Model mapping references a clause or element outside the supplied library")
        hit = clauses[mapping["ref"]]
        c.node(hit["ref"], pipeline.short_ref(hit["ref"]), "REG", "clause", title=hit["heading"])
        c.edge(mapping["element"], hit["ref"], "maps")
    packets = context.packets(elements, hits, mapped, clauses)
    run.emit("mapping", items=[{**m, "heading": clauses[m["ref"]]["heading"], "as_of": clauses[m["ref"]]["as_of"]} for m in mapped])
    run.emit("evidence_context", elements=packets)
    c.stage(7)
    c.log("F02", "SYS", "Source passages selected. Site findings must cite these records; no precomputed site assumptions are injected.", wait=0)
    inputs = {**base, "elements": elements, "case_context": run.case_context, "evidence_packets": packets,
              "evidence": evidence, "clause_library": {k: v["text"] for k, v in clauses.items()}, "facts": {}, "findings": []}
    c.stage(8)
    frame = call("frame", inputs)
    run.emit("frame", sections=[{**s, "feeds": [], "regs": []} for s in frame["sections"]])
    rca = call("rca", inputs)
    run.emit("rca", **rca)
    c.stage(9)
    changes = call("change_control", {**inputs, "rca": rca})
    for item in changes["items"]:
        if set(item.get("targets", [])) - set(selected):
            raise ValueError("Change control targets evidence outside the retrieved case documents")
    run.emit("change_control", items=[{**item, "impacted": [], "target_docs": []} for item in changes["items"]])
    c.stage(10)
    actions = call("capa", {**inputs, "rca": rca})
    plan = [{"lane": lane, "text": a["text"], "owner": a["owner"], "day": pipeline._day(a["due"])}
            for lane in ("correction", "corrective", "preventive", "effectiveness") for a in actions.get(lane, [])]
    run.emit("capa", **actions, plan=plan)
    c.stage(11)
    c.log("F11", "SYS", "Impact conclusions require source evidence and reviewer assessment; no synthetic risk matrix is assigned.", wait=0)
    c.stage(12)
    run.draft = call("draft", {**inputs, "rca": rca, "capa": actions, "frame": frame, "change_control": changes["items"]})
    check_claim_scope(run.draft, set(evidence), set(clauses), element_ids)
    run.emit("draft", version="v0.1", sections=run.draft["sections"])
    c.stage(13)
    first = pipeline.link_and_verify(c, run, evidence, "v0.1", initial=True)
    c.stage(14)
    issues = call("redteam", {**inputs, "draft": run.draft, "verification": run.claim_res})["issues"]
    run.emit("redteam", issues=issues)
    revision = call("revise", {**inputs, "draft": run.draft, "red_team": issues,
                    "failed_citations": [{"claim": key, "reason": value["reason"]} for key, value in run.claim_res.items() if value["status"] == "removed"]})
    pipeline.apply_patch(run.draft, revision)
    check_claim_scope(run.draft, set(evidence), set(clauses), element_ids)
    run.version = "v0.2"
    run.emit("draft", version=run.version, sections=run.draft["sections"], revised=list(revision["replace"]))
    final = pipeline.link_and_verify(c, run, evidence, "v0.2", initial=False)
    run.review_packet = context.review_packet(run, evidence, packets, issues, revision)
    run.emit("review_packet", **run.review_packet)
    c.stage(15)
    run.score = pipeline.score(run, elements, issues, revision, first, final)
    run.emit("score", **run.score)
    run.document = pipeline.assemble(run, case)
    c.audit("system", "review_packet_created", {"doc_sha256": pipeline.sha(run.document), "score": run.score})
    run.status = "awaiting_review"
    run.emit("gate", state=run.status, version=run.version, doc_sha256=pipeline.sha(run.document),
             open_items=run.score["open_items"], audit={"intact": audit.verify_chain(con)[0]})
    run.emit("done")
