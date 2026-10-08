"""Validated, immutable case packages with source provenance."""
import datetime
import hashlib
import json
import re
import uuid

SCHEMA = """CREATE TABLE IF NOT EXISTS cases_v1(
 case_id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
 imported_by TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL
)"""


def text(obj, key, maximum=10000):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{key}: nonempty text required (maximum {maximum} characters)")
    return value.strip()


def validate(package):
    if not isinstance(package, dict):
        raise ValueError("Case package must be a JSON object")
    if package.get("synthetic") is not False:
        raise ValueError("Case package must explicitly declare synthetic: false")
    if package.get("authority") != "US FDA":
        raise ValueError("This corpus currently supports US FDA / 21 CFR only")
    result = {"title": text(package, "title", 300), "observation": text(package, "observation", 30000),
              "site_name": text(package, "site_name", 200), "product_class": text(package, "product_class", 200),
              "authority": "US FDA", "synthetic": False, "schema_version": 1}
    documents = package.get("documents")
    if not isinstance(documents, list) or not 1 <= len(documents) <= 500:
        raise ValueError("Supply between 1 and 500 source documents")
    normalized, seen = [], set()
    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError("Each source document must be an object")
        identifier = text(doc, "id", 100)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", identifier) or identifier in seen:
            raise ValueError("Document IDs must be unique and contain letters, digits, '.', '_' or '-'")
        seen.add(identifier)
        date = text(doc, "date", 10)
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            raise ValueError(f"{identifier}: date must be YYYY-MM-DD") from None
        sections = doc.get("sections")
        if not isinstance(sections, list) or not 1 <= len(sections) <= 100:
            raise ValueError(f"{identifier}: supply 1–100 source passages")
        passages = [{"ref": text(section, "ref", 200), "text": text(section, "text", 20000)} for section in sections if isinstance(section, dict)]
        if len(passages) != len(sections):
            raise ValueError(f"{identifier}: invalid passage")
        group = text(doc, "group", 100)
        plant = doc.get("plant") if isinstance(doc.get("plant"), str) else ""
        facility_name = doc.get("facility") if isinstance(doc.get("facility"), str) else ""
        record = {"id": identifier, "title": text(doc, "title", 300), "version": text(doc, "version", 50),
                  "date": date, "status": text(doc, "status", 50), "group": group,
                  "source": text(doc, "source", 1000), "sections": passages,
                  "type": group, "system": group, "plant": plant.strip()[:200], "facility": facility_name.strip()[:200],
                  "area": "", "meta": {}}
        record["sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        normalized.append(record)
    if package.get("facility_id"):
        result["facility_id"] = text(package, "facility_id", 100)
        result["document_records"] = package.get("document_records", [])
    result["documents"] = normalized
    result["id"] = "CASE-" + uuid.uuid4().hex
    return result


def save(con, package, username):
    case = validate(package)
    payload = json.dumps(case, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    con.execute(SCHEMA)
    con.execute("INSERT INTO cases_v1 VALUES(?,?,?,?,?,?)", (case["id"], case["title"],
                datetime.datetime.now(datetime.timezone.utc).isoformat(), username, payload, digest))
    con.commit()
    return case, digest


def load(con, identifier):
    con.execute(SCHEMA)
    row = con.execute("SELECT payload,sha256 FROM cases_v1 WHERE case_id=?", (identifier,)).fetchone()
    if not row:
        raise ValueError("Unknown imported case")
    if hashlib.sha256(row["payload"].encode()).hexdigest() != row["sha256"]:
        raise ValueError("Case package integrity check failed")
    return json.loads(row["payload"])


def recent(con):
    con.execute(SCHEMA)
    return [{"id": row["case_id"], "title": row["title"], "synthetic": False} for row in con.execute(
        "SELECT case_id,title FROM cases_v1 ORDER BY created_at DESC LIMIT 100")]
