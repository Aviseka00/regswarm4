"""Live evidence-driven workflow without seeded facts or scripted responses."""
import threading

from . import audit, context, llm, references, retrieval, roster, sitedocs, store

SOURCE_KIND = {
    "SOP": ("Standard operating procedures", "Controlled procedure"),
    "STP": ("Standard test procedures", "Laboratory method"),
    "BMR": ("Batch manufacturing records", "Batch record"),
    "MFR": ("Master formula records", "Master formula"),
    "Protocol": ("Protocols", "Study protocol"),
    "Deviation": ("Deviations", "Quality event"),
    "OOS": ("Out-of-specification records", "Laboratory event"),
    "Qualification": ("Qualification records", "Qualification"),
}


def source_systems(documents):
    """One QMS source per document class, plus the US FDA text already in the corpus."""
    counts = {}
    for document in documents:
        group = document.get("group") or "Record"
        counts[group] = counts.get(group, 0) + 1
    preferred = [name for name in SOURCE_KIND if name in counts]
    rest = sorted(name for name in counts if name not in SOURCE_KIND)
    systems = []
    for name in preferred + rest:
        title, kind = SOURCE_KIND.get(name, (name, "Site record"))
        systems.append({"id": name, "name": title, "short": name, "kind": kind,
                        "protocol": "Stored library", "count": counts[name]})
    systems.append({"id": "FDA", "name": "US FDA 21 CFR", "short": "US FDA", "kind": "Regulation text",
                    "protocol": "eCFR", "count": 0})
    return systems


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
    for document in documents:
        document["system"] = document.get("group") or "Record"
    systems = source_systems(documents)
    library = {"docs": documents, "systems": [item for item in systems if item["id"] != "FDA"],
               "group_labels": {d["group"]: d["group"] for d in documents}}
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
        n_agents=len(roster.ROSTER), n_docs=len(documents), systems=systems)
    c.audit("system", "case_opened", {"case": case["id"], "mode": "live", "obs_sha256": pipeline.sha(case["observation"])})
    public = {}

    def _load_references():
        public["value"] = references.lookup(case["observation"])

    reference_lookup = threading.Thread(target=_load_references, daemon=True)
    reference_lookup.start()

    def call(role, inputs):
        actors = {"classify": "T102", "decompose": "T103", "map": "A01", "frame": "T303", "rca": "T301",
                  "change_control": "F03", "capa": "T302", "draft": "T303", "redteam": "T403", "revise": "T303"}
        c.on(actors[role], f"Live {role}", wait=0)
        c.log("T303", "SYS", f"Live analysis: {role}", wait=0)
        try:
            if not llm.model_needed(model, role):
                result = llm.local_answer(role, inputs)
                model.calls.append({"role": role, "model": "on-this-computer", "provider": "local", "usage": {}, "seconds": 0})
            else:
                result = model.call(role, {"facts": {}, "input": inputs})
        except (RuntimeError, ValueError, TimeoutError) as error:
            c.log("T303", "SYS", f"Provider unavailable ({error}). This step finished on this computer at no cost.", wait=0)
            result = llm.local_answer(role, inputs)
            model.calls.append({"role": role, "model": "on-this-computer", "provider": "local", "usage": {}, "seconds": 0})
        run.metrics["llm_calls"] = model.calls
        c.audit("model", role, {"output_sha256": pipeline.sha(result), "model": model.model})
        store.save(con, run)
        c.off(actors[role])
        return result

    base = {"observation": case["observation"], "authority": case["authority"], "product_class": case["product_class"]}

    def evidence_from(selected_docs):
        built = {}
        for document in documents:
            if document["id"] in selected_docs:
                built["EV-" + document["id"]] = {"kind": document["group"], "label": document["title"],
                    "detail": document["source"], "version": document["version"], "date": document["date"],
                    "status": document["status"], "sha256": document["sha256"], "facility": document.get("facility") or "",
                    "passages": selected_docs[document["id"]]}
        return built

    c.stage(0)
    run.emit("upload", state="received", name=case["title"], chars=len(case["observation"]),
             words=len(case["observation"].split()), sha256=pipeline.sha(case["observation"]))
    run.emit("upload", state="parsed", entities=run.case_context["entities"], lines=[case["observation"]])
    run.emit("case_context", **run.case_context)
    run.emit("query_core", phase="query", observation=case["observation"])
    query_subject = references.subject(case["observation"])
    c.node("OBS", query_subject["meaning"][:32], "OBS", "observation", size=3, title=query_subject["meaning"] + ". " + query_subject["why"])
    c.log("T102", "SYS", "The query is in the RegSwarm core. Sources are read next.", wait=0)
    c.stage(1)
    for source in systems:
        if source["id"] != "FDA":
            run.emit("qms_system", state="connected", **source)
        c.log("F10", "SYS", "The core is fetching the current SOP, STP, BMR, MFR, and other records for this facility and the same product. Each retrieved Word or PDF file is read in full, including later pages and table rows.", wait=0)
    c.stage(2)
    for offset in range(0, len(documents), 20):
        batch = documents[offset:offset + 20]
        run.emit("doc_batch", system="library", fetched=offset + len(batch), total=len(documents),
                 items=[{k: d.get(k, "") for k in ("id", "title", "group", "version", "status", "date", "plant", "facility")} for d in batch])
    unread = [document["title"] for document in documents if not any((section.get("text") or "").strip() for section in (document.get("sections") or []))]
    if unread:
        c.log("F10", "SYS", "These files had no selectable text and were not read: " + "; ".join(unread[:8]), wait=0)
    run.emit("inventory", **sitedocs.inventory(library))
    index = sitedocs.Index(library)
    hits, selected = {}, {}
    try:
        c.stage(3)
        found = sitedocs.ensure_groups(index.search(case["observation"], k=80, facility=case.get("site_name"), product=case.get("product_class")), documents, k=24, cap=2)
        hits["QRY"] = found
        by_id = {document["id"]: document for document in documents}
        def remember(hit):
            if hit["doc_id"] in selected:
                return
            source = by_id.get(hit["doc_id"]) or {}
            sections = [{"ref": section.get("ref") or "Document", "text": section.get("text") or ""}
                        for section in (source.get("sections") or []) if (section.get("text") or "").strip()]
            selected[hit["doc_id"]] = sections or [{"ref": hit["ref"], "text": hit["passage"]}]
        home_name = (case.get("site_name") or "").strip().lower()
        shown = set()
        def link_document(hit):
            remember(hit)
            source = by_id.get(hit["doc_id"]) or {}
            plant = source.get("plant") or "Plant"
            facility = source.get("facility") or "Facility"
            same = facility.strip().lower() == home_name
            passage = " ".join(section.get("text") or "" for section in (source.get("sections") or [])) or hit.get("passage") or ""
            found_impact = references.impact(case["observation"], f"{hit.get('title') or ''} {passage}", same)
            if found_impact["kind"] == "none":
                return
            kind = found_impact["kind"]
            color = "#0f9f6b" if kind == "direct" else "#e38b2c"
            cluster = "DIR" if kind == "direct" else "DST"
            facility_id = "FAC-" + plant + "/" + facility
            shown.add(hit["doc_id"])
            c.node(facility_id, facility[:24], cluster, "location", title=found_impact["why"] + " " + plant + " / " + facility, color=color)
            c.edge("OBS", facility_id, kind)
            c.node("EV-" + hit["doc_id"], hit["doc_id"], cluster, "document", title=found_impact["why"] + " " + (hit.get("title") or ""), color=color)
            c.edge(facility_id, "EV-" + hit["doc_id"], "evidences")
            c.edge("OBS", "EV-" + hit["doc_id"], kind)
        for hit in found:
            link_document(hit)
        run.emit("pull_element", element="QRY", text=case["observation"], query=case["observation"],
                 scanned=len(documents), matched=len(found), hits=found)
        c.stage(4)
        clauses = {}
        for hit in retrieval.search(con, case["observation"], k=5, doc_prefix="21 CFR 21"):
            clauses[hit["ref"]] = hit
        reference_lookup.join(timeout=2.5)
        loaded = public.get("value") or {"catalog": [dict(item) for item in references.CATALOG], "recalls": [],
                                         "note": "openFDA could not be reached. The publication list is still available.",
                                         "recommendation": dict(references.RECOMMENDATION)}
        run.emit("qms_system", state="connected", id="FDA", name="US FDA 21 CFR", short="US FDA",
                 kind="Regulation text", protocol="eCFR", count=len(clauses))
        for guide in query_subject["guidelines"]:
            guide_id = "GDL-" + guide["id"]
            label = (guide.get("cfr") or guide["body"]).replace("21 CFR ", "")[:18]
            c.node(guide_id, label, "GDL", "guideline", size=2, title=guide["body"] + " · " + guide["title"] + ". " + guide["note"],
                   color=references.BODY_COLOR.get(guide["body"], "#1239b8"))
            c.edge("OBS", guide_id, "guides")
            if guide.get("cfr"):
                loaded_clause = retrieval.lookup(con, guide["cfr"])
                if loaded_clause:
                    clauses[loaded_clause["ref"]] = loaded_clause
                    c.node(loaded_clause["ref"], pipeline.short_ref(loaded_clause["ref"]), "REG", "clause", title=loaded_clause["heading"])
                    c.edge(guide_id, loaded_clause["ref"], "part")
        names = ", ".join(dict.fromkeys(guide["body"] for guide in query_subject["guidelines"]))
        c.log("A01", "SYS", query_subject["why"] + (" Guidelines on the graph: " + names + "." if names else ""), wait=0)
        evidence = evidence_from(selected)
        c.stage(5)
        run.emit("analyze_core", phase="analyze", documents=len(selected), guidelines=len(clauses),
                 sources=sum(1 for source in systems if source["id"] != "FDA"))
        c.log("T303", "SYS", "The core is analyzing the query, the retrieved documents, and the guidelines together.", wait=0)
        c.stage(6)
        classification = call("classify", {**base, "evidence": evidence,
            "clause_library": {k: v["text"] for k, v in clauses.items()},
            "roster": [{"id": a["id"], "name": a["name"]} for a in roster.ROSTER]})
        for agent_id in classification.get("activate") or []:
            agent = roster.BY_ID.get(agent_id)
            if agent:
                c.on(agent_id, agent["name"], wait=0)
                c.off(agent_id)
        run.emit("classification", **{k: classification.get(k) for k in ("authority", "document_type", "product_class", "domains", "confidence")})
        c.stage(7)
        decomposition = call("decompose", {**base, "evidence": evidence})
        elements = decomposition["elements"]
        element_ids = {e["id"] for e in elements}
        run.emit("elements", elements=elements)
        for element in elements:
            c.node(element["id"], element["id"], "OBS", "element", title=element["text"])
            c.edge("OBS", element["id"], "part")
            query = decomposition.get("doc_queries", {}).get(element["id"], element["text"])
            refined = sitedocs.ensure_groups(index.search(query, k=80, facility=case.get("site_name"), product=case.get("product_class")), documents, k=24, cap=2)
            hits[element["id"]] = refined
            for hit in refined:
                link_document(hit)
                c.edge("EV-" + hit["doc_id"], element["id"], "evidences")
            run.emit("pull_element", element=element["id"], text=element["text"], query=query,
                     scanned=len(documents), matched=len(refined), hits=refined)
        evidence = evidence_from(selected)
        catalog = [{"id": document["id"]} for document in documents]
        texts = {document["id"]: (document.get("title") or "") + "\n" + "\n".join((section.get("text") or "") for section in (document.get("sections") or [])) for document in documents}
        cites = {ident: [item for item in references.document_references(text, catalog) if item != ident] for ident, text in texts.items()}
        wave = list(shown)
        traced = 0
        for _ in range(2):
            nxt = []
            for source in wave:
                for target in cites.get(source, []):
                    if target not in shown:
                        c.node("EV-" + target, target, "REF", "document", title="Referenced from " + source + ". The stored text names this document.", color="#5a72f7")
                        shown.add(target)
                        nxt.append(target)
                    before = len(c.run.edges_seen)
                    c.edge("EV-" + source, "EV-" + target, "refers")
                    traced += len(c.run.edges_seen) - before
            wave = nxt
        if traced:
            c.log("F02", "SYS", str(traced) + " document reference" + ("s" if traced != 1 else "") + " traced between BMR, MFR, SOP, STP, and the other stored files.", wait=0)
        run.emit("pull_findings", findings=[])
        run.emit("pull_done", funnel=[{"label": "Imported documents", "value": len(documents)},
                                      {"label": "Retrieved documents", "value": len(selected)}])
        c.stage(8)
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
        run.emit("qms_system", state="connected", id="FDA", name="US FDA 21 CFR", short="US FDA",
                 kind="Regulation text", protocol="eCFR", count=len({item["ref"] for item in mapped}))
        run.emit("evidence_context", elements=packets)
    finally:
        index.con.close()
    c.log("F02", "SYS", "The core analyzed the query against the retrieved passages and the guideline text.", wait=0)
    inputs = {**base, "elements": elements, "case_context": run.case_context, "evidence_packets": packets,
              "evidence": evidence, "clause_library": {k: v["text"] for k, v in clauses.items()}, "facts": {}, "findings": [],
              "public_references": loaded}
    c.stage(9)
    frame = call("frame", inputs)
    run.emit("frame", sections=[{**s, "feeds": [], "regs": []} for s in frame["sections"]])
    rca = call("rca", inputs)
    run.emit("rca", **rca)
    c.stage(10)
    changes = call("change_control", {**inputs, "rca": rca})
    for item in changes["items"]:
        if set(item.get("targets", [])) - set(selected):
            raise ValueError("Change control targets evidence outside the retrieved case documents")
    run.emit("change_control", items=[{**item, "impacted": [], "target_docs": []} for item in changes["items"]])
    c.stage(11)
    actions = call("capa", {**inputs, "rca": rca})
    plan = [{"lane": lane, "text": a["text"], "owner": a["owner"], "day": pipeline._day(a["due"])}
            for lane in ("correction", "corrective", "preventive", "effectiveness") for a in actions.get(lane, [])]
    run.emit("capa", **actions, plan=plan)
    c.stage(12)
    packet = llm.risk_packet(case["observation"], evidence)
    run.emit("impact", matrix=packet["matrix"], summary=packet["summary"], batches=packet["batches"], docs=packet["docs"])
    c.log("F11", "SYS", "The cited passages are ready for QA. Severity is " + packet["summary"]["severity"] + ". " + packet["summary"].get("pair", "")[:240], wait=0)
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
