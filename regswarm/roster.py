"""The 100-agent roster from the RegSwarm blueprint.

100 agents are *available*; a query activates only the relevant handful.
`IMPLEMENTED` marks which of them this MVP actually runs. Agents outside that set
are shown in the UI as roadmap (they are not simulated) so the demo never claims
capabilities the build does not have.
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
}

ROSTER = []
for key, label, tier in CLUSTERS:
    for i, name in enumerate(_AGENTS[key], 1):
        ROSTER.append({"id": f"{key}{i:02d}", "cluster": key, "cluster_label": label,
                       "tier": tier, "name": name})

assert len(ROSTER) == 100, len(ROSTER)
BY_ID = {a["id"]: a for a in ROSTER}

# Agents this MVP actually runs (backed by real code / corpus / prompts).
IMPLEMENTED = {
    "T101", "T102", "T103", "T105",     # orchestrator, classifier, decomposer, escalation
    "A01",                               # 21 CFR 210/211 retrieval specialist
    "A02",                               # 21 CFR 600-680 (evaluated; activated only for biologics)
    "F01", "F02",                        # deviation management, CAPA effectiveness
    "F03", "F09", "F10", "F11",          # change control, training records, document & record management, QRM
    "H01",                               # batch record review (executed BMR analytics)
    "G02",                               # environmental monitoring & trending (real analytics)
    "T301", "T302", "T303", "T305",      # RCA, CAPA, response drafter, citation & evidence linker
    "T401", "T403", "T404",              # citation verifier, red team, scorer/judge
}
for a in ROSTER:
    a["implemented"] = a["id"] in IMPLEMENTED

# Local search specialists backed by the persistent facility category index.
for i, name in enumerate(("SOP search", "STP search", "Protocol search", "BMR search", "Deviation search", "CAPA search", "Change control search", "Risk assessment search"), 1):
    agent = {"id": f"LIB{i:02d}", "cluster": "F", "cluster_label": "Facility search", "tier": 2, "name": name, "implemented": True}
    ROSTER.append(agent)
    BY_ID[agent["id"]] = agent
