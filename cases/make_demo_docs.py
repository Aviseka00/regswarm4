"""Generate the SYNTHETIC QMS document library for the demo site (demo_site/docs.json).

It stands in for what production connectors would pull from the site's real systems:
document management (SOPs, STPs, protocols, master BMRs, site master file, policies),
the MES batch-record archive (executed BMRs), the eQMS (deviations, CAPA, change control,
audits), LIMS (EM data, trend reports), the LMS (training) and CMMS / validation records.

Everything here is invented. Deterministic: same output every run. Run after make_demo_site.py.
"""
import csv, datetime, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "demo_site")
site = json.load(open(os.path.join(SITE, "site.json"), encoding="utf-8"))
rows = list(csv.DictReader(open(os.path.join(SITE, "em_data.csv"), encoding="utf-8")))
START = datetime.date(2026, 4, 6)

SYSTEMS = [
    {"id": "DMS", "name": "Document Management", "short": "DMS", "kind": "SOPs, STPs, protocols, master BMRs, SMF, policies", "protocol": "REST / SFTP export"},
    {"id": "MES", "name": "MES batch-record archive", "short": "MES", "kind": "Executed batch records", "protocol": "REST + PDF archive"},
    {"id": "EQMS", "name": "eQMS", "short": "eQMS", "kind": "Deviations, CAPA, change control, audits", "protocol": "REST API"},
    {"id": "LIMS", "name": "LIMS", "short": "LIMS", "kind": "EM results, trend reports, media records", "protocol": "DB view (read-only)"},
    {"id": "LMS", "name": "Training / LMS", "short": "LMS", "kind": "Training matrix and operator qualification", "protocol": "REST API"},
    {"id": "CMMS", "name": "Validation & Engineering (CMMS)", "short": "CMMS", "kind": "Equipment, HVAC and calibration records", "protocol": "REST API"},
]
GROUP_LABEL = {"SOP": "SOPs", "STP": "STPs", "Protocol": "Protocols & reports", "Master BMR": "Master BMRs",
               "Executed BMR": "Executed BMRs", "SMF": "SMF & policies", "Deviation": "Deviations", "CAPA": "CAPAs",
               "Change control": "Change controls", "Audit": "Audits & complaints", "LIMS data": "EM & LIMS data",
               "Training": "Training records", "Equipment": "Equipment & HVAC"}

DOCS = []


def doc(id_, group, system, title, version="1.0", status="Effective", date="2025-01-01", owner="Quality Assurance",
        area="Site", sections=None, refs=None, meta=None, type_=None):
    DOCS.append({"id": id_, "group": group, "type": type_ or group, "system": system, "title": title, "version": version,
                 "status": status, "date": date, "owner": owner, "area": area,
                 "sections": [{"ref": r, "text": t} for r, t in (sections or [])], "refs": refs or [], "meta": meta or {}})


# ------------------------------------------------------------------ DMS: SOPs
FS2 = "Filling Suite 2"
doc("SOP-EM-014", "SOP", "DMS", "Environmental Monitoring Program - Aseptic Areas", "6.0", "Effective", "2025-03-01", "Head of Microbiology", FS2,
    [("5.3", "Grade A viable monitoring by settle plate (4 hours) and active air is performed at every critical location during each filling operation. Results are recorded in LIMS against the batch."),
     ("7.2", "Any Grade A action-limit result shall be investigated to root cause within 10 working days, including review of aseptic interventions, personnel monitoring, equipment and cleaning records, and an assessment of every batch filled in the affected period."),
     ("7.4", "Repeated action-limit results at one location within a four week period shall trigger a formal investigation and a QA review of the location, whether or not each individual result was investigated."),
     ("9.1", "EM data shall be trended monthly by Microbiology and reviewed by QA; a quarterly trend report shall be approved by the Head of Quality."),
     ("9.2", "Monthly environmental monitoring summary reports shall be issued by the 15th day of the following month.")],
    ["SOP-QA-022", "STP-MB-031", "STP-MB-040", "SOP-AS-003"])
doc("SOP-QA-022", "SOP", "DMS", "Deviation Management", "9.0", "Effective", "2025-06-15", "Head of Quality", "Site",
    [("5.4", "Closure of a deviation as 'no product impact' requires documented justification and a QA batch-impact assessment."),
     ("6.1", "Root cause shall be determined using a structured method. A deviation shall not be closed with root cause 'Not determined' without Head of Quality approval and a documented risk assessment.")],
    ["SOP-QA-030", "SOP-QA-027"])
doc("SOP-AS-003", "SOP", "DMS", "Aseptic Behaviour and Interventions", "4.0", "Effective", "2024-11-01", "Head of Aseptic Operations", FS2,
    [("6.1", "Interventions in the Grade A zone shall be recorded, and repeated interventions at one location shall be evaluated."),
     ("6.3", "Stopper bowl clearance is a critical intervention. Operators must use approved sterile tools and record each stopper bowl intervention with initials and time in the batch record.")],
    ["SOP-GW-002", "SOP-EM-014"])
doc("SOP-GW-002", "SOP", "DMS", "Gowning Qualification for Grade A and B Areas", "5.0", "Effective", "2025-02-10", "Head of Aseptic Operations", FS2,
    [("4.1", "Operators shall be qualified for gowning before entering Grade A or B areas and requalified every 12 months by gowning observation and finger dab monitoring."),
     ("4.4", "An operator whose requalification is overdue shall not perform Grade A interventions until requalified.")], ["SOP-TR-009"])
doc("SOP-QA-030", "SOP", "DMS", "Batch Record Review and Release", "7.0", "Effective", "2025-04-20", "Head of Quality", "Site",
    [("5.2", "QA reviews the executed batch record, related deviations and environmental monitoring results before batch release. Any EM excursion during the filling period shall be referenced in the batch record."),
     ("5.5", "A batch shall not be released while an associated deviation is open or closed without a determined root cause.")], ["SOP-QA-022"])
doc("SOP-QA-018", "SOP", "DMS", "Change Control", "8.0", "Effective", "2025-05-05", "Head of Quality Systems", "Site",
    [("4.2", "Every change to equipment, process, procedure or computerised system is assessed for impact on validated state, sterility assurance and regulatory filings before implementation."),
     ("4.6", "Changes to critical aseptic equipment require documented consideration of airflow visualisation, media fill (aseptic process simulation) and requalification.")], ["SOP-QA-022"])
doc("SOP-TR-009", "SOP", "DMS", "Training and Qualification of Aseptic Personnel", "6.0", "Effective", "2025-01-20", "Head of Aseptic Operations", "Site",
    [("3.2", "Aseptic operators complete initial aseptic technique qualification and annual requalification including a media fill participation.")], ["SOP-GW-002"])
doc("SOP-QA-027", "SOP", "DMS", "CAPA Management", "6.0", "Effective", "2025-03-30", "Head of Quality Systems", "Site",
    [("5.1", "Each CAPA has a defined effectiveness check with an owner and a due date. A CAPA is closed only after the effectiveness check is documented.")], ["SOP-QA-022"])
for i, (id_, t, txt) in enumerate([
    ("SOP-WH-011", "Warehouse Temperature Mapping", "Temperature mapping of the finished goods warehouse is performed annually and after layout change. Data loggers are placed at defined positions."),
    ("SOP-QC-045", "HPLC System Calibration", "Calibration of liquid chromatography systems including detector linearity, flow accuracy and injector precision."),
    ("SOP-EN-020", "Compressed Air and Gas Testing", "Compressed air and process gases are sampled for particulates, oil and microbial content quarterly at each point of use."),
    ("SOP-PU-006", "Purified Water Sampling", "Purified water loop sampling for conductivity, TOC and bioburden at defined use points."),
    ("SOP-LB-003", "Labelling Operations", "Line clearance, label reconciliation and label storage for packaging operations."),
    ("SOP-IT-012", "Backup and Restore of GxP Systems", "Backup schedule, verification and restore testing for validated computerised systems.")]):
    doc(id_, "SOP", "DMS", t, "3.0", "Effective", "2024-0%d-15" % (i + 2), "Operations", "Site", [("1", txt)])

# STPs
doc("STP-MB-031", "STP", "DMS", "Settle Plate Environmental Monitoring", "4.0", "Effective", "2025-03-01", "Head of Microbiology", FS2,
    [("6", "Expose settle plates at Grade A locations for up to four hours, incubate and count colony forming units. A result at or above the action limit is reported immediately to QA and a deviation is raised.")], ["SOP-EM-014"])
doc("STP-MB-033", "STP", "DMS", "Contact Plate and Glove Print Monitoring", "3.0", "Effective", "2025-03-01", "Head of Microbiology", FS2,
    [("6", "Personnel monitoring by glove print and gown contact plate at the end of each aseptic operation; results are trended per operator.")], ["SOP-EM-014"])
doc("STP-MB-040", "STP", "DMS", "Microbial Identification of Environmental Isolates", "5.0", "Effective", "2025-03-01", "Head of Microbiology", "QC Microbiology",
    [("5", "Isolates from Grade A and B locations are identified to species level. Human associated flora such as Staphylococcus and Micrococcus indicate a possible personnel or intervention source.")], ["SOP-EM-014"])
doc("STP-MB-022", "STP", "DMS", "Growth Promotion Testing of Culture Media", "3.0", "Effective", "2024-09-01", "Head of Microbiology", "QC Microbiology",
    [("4", "Each lot of settle plates is growth promotion tested before use.")])
doc("STP-QC-101", "STP", "DMS", "Bacterial Endotoxins Test", "6.0", "Effective", "2024-06-01", "Head of QC", "QC Laboratory", [("3", "Gel clot and kinetic chromogenic bacterial endotoxin testing of finished product.")])
doc("STP-QC-115", "STP", "DMS", "Sterility Testing by Membrane Filtration", "7.0", "Effective", "2024-06-01", "Head of QC", "QC Laboratory", [("4", "Sterility test of finished product by membrane filtration in an isolator, 14 day incubation.")])
doc("STP-QC-140", "STP", "DMS", "Sub-visible Particulate Matter", "4.0", "Effective", "2024-06-01", "Head of QC", "QC Laboratory", [("3", "Light obscuration test for sub-visible particles in injections.")])

# Protocols and reports
doc("PRT-VAL-APS-2026-01", "Protocol", "DMS", "Aseptic Process Simulation Protocol, Line 2", "1.0", "Approved", "2026-01-05", "Head of Validation", FS2,
    [("3", "Three consecutive media fills simulate the worst-case aseptic filling process including planned and corrective interventions at the stopper bowl and filling needles.")], ["SOP-AS-003"])
doc("APS-2026-01", "Protocol", "DMS", "Aseptic Process Simulation Report, Line 2 (January 2026)", "1.0", "Approved", "2026-01-30", "Head of Validation", FS2,
    [("Result", "3 runs, 0 contaminated units. Line 2 media fill; next due 2026-07."),
     ("Scope", "Interventions simulated used the stopper bowl configuration in place in January 2026. The report does not cover later equipment or process changes.")], ["PRT-VAL-APS-2026-01"], {"date": "2026-01-14"}, type_="Report")
doc("PRT-VAL-HVAC-2025-07", "Protocol", "DMS", "HVAC and Airflow Visualisation Protocol, Filling Suite 2", "1.0", "Approved", "2025-06-30", "Head of Validation", FS2,
    [("4", "Airflow visualisation (smoke study) under dynamic conditions over the stopper bowl, needles and conveyor infeed; HEPA integrity and recovery testing.")])
doc("RPT-VAL-HVAC-2025-07", "Protocol", "DMS", "HVAC and Airflow Visualisation Report, Filling Suite 2", "1.0", "Approved", "2025-08-05", "Head of Validation", FS2,
    [("Result", "Unidirectional airflow demonstrated over Grade A critical zones on 2025-07-22 in the configuration at that date. Air handling unit AHU-07 supplies Filling Line 1 and Filling Line 2.")],
    ["PRT-VAL-HVAC-2025-07"], {"smoke_study_date": "2025-07-22", "serves": ["FL1", "FL2"]}, type_="Report")
doc("PRT-VAL-EQ-STOPPER-2024", "Protocol", "DMS", "Stopper Bowl and Feeder IQ/OQ Protocol, Line 2", "1.0", "Approved", "2024-03-10", "Head of Validation", FS2,
    [("5", "Installation and operational qualification of the vibratory stopper bowl, feeder rate range, cover and sterilisation of stopper contact parts.")])
doc("RPT-VAL-EQ-STOPPER-2024", "Protocol", "DMS", "Stopper Bowl and Feeder IQ/OQ Report, Line 2", "1.0", "Approved", "2024-05-02", "Head of Validation", FS2,
    [("Result", "Qualified at the validated feeder rate range. Operation outside the qualified range requires change control and requalification.")], ["PRT-VAL-EQ-STOPPER-2024"], type_="Report")
doc("PRT-VAL-GOWN-2025", "Protocol", "DMS", "Gowning Qualification Protocol", "1.0", "Approved", "2025-01-25", "Head of Aseptic Operations", FS2, [("4", "Operator gowning observation and finger dab acceptance criteria for Grade A and B entry.")], ["SOP-GW-002"])
doc("PRT-CLN-014", "Protocol", "DMS", "Cleaning and Disinfection Efficacy Protocol", "2.0", "Approved", "2024-10-10", "Head of Microbiology", FS2, [("3", "Disinfectant efficacy on cleanroom surfaces including stainless steel and epoxy.")])
doc("PRT-EM-OP-2024", "Protocol", "DMS", "Environmental Monitoring Performance Qualification", "1.0", "Approved", "2024-04-12", "Head of Microbiology", FS2, [("3", "Sampling locations, alert and action limits and monitoring frequency for the filling suite, justified by risk assessment.")], ["SOP-EM-014"])
doc("PRT-VAL-LYO-2023", "Protocol", "DMS", "Lyophiliser Performance Qualification", "1.0", "Approved", "2023-11-05", "Head of Validation", "Lyophilisation", [("3", "Shelf temperature mapping and sublimation rate study.")])
doc("PRT-VAL-WFI-2024", "Protocol", "DMS", "Water for Injection Loop Qualification", "1.0", "Approved", "2024-08-20", "Head of Validation", "Utilities", [("3", "WFI loop flow, temperature and microbial performance qualification.")])

# Master BMR, SMF, policies
doc("MBR-FL2-VIAL-10ML", "Master BMR", "DMS", "Master Batch Record, Product A 10 mL vial, Filling Line 2", "11.0", "Effective", "2025-09-01", "Head of Production", FS2,
    [("Interventions", "Record every Grade A intervention including stopper bowl clearance with time and initials. Attach the environmental monitoring summary for the filling period."),
     ("QA review", "QA review checklist: deviations referenced, environmental monitoring excursions referenced, operators qualified.")], ["SOP-AS-003", "SOP-EM-014", "SOP-QA-030"])
doc("MBR-FL1-VIAL-5ML", "Master BMR", "DMS", "Master Batch Record, Product B 5 mL vial, Filling Line 1", "8.0", "Effective", "2025-05-01", "Head of Production", "Filling Suite 1", [("Interventions", "Record Grade A interventions on Filling Line 1.")], ["SOP-AS-003"])
doc("MBR-INSP-VIAL", "Master BMR", "DMS", "Master Batch Record, Visual Inspection", "5.0", "Effective", "2025-02-01", "Head of Production", "Inspection", [("1", "Manual and automated visual inspection of filled vials.")])
doc("SMF-001", "SMF", "DMS", "Site Master File", "12.0", "Effective", "2026-02-01", "Site Head", "Site",
    [("Sterile manufacturing", "Filling Suite 2 contains Filling Line 2 for Product A. Grade A filling zone within Grade B background. Filling Line 1 and Line 2 are served by a shared air handling unit AHU-07."),
     ("Quality unit", "The quality unit is responsible for approval of procedures, review of investigations and batch release. Head of Quality reports to the Site Head.")], ["SOP-QA-030"], type_="Site Master File")
doc("QP-001", "SMF", "DMS", "Quality Policy", "5.0", "Effective", "2025-01-01", "Site Head", "Site", [("1", "Quality is the responsibility of every employee. Investigations are completed to root cause and drive lasting corrective action.")], type_="Quality policy")
doc("QP-003", "SMF", "DMS", "Contamination Control Strategy", "3.0", "Effective", "2025-08-01", "Head of Quality", FS2,
    [("Personnel", "Personnel are the primary source of contamination in aseptic processing; interventions are minimised and monitored."),
     ("Monitoring", "Environmental monitoring trends are reviewed monthly and after any excursion; the strategy is reviewed after changes to critical equipment.")], ["SOP-EM-014", "SOP-AS-003"], type_="Quality policy")
doc("QP-004", "SMF", "DMS", "Aseptic Operations Policy", "2.0", "Effective", "2024-12-01", "Head of Aseptic Operations", FS2, [("1", "Aseptic operations are performed only by qualified personnel using approved procedures.")], ["SOP-AS-003"], type_="Quality policy")
doc("QP-007", "SMF", "DMS", "Data Integrity Policy", "2.0", "Effective", "2025-01-01", "Head of Quality Systems", "Site", [("1", "Records are attributable, legible, contemporaneous, original and accurate.")], type_="Quality policy")

# ------------------------------------------------------------------ MES: executed BMRs (Line 2 + Line 1)
OPS = {1: [101, 102, 103], 2: [104, 102, 105], 3: [104, 101, 106], 4: [101, 103, 108], 5: [107, 102, 105], 6: [104, 107, 103],
       7: [107, 101, 105], 8: [102, 106, 108], 9: [104, 103, 106], 10: [107, 104, 102], 11: [101, 105, 108], 12: [104, 107, 106]}
INTERV = {1: 2, 2: 7, 3: 6, 4: 2, 5: 3, 6: 8, 7: 6, 8: 2, 9: 9, 10: 10, 11: 2, 12: 7}
exc_batches = {r["batch"] for r in rows if r["grade"] == "A" and int(r["cfu"]) >= int(r["action_limit"])}
for wk in range(1, 13):
    b = f"FL2-B26-{100 + wk}"
    fill = START + datetime.timedelta(days=7 * (wk - 1) + 2)
    qa = fill + datetime.timedelta(days=8)
    disp = "Released - warehouse" if wk == 12 else "Distributed"
    ops = [f"OP-{n}" for n in OPS[wk]]
    exc = b in exc_batches
    doc(f"EBR-{b}", "Executed BMR", "MES", f"Executed batch record {b}", "1.0", "Executed", fill.isoformat(), "Production", FS2,
        [("Batch summary", f"Executed batch record for batch {b}, Filling Line 2, Filling Suite 2. Product A sterile injection 10 mL vial. Filled {fill.isoformat()}. Operators {', '.join(ops)}."),
         ("Interventions", f"Grade A interventions recorded in the aseptic filling zone: {INTERV[wk]} (stopper bowl clearance and needle changes logged with operator initials)."),
         ("QA review", f"Batch record reviewed and approved by QA on {qa.isoformat()}. Environmental monitoring reviewed: no excursions referenced. Deviations referenced: none."),
         ("Disposition", f"Disposition: {disp}.")],
        ["MBR-FL2-VIAL-10ML", "SOP-QA-030"],
        {"batch": b, "week": wk, "product": "Product A", "fill_date": fill.isoformat(), "operators": ops, "interventions": INTERV[wk],
         "em_excursion_referenced": False, "qa_review_date": qa.isoformat(), "disposition": disp, "line": "FL2", "excursion_batch": exc})
for n in range(1, 4):
    b = f"FL1-B26-{200 + n}"
    fill = datetime.date(2026, 4, 6) + datetime.timedelta(days=21 * (n - 1) + 3)
    doc(f"EBR-{b}", "Executed BMR", "MES", f"Executed batch record {b}", "1.0", "Executed", fill.isoformat(), "Production", "Filling Suite 1",
        [("Batch summary", f"Executed batch record for batch {b}, Filling Line 1, Filling Suite 1. Product B sterile injection 5 mL vial. Filled {fill.isoformat()}."),
         ("Disposition", "Disposition: Distributed.")], ["MBR-FL1-VIAL-5ML"],
        {"batch": b, "product": "Product B", "fill_date": fill.isoformat(), "line": "FL1", "disposition": "Distributed", "excursion_batch": False})

# ------------------------------------------------------------------ eQMS: deviations
loc_desc = {r["location"]: r["location_desc"] for r in rows}
by_sample = {r["sample_id"]: r for r in rows}
for d in site["deviations"]:
    r = by_sample[d["sample_id"]]
    doc(d["id"], "Deviation", "EQMS", f"Grade A EM excursion {r['location']} ({r['sample_id']})", "1.0", d["status"], d["opened"], "Microbiology", FS2,
        [("Description", f"Grade A viable result {r['cfu']} CFU at {loc_desc[r['location']]} on {r['date']}, batch {d['batch']}, organism {r['organism']}. Action limit exceeded."),
         ("Closure", (d["closure_statement"] or "Investigation in progress.") + f" Root cause: {d['root_cause']}. Batch impact assessment: not performed. Other batches reviewed: no.")],
        ["SOP-QA-022", "SOP-EM-014"], {"root_cause": d["root_cause"], "batch": d["batch"], "sample": d["sample_id"]})
for i, (id_, t, txt) in enumerate([
    ("DEV-26-0301", "Label misprint on Line 3 packaging", "Batch code misprinted on 40 cartons; reprinted under line clearance. Root cause: printer template error."),
    ("DEV-26-0309", "Warehouse temperature excursion", "Warehouse zone C exceeded 25 C for 3 hours during HVAC fault. Product assessed, no impact."),
    ("DEV-26-0322", "HPLC baseline drift", "Baseline drift in chromatography system; column replaced."),
    ("DEV-26-0333", "Conveyor jam on Line 1 packaging", "Conveyor jam cleared; operator retrained."),
    ("DEV-26-0345", "Water conductivity alert", "Purified water conductivity alert level at use point 4; sanitised."),
    ("DEV-26-0358", "Data backup failure", "Nightly backup failed once; rerun succeeded.")]):
    doc(id_, "Deviation", "EQMS", t, "1.0", "Closed", "2026-0%d-1%d" % (3 + i % 3, i + 1), "Operations", "Site", [("Description", txt)], ["SOP-QA-022"], {"root_cause": "Determined"})

# CAPA
doc("CAPA-25-019", "CAPA", "EQMS", "Grade A excursions at FL2-A1 (stopper bowl), Q3 2025", "1.0", "Closed", "2025-08-12", "Head of Aseptic Operations", FS2,
    [("Actions", "Retrain aseptic operators; replace stopper bowl cover gasket; increase settle plate frequency at FL2-A1 for 8 weeks."),
     ("Effectiveness", "Effectiveness check planned January 2026: no Grade A action limit result at FL2-A1 for 90 days. No effectiveness check record found. CAPA closed 2025-10-30.")],
    ["SOP-QA-027", "SOP-AS-003"], {"closed": "2025-10-30", "location": "FL2-A1", "effectiveness_verified": False})
doc("CAPA-25-031", "CAPA", "EQMS", "Late EM summary reports (internal audit IA-2025-11)", "1.0", "Closed", "2025-11-20", "Head of Microbiology", FS2,
    [("Actions", "Add eQMS reminder for monthly environmental monitoring summary due dates."), ("Effectiveness", "Reminder implemented; effectiveness not assessed.")],
    ["SOP-EM-014", "SOP-QA-027"], {"effectiveness_verified": False})
doc("CAPA-26-007", "CAPA", "EQMS", "Warehouse HVAC alarm response", "1.0", "Open", "2026-03-10", "Facilities", "Warehouse", [("Actions", "Add alarm escalation for warehouse HVAC.")])
doc("CAPA-26-011", "CAPA", "EQMS", "Label printer template control", "1.0", "Open", "2026-03-25", "Operations", "Packaging", [("Actions", "Lock label printer templates.")])

# Change control
doc("CC-26-031", "Change control", "EQMS", "Stopper bowl feed rate and cover modification, Filling Line 2", "1.0", "Closed", "2026-04-03", "Head of Aseptic Operations", FS2,
    [("Change", "Increase vibratory feed rate and replace the stopper bowl cover to reduce stopper jams and the number of interventions."),
     ("Impact assessment", "No impact on sterility assurance. No requalification required. Aseptic process simulation not repeated. Airflow visualisation not repeated.")],
    ["SOP-QA-018", "PRT-VAL-EQ-STOPPER-2024", "SOP-AS-003"],
    {"effective": "2026-04-03", "requalification_required": False, "aps_repeated": False, "smoke_study_repeated": False, "line": "FL2"})
doc("CC-25-102", "Change control", "EQMS", "Revision of SOP-EM-014 to version 6.0", "1.0", "Closed", "2025-02-12", "Head of Microbiology", FS2,
    [("Change", "Revise the environmental monitoring SOP: monthly summaries and quarterly trend reports.")], ["SOP-EM-014"])
for id_, t, txt, dt in [("CC-26-012", "Label template change", "Update label artwork template.", "2026-02-03"),
                        ("CC-26-020", "Backup server replacement", "Replace backup server for GxP systems.", "2026-03-01"),
                        ("CC-26-025", "WFI loop sensor replacement", "Replace conductivity sensors on WFI loop.", "2026-03-18"),
                        ("CC-25-097", "Line 1 conveyor guard modification", "Add guard to Line 1 conveyor.", "2025-10-05")]:
    doc(id_, "Change control", "EQMS", t, "1.0", "Closed", dt, "Engineering", "Site", [("Change", txt)])

# Audits
doc("IA-2025-11", "Audit", "EQMS", "Internal audit report, Quality Systems and Microbiology (November 2025)", "1.0", "Closed", "2025-11-14", "Head of Quality", FS2,
    [("Finding 3", "Minor: monthly environmental monitoring summary reports for Filling Suite 2 were issued late in three of the last six months; quarterly trend report approval is not tracked."),
     ("Finding 5", "Observation: repeated Grade A results at the stopper bowl in Q3 2025 were closed by CAPA-25-019 without an effectiveness check.")],
    ["SOP-EM-014", "CAPA-25-019"])
doc("IA-2026-03", "Audit", "EQMS", "Internal audit report, Warehouse and Distribution", "1.0", "Closed", "2026-03-20", "Head of Quality", "Warehouse", [("Summary", "No critical or major findings.")])
doc("CMP-26-004", "Audit", "EQMS", "Customer complaint: cracked vial", "1.0", "Closed", "2026-02-18", "Quality Assurance", "Site", [("Complaint", "Cracked vial reported from a distributor; investigation concluded transit damage.")], type_="Complaint")

# ------------------------------------------------------------------ LIMS
doc("LIMS-EM-FL2", "LIMS data", "LIMS", "Environmental monitoring results, Filling Suite 2 (12 weeks)", "1.0", "Approved", "2026-06-30", "Microbiology", FS2,
    [("Summary", f"{len(rows)} samples across Grade A and Grade B locations, settle plates, April to June 2026. Grade A action limit 1 CFU. Organisms identified to species."),
     ("Locations", "FL2-A1 stopper bowl; FL2-A2 filling needle 3; FL2-A3 conveyor infeed; FL2-A4 star wheel; Grade B backgrounds.")],
    ["SOP-EM-014", "STP-MB-031"], {"csv": "em_data.csv"}, type_="EM dataset")
for t in site["trend_register"]:
    if t["status"] != "Not issued":
        doc(t["id"], "LIMS data", "LIMS", f"Quarterly EM trend report {t['period']}", "1.0", t["status"], "2026-01-19", "Head of Microbiology", FS2,
            [("Conclusion", "Grade A excursions at low frequency; no adverse trend; recommended continued monitoring at FL2-A1.")], ["SOP-EM-014"], {"period": t["period"]}, type_="Trend report")
for m, mon in enumerate(["January", "February", "March"], 1):
    doc(f"MSR-2026-0{m}", "LIMS data", "LIMS", f"Monthly EM summary {mon} 2026", "1.0", "Approved", "2026-0%d-1%d" % (m + 1, 4 + m), "Head of Microbiology", FS2,
        [("Summary", f"Environmental monitoring summary for {mon} 2026, Filling Suite 2: results reviewed by QA, no adverse trend.")], ["SOP-EM-014"], {"month": f"2026-0{m}"}, type_="Monthly EM summary")
doc("GPT-2026-Q1", "LIMS data", "LIMS", "Media growth promotion records Q1 2026", "1.0", "Approved", "2026-03-31", "Microbiology", "QC Microbiology", [("Result", "All media lots passed growth promotion.")], ["STP-MB-022"], type_="Media record")
doc("GPT-2026-Q2", "LIMS data", "LIMS", "Media growth promotion records Q2 2026", "1.0", "Approved", "2026-06-30", "Microbiology", "QC Microbiology", [("Result", "All media lots passed growth promotion.")], ["STP-MB-022"], type_="Media record")

# ------------------------------------------------------------------ LMS
DUE = {101: "2026-11-15", 102: "2026-10-01", 103: "2026-12-05", 104: "2026-03-31", 105: "2027-01-20", 106: "2026-09-10", 107: "2026-04-10", 108: "2026-12-12"}
for n in range(101, 109):
    over = DUE[n] < "2026-07-01"
    doc(f"TRN-OP-{n}", "Training", "LMS", f"Aseptic qualification record, operator OP-{n}", "1.0", "Overdue" if over else "Current", "2025-04-01", "Head of Aseptic Operations", FS2,
        [("Qualification", f"Operator OP-{n}: aseptic technique requalification due {DUE[n]}. Status as of 2026-07-01: {'OVERDUE' if over else 'current'}. Gowning qualification recorded.")],
        ["SOP-TR-009", "SOP-GW-002"], {"operator": f"OP-{n}", "requal_due": DUE[n], "status": "Overdue" if over else "Current"}, type_="Training record")
doc("TM-FL2", "Training", "LMS", "Training matrix, Filling Suite 2 aseptic operators", "1.0", "Current", "2026-07-01", "Head of Aseptic Operations", FS2,
    [("Summary", "Eight aseptic operators are assigned to Filling Line 2. Two operators have overdue aseptic technique requalification (OP-104, OP-107).")], ["SOP-TR-009"], type_="Training matrix")

# ------------------------------------------------------------------ CMMS
doc("EQ-FL2-STOPPER-PM", "Equipment", "CMMS", "Preventive maintenance record, stopper bowl and feeder, Line 2", "1.0", "Completed", "2026-03-27", "Engineering", FS2,
    [("Work done", "Stopper bowl vibratory feeder serviced and cover gasket replaced. No airflow visualisation performed after maintenance.")], ["PRT-VAL-EQ-STOPPER-2024"], {"date": "2026-03-27"}, type_="Equipment record")
doc("EQ-LOG-FL2", "Equipment", "CMMS", "Equipment logbook, Filling Line 2", "1.0", "Active", "2026-06-30", "Engineering", FS2,
    [("Entries", "Frequent stopper jam entries April to June 2026 at the stopper bowl; operator intervention logged each time.")], type_="Equipment record")
doc("CERT-HVAC-FL2-2026", "Equipment", "CMMS", "HEPA integrity and recovery certificate, Filling Suite 2", "1.0", "Current", "2026-01-12", "Engineering", FS2,
    [("Certificate", "HEPA filters serving Filling Suite 2 integrity tested and passed. Air handling unit AHU-07 also serves Filling Line 1.")], ["RPT-VAL-HVAC-2025-07"], {"serves": ["FL1", "FL2"]}, type_="Certificate")
doc("CAL-FL2-PARTICLE", "Equipment", "CMMS", "Particle counter calibration, Filling Suite 2", "1.0", "Current", "2026-02-02", "Engineering", FS2, [("Result", "Calibrated within tolerance.")], type_="Equipment record")
doc("CAL-AIRSAMPLER", "Equipment", "CMMS", "Active air sampler calibration", "1.0", "Current", "2026-02-02", "Engineering", "Filling Suite 2", [("Result", "Flow rate verified.")], type_="Equipment record")
doc("CERT-HVAC-FL1-2026", "Equipment", "CMMS", "HEPA integrity certificate, Filling Suite 1", "1.0", "Current", "2026-01-12", "Engineering", "Filling Suite 1", [("Certificate", "HEPA filters serving Filling Suite 1 tested and passed.")], type_="Certificate")

# ------------------------------------------------------------------ sanity + write
ids = [d["id"] for d in DOCS]
assert len(ids) == len(set(ids)), "duplicate ids"
known = set(ids)
for d in DOCS:
    d["refs"] = [r for r in d["refs"] if r in known]
out = {"site": "DEMO SITE (SYNTHETIC)", "as_of": "2026-07-01", "systems": SYSTEMS, "group_labels": GROUP_LABEL, "docs": DOCS}
json.dump(out, open(os.path.join(SITE, "docs.json"), "w", encoding="utf-8"), indent=1)
by_sys = {}
for d in DOCS:
    by_sys[d["system"]] = by_sys.get(d["system"], 0) + 1
print("documents", len(DOCS), by_sys)
