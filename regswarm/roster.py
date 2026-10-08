"""The 300-agent roster for RegSwarm.

300 specialists are available. A query activates only the handful that matches
its wording and the linked records. `IMPLEMENTED` marks the specialists backed
by the local workflow. The others stay visible so the reviewer can see the
coverage, and the run does not pretend they each made a separate model call.
"""

CLUSTERS = [
    # (key, label, tier, colour-index)
    ("T1", "Orchestration", 1),
    ("A", "US FDA", 2),
    ("B", "EU / EMA", 2),
    ("C", "Global harmonisation", 2),
    ("D", "Cell & gene therapy", 2),
    ("E", "Vaccines", 2),
    ("F", "Quality systems", 2),
    ("G", "Facilities & validation", 2),
    ("H", "Production", 2),
    ("T3", "Response & drafting", 3),
    ("T4", "Verification & governance", 4),
    ("I", "Query angles", 2),
    ("J", "Linked documents", 2),
    ("K", "Response route", 3),
    ("L", "Guideline references", 2),
]

_AGENTS = {
    "T1": [
        "Master Orchestrator", "Query Classifier", "Task Decomposer",
        "Consensus Judge", "Human Escalation Manager",
    ],
    "A": [
        "21 CFR 210/211 (finished pharmaceuticals)", "21 CFR 600-680 (biologics general)",
        "21 CFR 610 (release testing)", "21 CFR 1271 (HCT/Ps, GTP)",
        "21 CFR Part 11 (electronic records)", "CBER/OTP CGT guidance specialist",
        "483 & Warning Letter precedent analyst", "BLA / IND / NDA submission specialist",
        "PHS Act 351 specialist", "FDA inspection trends monitor",
        "Combination products (21 CFR Part 4)", "FDA formal correspondence drafter",
    ],
    "B": [
        "EudraLex Vol. 4 Part I", "EudraLex Vol. 4 Part II (APIs)",
        "Annex 1 (sterile manufacture, CCS)", "Annex 2 (biologicals)",
        "Annex 15 (qualification & validation)", "Annex 16 (QP certification)",
        "Part IV (ATMP GMP)", "Regulation 1394/2007 (ATMPs)",
        "EMA scientific guidelines", "QP declaration & supply chain",
        "CAT / scientific advice", "National authorities (MHRA, PEI, ANSM)",
    ],
    "C": [
        "WHO TRS", "ICH Q5A / Q5C / Q6B", "ICH Q7 / Q8 / Q9 / Q10",
        "ICH Q2(R2) / Q14", "PIC/S PE 009", "India CDSCO / Schedule M / NDCT",
        "TGA / Health Canada / PMDA / ANVISA", "USP chapters",
        "Ph. Eur. general chapters", "ISO 14644 / cleanroom standards",
    ],
    "D": [
        "CAR-T process CMC", "Viral vector manufacture", "Potency assay strategy",
        "Chain of identity / custody", "Donor screening & eligibility",
        "Autologous vs allogeneic logistics", "Cryopreservation & cold chain",
        "Closed-system / automated processing", "Comparability after process change",
        "Gene-editing considerations", "Starting material qualification",
        "CGT release & adventitious agents",
    ],
    "E": [
        "Seed lot & cell banks", "Upstream (1L to 2000L scale-up)",
        "Downstream purification", "Fill-finish & lyophilisation",
        "Adventitious agent testing", "Stability & shelf life",
        "Live attenuated / inactivated", "mRNA / LNP platforms",
        "Conjugate & subunit", "Vaccine release & lot protocol",
    ],
    "F": [
        "Deviation management", "CAPA effectiveness", "Change control (PACMP)",
        "OOS / OOT investigation", "Data integrity (ALCOA+)", "Annual product review",
        "Supplier & CMO oversight", "Contamination Control Strategy",
        "Personnel qualification & training", "Document & record management",
        "Quality risk management (ICH Q9)", "Complaints, recalls & field alerts",
    ],
    "G": [
        "Cleanroom classification & HVAC", "Environmental monitoring & trending",
        "Equipment DQ/IQ/OQ/PQ", "Process validation & PPQ",
        "Cleaning validation", "Computer system validation",
        "Utilities (WFI, PW, clean steam)", "Sterilisation & depyrogenation",
        "Single-use & extractables/leachables", "Aseptic process simulation",
    ],
    "H": [
        "Batch record review", "Upstream deviations", "Downstream deviations",
        "Yield & process performance", "Tech transfer between sites",
        "Material genealogy", "Raw material qualification", "GMP production scheduling",
    ],
    "T3": [
        "Root Cause Analysis Writer", "CAPA Plan Drafter",
        "483 / Deficiency Response Drafter", "Executive Summary Writer",
        "Citation & Evidence Linker",
    ],
    "T4": [
        "Citation Verifier", "Contradiction Detector", "Red-Team Agent",
        "Confidence Scorer & Final Judge",
    ],
    "I": [
        "Line clearance", "Label control", "Retained components", "Fill weight", "Stopper lot",
        "Environmental monitoring", "Action-limit excursion", "Residue limit", "Dirty-hold time",
        "Cleaning of product-contact parts", "Batch-record completeness", "Reviewer signature",
        "Yield reconciliation", "Material dispensing", "In-process weight", "Out-of-specification result",
        "Laboratory investigation", "Retest decision", "Reference standard", "Sample preparation",
        "Method suitability", "Impurity threshold", "Master formula", "Bill of materials",
        "Process parameters", "Cleaning validation", "Worst-case product", "Swab locations",
        "Qualification status", "Equipment log", "Aseptic behaviour", "Gowning",
        "Media fill", "Interventions", "Hold time", "Quarantine decision", "Product impact",
        "Complaint trend", "Recall assessment", "Data integrity", "Audit trail", "Access control",
        "Training effectiveness", "Supplier deviation", "Incoming inspection", "Status labelling",
        "Returned goods", "Distribution record",
    ],
    "J": [
        "Impacted SOP", "Impacted STP", "Impacted BMR", "Impacted protocol", "Impacted MFR",
        "Impacted deviation file", "Impacted OOS file", "Impacted qualification", "Cleaning log",
        "Line-clearance checklist", "Batch-record review form", "Environmental monitoring form",
        "Assay worksheet", "Specification", "Sampling plan", "Stability protocol",
        "Validation report", "Change-control record", "CAPA record", "Training curriculum",
        "Equipment use log", "Room release log", "Label reconciliation", "Component disposition",
        "Yield sheet", "In-process control sheet", "Laboratory notebook", "Reference-standard log",
        "Instrument calibration", "Method verification", "Retain-sample record", "Complaint file",
        "Returned-product record", "Distribution list", "Supplier file", "Incoming-goods record",
        "Warehouse status", "Dispensing ticket", "Weighing record", "Master batch record",
        "Packaging order", "Reconciliation sheet", "Deviation extension", "Investigation report",
        "Effectiveness check", "Annual product review", "Management review", "Risk assessment",
    ],
    "K": [
        "Open a deviation", "Product-impact assessment", "Quarantine the lot", "Hold the line",
        "Repeat line clearance", "OOS laboratory investigation", "Phase-one laboratory check",
        "Manufacturing investigation", "Five-why root cause", "Fishbone categories",
        "Confirmed cause versus hypothesis", "Immediate correction", "Corrective action",
        "Preventive action", "Effectiveness check", "CAPA owner and due point",
        "Minor change control", "Major change control", "Procedure revision",
        "Batch-record template revision", "Validation impact", "Regulatory-filing assessment",
        "Batch rejection decision", "Rework decision", "Retest rule", "Specification review",
        "Training action", "Supervision action", "Second-person check", "Label-room control",
        "Component segregation", "Cleaning-limit update", "Monitoring-plan update",
        "Alarm response", "Excursion investigation", "Trend review", "Supplier CAPA",
        "Field-alert assessment", "Recall decision", "Customer notification",
        "Management escalation", "Quality-unit approval", "Response letter",
        "Commitment register", "Due-date tracking", "Evidence of completion",
        "Batch disposition", "Response approval",
    ],
    "L": [
        "21 CFR 211.22 quality unit", "21 CFR 211.68 equipment", "21 CFR 211.100 procedures",
        "21 CFR 211.113 contamination", "21 CFR 211.122 labeling", "21 CFR 211.130 packaging",
        "21 CFR 211.160 laboratory controls", "21 CFR 211.165 testing", "21 CFR 211.180 records",
        "21 CFR 211.186 master record", "21 CFR 211.188 batch record", "21 CFR 211.192 record review",
        "21 CFR 211.198 complaints", "21 CFR Part 11 records", "21 CFR 210 definitions",
        "FDA CGMP regulations page", "openFDA enforcement reports", "WHO TRS GMP",
        "WHO TRS sterile products", "WHO data integrity", "EMA quality guidelines",
        "EU GMP Annex 1", "EU GMP Annex 11", "EU GMP Annex 15", "EudraLex Volume 4",
        "ICH Q7 API GMP", "ICH Q8 pharmaceutical development", "ICH Q9 quality risk",
        "ICH Q10 pharmaceutical quality system", "ICH Q2 analytical validation", "ICH Q3 impurities",
        "ICH Q12 lifecycle", "PIC/S GMP guide", "PIC/S data integrity", "India Schedule M",
        "CDSCO GMP", "USP general notices", "European Pharmacopoeia", "Indian Pharmacopoeia",
        "ISO 14644 cleanrooms", "FDA process validation guidance", "FDA OOS guidance",
        "FDA data-integrity guidance", "FDA label guidance", "EDQM certification",
        "ICH Q1 stability", "ICH Q11 development", "21 CFR 211.42 facilities",
    ],
}

ROSTER = []
for key, label, tier in CLUSTERS:
    for i, name in enumerate(_AGENTS[key], 1):
        ROSTER.append({"id": f"{key}{i:02d}", "cluster": key, "cluster_label": label,
                       "tier": tier, "name": name})

assert len(ROSTER) == 292, len(ROSTER)
BY_ID = {a["id"]: a for a in ROSTER}

# Agents this MVP actually runs (backed by real code / corpus / prompts).
IMPLEMENTED = {
    "T101", "T102", "T103", "T105",     # orchestrator, classifier, decomposer, escalation
    "A01",                               # 21 CFR 210/211 retrieval specialist
    "A02",                               # 21 CFR 600-680 (evaluated; activated only for biologics)
    "F01", "F02", "F04", "F05",         # deviation, CAPA, OOS investigation, data integrity
    "F03", "F09", "F10", "F11",          # change control, training records, document & record management, QRM
    "H01",                               # batch record review (executed BMR analytics)
    "G02", "G05",                        # environmental monitoring, cleaning validation
    "T301", "T302", "T303", "T305",      # RCA, CAPA, response drafter, citation & evidence linker
    "T401", "T403", "T404",              # citation verifier, red team, scorer/judge
    "I01", "I02", "I06", "I08", "I11", "I16", "I25", "I40",
    "J01", "J03", "J05", "J06", "J07", "K01", "K06", "K09", "K13", "L12",
}
for a in ROSTER:
    a["implemented"] = a["id"] in IMPLEMENTED

# Local search specialists backed by the persistent facility category index.
for i, name in enumerate(("SOP search", "STP search", "BMR search", "Protocol search", "MFR search", "Deviation search", "OOS search", "Qualification search"), 1):
    agent = {"id": f"LIB{i:02d}", "cluster": "F", "cluster_label": "Facility search", "tier": 2, "name": name, "implemented": True}
    ROSTER.append(agent)
    BY_ID[agent["id"]] = agent

assert len(ROSTER) == 300, len(ROSTER)
