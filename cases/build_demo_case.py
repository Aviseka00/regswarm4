"""Builds cases/demo_em_483.json - the SYNTHETIC demo case.

The observation, site data and agent wording are invented for the demo. Regulation
quotes below are checked by the citation verifier against the real eCFR text at run
time; two deliberate errors (marked SEEDED) are included in draft v0.1 so the demo
shows the verifier catching them. Edit this file and re-run it to change the demo.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEVS = ["EV-DEV-26-%04d" % n for n in range(407, 471, 7)]

OBSERVATION = (
    "OBSERVATION 1\n"
    "Procedures designed to prevent microbiological contamination of drug products purporting to be sterile "
    "are not followed, and environmental monitoring excursions are not adequately investigated.\n\n"
    "Specifically, between April and June 2026, Grade A (ISO 5) viable environmental monitoring results at or "
    "above the action limit were recorded in the aseptic filling zone of Filling Line 2 on multiple occasions, "
    "including repeated results at the stopper bowl location. The associated deviations were closed as "
    "\"no product impact\" without a determined root cause. There was no documented assessment of other batches "
    "filled during the period. Quarterly environmental monitoring trend reports required by your procedure "
    "SOP-EM-014 were not issued for the first and second quarters of 2026."
)

ELEMENTS = [
    {"id": "E1", "text": "Aseptic procedures did not prevent recurring Grade A viable excursions on Filling Line 2"},
    {"id": "E2", "text": "Excursion deviations closed 'no product impact' without a determined root cause"},
    {"id": "E3", "text": "No assessment of other batches filled during the period"},
    {"id": "E4", "text": "Required EM trend reports (SOP-EM-014) not issued for Q1 and Q2 2026"},
    {"id": "E5", "text": "Quality unit did not ensure errors were fully investigated before batch decisions"},
]

QUERIES = [
    {"agent": "A01", "q": "procedures to prevent microbiological contamination of sterile drug products, validation of aseptic processes"},
    {"agent": "A01", "q": "system for monitoring environmental conditions in aseptic processing areas"},
    {"agent": "A01", "q": "unexplained discrepancy thoroughly investigated, investigation shall extend to other batches, written record"},
    {"agent": "A01", "q": "quality control unit responsibility authority review production records errors fully investigated"},
    {"agent": "A01", "q": "written procedures shall be followed, deviation from written procedures recorded and justified"},
    {"agent": "A01", "q": "personnel training in the particular operations the employee performs"},
]

MAP = [
    ("E1", "21 CFR 211.113(b)", "Requires written contamination-prevention procedures that are 'established and followed'; recurring Grade A excursions show they are not effective."),
    ("E1", "21 CFR 211.42(c)(10)(iv)", "Aseptic areas must have a system for monitoring environmental conditions; the monitoring detected the problem but nothing acted on it."),
    ("E1", "21 CFR 211.25(a)", "Personnel must be trained in the particular operations they perform, including aseptic interventions."),
    ("E2", "21 CFR 211.192", "Unexplained discrepancies must be thoroughly investigated and the record must include conclusions and follow-up."),
    ("E3", "21 CFR 211.192", "The investigation must extend to other batches that may have been associated with the failure."),
    ("E4", "21 CFR 211.100(b)", "Written procedures (here SOP-EM-014 section 9.1) must be followed; departures must be recorded and justified."),
    ("E5", "21 CFR 211.22(a)", "The quality control unit must ensure errors are fully investigated."),
]

Q_113B_A = "Appropriate written procedures, designed to prevent microbiological contamination of drug products purporting to be sterile, shall be established and followed"
Q_113B_B = "Such procedures shall include validation of all aseptic and sterilization processes"
Q_42 = "A system for monitoring environmental conditions"
Q_192_A = "shall be thoroughly investigated, whether or not the batch has already been distributed"
Q_192_B = "The investigation shall extend to other batches of the same drug product and other drug products that may have been associated with the specific failure or discrepancy"
Q_192_C = "A written record of the investigation shall be made and shall include the conclusions and followup"
Q_22 = "that no errors have occurred or, if errors have occurred, that they have been fully investigated"
Q_100 = "Any deviation from the written procedures shall be recorded and justified"
Q_25 = "Training shall be in the particular operations that the employee performs"
Q_188 = "Any investigation made according to § 211.192"
Q_100A = "These written procedures, including any changes, shall be drafted, reviewed, and approved by the appropriate organizational units and reviewed and approved by the quality control unit"
EXC_EBR = ["EV-EBR-FL2-B26-%d" % (100 + w) for w in (2, 3, 5, 6, 7, 8, 9, 10, 12)]
DOC_QUERIES = {
    "E1": "aseptic interventions stopper bowl Grade A excursions procedures contamination personnel gowning airflow",
    "E2": "deviation closure root cause not determined no product impact investigation",
    "E3": "batch record review batches distributed batch impact assessment other batches release",
    "E4": "environmental monitoring trend report monthly quarterly summary",
    "E5": "quality unit review approval investigation batch release responsibility",
}


def reg(cid, text, cites, els):
    return {"id": cid, "kind": "regulatory", "text": text, "cites": cites, "elements": els}


def fact(cid, text, ev, els):
    return {"id": cid, "kind": "site_fact", "text": text, "evidence": ev, "elements": els}


def act(cid, text, els):
    return {"id": cid, "kind": "action", "text": text, "elements": els}


c4_good = reg("c4", "Unexplained discrepancies must be thoroughly investigated whether or not the batch has been distributed, "
              "and the written investigation record must include conclusions and follow-up.",
              [{"ref": "21 CFR 211.192", "quote": Q_192_A}, {"ref": "21 CFR 211.192", "quote": Q_192_C}], ["E2"])
# SEEDED DEFECT 1: fabricated quotation (a plausible-sounding invented deadline)
c4_bad = reg("c4", "Unexplained discrepancies must be investigated and closed within 30 days, with a written record.",
             [{"ref": "21 CFR 211.192", "quote": "shall be investigated and closed within 30 days of detection"}], ["E2"])
# SEEDED DEFECT 2: paragraph that does not exist in the section
c9_bad = reg("c9", "Corrective action is mandatory whenever repeated microbial excursions occur at one location.",
             [{"ref": "21 CFR 211.113(d)", "quote": "corrective action shall be initiated when repeated excursions occur"}], ["E1"])
c9_good = reg("c9", "The aseptic process, including its interventions, must be validated and maintained so that microbiological contamination is prevented.",
              [{"ref": "21 CFR 211.113(b)", "quote": Q_113B_B}], ["E1"])

DRAFT = {"sections": [
    {"id": "ack", "title": "Acknowledgment", "claims": [
        act("c1", "The site acknowledges Observation 1 and treats the Grade A environmental monitoring excursions in Filling Suite 2 "
                  "as a systemic quality-system failure, not as isolated events.", ["E1", "E2"])]},
    {"id": "basis", "title": "Regulatory basis", "claims": [
        reg("c2", "Aseptic operations must be governed by written procedures designed to prevent microbiological contamination, established and followed.",
            [{"ref": "21 CFR 211.113(b)", "quote": Q_113B_A}], ["E1"]),
        reg("c3", "Aseptic processing areas must include a system for monitoring environmental conditions.",
            [{"ref": "21 CFR 211.42(c)(10)(iv)", "quote": Q_42}], ["E1", "E4"]),
        c4_bad,
        reg("c5", "The quality control unit is responsible for ensuring that errors are fully investigated.",
            [{"ref": "21 CFR 211.22(a)", "quote": Q_22}], ["E2", "E5"]),
        reg("c6", "Written procedures must be followed and any deviation from them recorded and justified; this includes the site's own EM trending requirement.",
            [{"ref": "21 CFR 211.100(b)", "quote": Q_100}], ["E4"]),
        reg("c29", "Batch production and control records must include any investigation made under 21 CFR 211.192, so an excursion investigation must be traceable from the batch record.",
            [{"ref": "21 CFR 211.188(b)(12)", "quote": Q_188}], ["E2", "E3"])]},
    {"id": "rca", "title": "Root cause analysis", "claims": [
        fact("c7", "{n_exc} Grade A action-limit results were recorded in {n_samples_a} samples between {period_start} and {period_end}; "
                   "{hot_n} ({hot_share_pct}%) were at {hot_loc} ({hot_desc}), in {weeks_with_exc} of {n_weeks} weeks.", ["EV-EM-DATA"], ["E1"]),
        fact("c8", "{human_flora_pct}% of isolates ({human_flora_n} of {n_exc}) were human-associated flora (Staphylococcus, Micrococcus); "
                   "a personnel or intervention source is the leading hypothesis, to be confirmed by the reopened investigations.", ["EV-EM-DATA"], ["E1"]),
        c9_bad,
        fact("c10", "{n_closed_no_rc} of {n_devs} related deviations were closed with root cause 'Not determined' and none has a documented "
                    "batch-impact assessment, although SOP-EM-014 section 7.2 requires both.", ["EV-SOP-EM-014", "EV-SOP-QA-022"] + DEVS, ["E2", "E3"]),
        fact("c11", "EM trend reports for {missing_trend_periods} were not issued although SOP-EM-014 section 9.1 requires quarterly trend reports.",
             ["EV-SOP-EM-014", "EV-TR-2026-Q1", "EV-TR-2026-Q2"], ["E4"]),
        fact("c12", "The most recent aseptic process simulation on Line 2 (APS-2026-01, January 2026) passed, but it cannot show that the process stayed in control between April and June.",
             ["EV-APS-2026-01"], ["E1"]),
        fact("c24", "Executed batch records show {bmr_int_hot} Grade A interventions per batch on average where a {hot_loc} excursion occurred, against {bmr_int_rest} on the other batches; "
                    "QA batch-record review did not reference the excursion or a deviation in {n_bmr_unlinked} of {n_exc_bmr} excursion batches.",
             ["EV-SOP-QA-030", "EV-MBR-FL2-VIAL-10ML"] + EXC_EBR, ["E1", "E2", "E3"]),
        fact("c25", "{n_lapsed_batches} of {n_exc_bmr} excursion batches involved an operator whose aseptic requalification was overdue ({lapsed_ops}), against {n_nonexc_lapsed} of {n_nonexc_batches} batches without an excursion; "
                    "this is an association to be tested in the reopened investigations, not a confirmed cause.",
             ["EV-TM-FL2", "EV-TRN-OP-104", "EV-TRN-OP-107", "EV-SOP-GW-002"], ["E1"]),
        fact("c26", "Change control CC-26-031 (stopper-bowl modification, effective {cc_effective}) concluded no sterility impact and did not repeat the media fill or airflow visualisation; "
                    "the first {hot_loc} excursion followed {cc_gap_days} days later and the last airflow study predates the change by {smoke_gap_days} days.",
             ["EV-CC-26-031", "EV-APS-2026-01", "EV-RPT-VAL-HVAC-2025-07", "EV-EQ-FL2-STOPPER-PM", "EV-SOP-QA-018"], ["E1"]),
        fact("c27", "CAPA-25-019 addressed excursions at the same location in 2025 and was closed without its planned effectiveness check; internal audit IA-2025-11 had already flagged late EM reporting.",
             ["EV-CAPA-25-019", "EV-IA-2025-11", "EV-CAPA-25-031"], ["E1", "E4"]),
        fact("c28", "{n_dist} of the {n_exc_bmr} batches filled during excursion weeks are recorded as distributed in the batch-record archive.",
             EXC_EBR, ["E3"])]},
    {"id": "correction", "title": "Immediate corrections", "claims": [
        act("c13", "Day 2: place all Line 2 batches filled since {period_start} under quality hold pending batch-impact assessment (owner: Head of Quality).", ["E3"]),
        act("c14", "Day 5: reopen the {n_closed_no_rc} deviations closed without root cause and assign QA-led investigations covering interventions, gowning, personnel monitoring and cleaning records (owner: Head of Quality).", ["E2"]),
        act("c15", "Day 5: increase Grade A sampling and add active-air monitoring at {hot_loc} until the root cause is confirmed (owner: Head of Microbiology).", ["E1"])]},
    {"id": "capa", "title": "Corrective and preventive actions", "claims": [
        act("c16", "Day 30: complete a documented risk assessment (ICH Q9) of stopper-bowl interventions and implement any resulting design or procedural changes (owner: Head of Aseptic Operations).", ["E1"]),
        reg("c17", "Day 30: retrain and re-qualify aseptic operators in the particular operations they perform, focusing on Grade A interventions.",
            [{"ref": "21 CFR 211.25(a)", "quote": Q_25}], ["E1"]),
        act("c18", "Day 45: configure the eQMS so a Grade A excursion deviation cannot be closed without a QA-approved root cause and batch-impact assessment, and align SOP-EM-014 and SOP-QA-022 (owner: Head of Quality Systems).", ["E2", "E5"]),
        act("c19", "Day 15: issue the missing {missing_trend_periods} trend reports; from then on trend monthly with an automatic trigger for repeat excursions at one location (owner: Head of Microbiology).", ["E4"]),
        act("c20", "Day 120: effectiveness check - no Grade A action-limit recurrence at {hot_loc} for 90 days and 100% of excursion deviations closed with root cause and batch assessment (owner: Head of Quality).", ["E1", "E2"])]},
    {"id": "impact", "title": "Change control and impacted areas", "claims": [
        reg("c30", "Changes to written production and process-control procedures must be drafted, reviewed and approved by the appropriate units and by the quality control unit.",
            [{"ref": "21 CFR 211.100(a)", "quote": Q_100A}], ["E5"]),
        act("c31", "Day 15 to 45: open {n_cc} change controls (CC-NEW-01 to CC-NEW-05) covering requalification of the Line 2 stopper bowl, revision of SOP-EM-014 and SOP-QA-022, the eQMS closure gate, the batch-record checklist and the training block; {n_docs_revise} controlled documents are revised together under QA approval.", ["E1", "E2", "E5"]),
        fact("c32", "The impact assessment covers {n_exc_bmr} batches, Filling Line 2, Filling Line 1 (shared air handling unit AHU-07) and the deviation, change-control, trending and training systems.",
             ["EV-SMF-001", "EV-CERT-HVAC-FL2-2026", "EV-RPT-VAL-HVAC-2025-07"], ["E1", "E3"])]},
    {"id": "timeline", "title": "Timeline and commitments", "claims": [
        act("c21", "Written progress updates will be sent to FDA at Days 30, 60 and 90, with completed investigation reports.", ["E2", "E3"])]},
]}

REDTEAM = {"issues": [
    {"id": "R1", "severity": "high", "target_claim": "c13",
     "attack": "The response holds batches but never addresses batches already distributed; the regulation requires investigation whether or not the batch has been distributed.",
     "fix": "Add a commitment covering distributed batches: health-hazard evaluation and a documented recall decision."},
    {"id": "R2", "severity": "medium", "target_claim": "c4",
     "attack": "Two regulatory citations in the draft cannot be substantiated (an invented deadline and a paragraph that does not exist) - an inspector who checks them will discount the whole response.",
     "fix": "Replace both with verifiable citations or remove the claims."},
    {"id": "R3", "severity": "medium", "target_claim": "c20",
     "attack": "A 90-day effectiveness window is short for a pattern that persisted across 12 weeks; investigators commonly expect a longer confirmation period.",
     "fix": "Management to decide whether to extend the check to 6-12 months."},
]}

REVISE = {
    "replace": {"c4": c4_good, "c9": c9_good},
    "add": [
        {"section": "basis", "claim": reg("c22", "The investigation must extend to other batches of the same and other drug products that may have been associated with the failure.",
                                          [{"ref": "21 CFR 211.192", "quote": Q_192_B}], ["E3"])},
        {"section": "correction", "claim": act("c23", "Day 10: extend the batch-impact assessment to every Line 2 batch filled from {period_start} to {period_end}, including any distributed batches, with a documented health-hazard evaluation and a recall decision by the Head of Quality.", ["E3"])},
    ],
    "resolves": ["R1", "R2"],
}

CASE = {
    "id": "DEMO-483-EM-001",
    "title": "Grade A EM excursions closed without investigation (synthetic demo)",
    "synthetic": True,
    "seeded_defects": ["c4", "c9"],   # draft v0.1 claims that are wrong ON PURPOSE
    "site_dir": "demo_site",
    "upload_name": "FDA-483_Observation-1_demo.txt",
    "demo_notes": [
        "SYNTHETIC DEMO: observation and site data are invented; regulation text is real 21 CFR.",
        "Draft v0.1 deliberately contains 2 citation errors to show the verifier at work.",
    ],
    "observation": OBSERVATION,
    "evidence_links": {
        "EV-SOP-EM-014": ["E2", "E3", "E4"], "EV-SOP-QA-022": ["E2"], "EV-SOP-AS-003": ["E1"],
        "EV-TR-2026-Q1": ["E4"], "EV-TR-2026-Q2": ["E4"], "EV-APS-2026-01": ["E1"],
    },
    "script": {
        "classify": {
            "authority": "US FDA", "document_type": "FDA Form 483 observation",
            "product_class": "Sterile drug product, aseptic processing (21 CFR 211)",
            "domains": ["Environmental monitoring", "Aseptic processing", "Deviation and investigation", "Quality unit oversight"],
            "activate": ["A01", "G02", "F01", "F02", "F10", "H01", "F09", "F03", "F11"],
            "skip": [{"agent": "A02", "reason": "21 CFR 600-680 applies to licensed biologics; not triggered by this product class"}],
            "confidence": 0.97},
        "decompose": {"elements": ELEMENTS, "queries": QUERIES, "doc_queries": DOC_QUERIES},
        "frame": {"sections": [
            {"id": "ack", "title": "Acknowledgment", "purpose": "Accept the observation and commit to a systemic response", "elements": ["E1", "E2"]},
            {"id": "basis", "title": "Regulatory basis", "purpose": "State the governing 21 CFR clauses, each verified against the corpus", "elements": ["E1", "E2", "E3", "E4", "E5"]},
            {"id": "rca", "title": "Root cause analysis", "purpose": "Evidence from EM data, batch records, training and change history", "elements": ["E1", "E2", "E3", "E4"]},
            {"id": "correction", "title": "Immediate corrections", "purpose": "Contain: hold, reopen, sample harder", "elements": ["E1", "E2", "E3"]},
            {"id": "capa", "title": "Corrective and preventive actions", "purpose": "Fix the system and prove it worked", "elements": ["E1", "E2", "E4", "E5"]},
            {"id": "impact", "title": "Change control and impacted areas", "purpose": "What changes, and what else it touches", "elements": ["E1", "E3", "E5"]},
            {"id": "timeline", "title": "Timeline and commitments", "purpose": "Dated commitments and progress reports to FDA", "elements": ["E2", "E3"]}]},
        "change_control": {"items": [
            {"id": "CC-NEW-01", "title": "Retrospective assessment and requalification of the Line 2 stopper bowl (reopens CC-26-031)", "type": "Equipment / process", "class": "Major",
             "targets": ["CC-26-031", "PRT-VAL-EQ-STOPPER-2024"], "why": "The 2026 modification closed without airflow visualisation or media fill; excursions began {cc_gap_days} days later.",
             "validation": "Repeat airflow visualisation and three media fills before routine filling resumes", "filing": "Regulatory Affairs to assess whether a filing update is needed (to be confirmed)",
             "owner": "Head of Aseptic Operations", "due": "Day 30", "elements": ["E1"]},
            {"id": "CC-NEW-02", "title": "Revise SOP-EM-014 and SOP-QA-022: repeat-location trigger; no closure without root cause and batch assessment", "type": "Procedure", "class": "Major",
             "targets": ["SOP-EM-014", "SOP-QA-022"], "why": "Procedures allowed repeated excursions to close individually without trending or batch assessment.",
             "validation": "None for the procedure itself; training on the revised SOPs before effective date", "filing": "No filing impact expected (to be confirmed)",
             "owner": "Head of Quality", "due": "Day 45", "elements": ["E2", "E3", "E4"]},
            {"id": "CC-NEW-03", "title": "eQMS deviation workflow gate for Grade A excursions", "type": "Computerised system", "class": "Major",
             "targets": ["SOP-QA-022"], "why": "The eQMS permitted closure with root cause 'Not determined' and no batch-impact assessment.",
             "validation": "Computer system validation: URS update, OQ of the gate, Part 11 review", "filing": "No filing impact expected (to be confirmed)",
             "owner": "Head of Quality Systems", "due": "Day 45", "elements": ["E2", "E5"]},
            {"id": "CC-NEW-04", "title": "Batch record and QA review checklist: reference EM excursions and deviations", "type": "Document", "class": "Minor",
             "targets": ["MBR-FL2-VIAL-10ML", "SOP-QA-030"], "why": "QA review approved {n_bmr_unlinked} batch records without referencing the excursion.",
             "validation": "Master BMR revision approved by QA", "filing": "None expected", "owner": "Head of Production", "due": "Day 30", "elements": ["E3", "E5"]},
            {"id": "CC-NEW-05", "title": "Training system block for overdue aseptic requalification", "type": "Training system", "class": "Minor",
             "targets": ["SOP-TR-009", "SOP-GW-002"], "why": "{n_lapsed_ops} operators with overdue requalification worked on {n_lapsed_batches} excursion batches.",
             "validation": "LMS rule change verified in test before release", "filing": "None expected", "owner": "Head of Aseptic Operations", "due": "Day 15", "elements": ["E1"]}]},
        "map": {"items": [{"element": e, "ref": r, "rationale": t} for e, r, t in MAP]},
        "rca": {
            "whys": [
                "Grade A action-limit results recurred at {hot_loc} in {weeks_with_exc} of {n_weeks} weeks.",
                "{human_flora_pct}% of isolates were human-associated flora, so a personnel or intervention source is the leading hypothesis (to be confirmed).",
                "Each event was closed individually as 'no product impact' with root cause 'Not determined', so the pattern was never connected across deviations.",
                "Deviation closure did not enforce SOP-EM-014 section 7.2 or SOP-QA-022 section 5.4 (root cause and batch assessment); no QA gate prevented closure.",
                "The quarterly trend review that would have exposed the pattern (SOP-EM-014 section 9.1) was not performed for {missing_trend_periods}."],
            "categories": {
                "People": ["Aseptic interventions at the stopper bowl to be reviewed", "Operator gowning and behaviour to be assessed"],
                "Process": ["Deviation closure without root cause", "Trend review not performed"],
                "Equipment": ["Stopper-bowl design and access to be assessed"],
                "Environment": ["Grade A airflow at {hot_loc} to be re-verified"],
                "Materials": ["Stopper handling and sterilisation records to be reviewed"],
                "Systems": ["eQMS permits closure without RCA or batch assessment"]},
            "root_causes": [
                {"id": "RC1", "text": "Deviation and trending controls allowed recurring Grade A excursions to be closed individually without root cause or batch assessment.",
                 "evidence": ["EV-SOP-EM-014", "EV-SOP-QA-022", "EV-TR-2026-Q1", "EV-TR-2026-Q2"]},
                {"id": "RC2", "text": "Probable personnel or intervention source at the stopper bowl - to be confirmed by the reopened investigations.", "evidence": ["EV-EM-DATA"]}]},
        "capa": {
            "correction": [
                {"text": "Place Line 2 batches filled since {period_start} on quality hold", "owner": "Head of Quality", "due": "Day 2"},
                {"text": "Reopen the {n_closed_no_rc} deviations closed without root cause", "owner": "Head of Quality", "due": "Day 5"},
                {"text": "Increase Grade A sampling at {hot_loc}", "owner": "Head of Microbiology", "due": "Day 5"}],
            "corrective": [
                {"text": "Risk assessment of stopper-bowl interventions", "owner": "Head of Aseptic Operations", "due": "Day 30"},
                {"text": "Retrain and re-qualify aseptic operators", "owner": "Head of Aseptic Operations", "due": "Day 30"}],
            "preventive": [
                {"text": "eQMS gate: no closure of Grade A excursions without RCA and batch assessment", "owner": "Head of Quality Systems", "due": "Day 45"},
                {"text": "Monthly EM trending with repeat-location trigger; issue missing reports", "owner": "Head of Microbiology", "due": "Day 15"}],
            "effectiveness": [
                {"text": "No Grade A recurrence at {hot_loc} for 90 days; 100% of excursion deviations closed with RCA", "owner": "Head of Quality", "due": "Day 120"}]},
        "draft": DRAFT,
        "redteam": REDTEAM,
        "revise": REVISE,
    },
}

if __name__ == "__main__":
    out = os.path.join(HERE, "demo_em_483.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(CASE, f, indent=1, ensure_ascii=False)
    print("wrote", out)
