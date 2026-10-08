"""Plant and facility libraries with immutable versions and indexed, category-scoped search."""
import base64
import concurrent.futures
import datetime
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
import zipfile
import zlib
import xml.etree.ElementTree as ET
from . import intake, sitedocs

DEFAULTS = ('SOP', 'STP', 'BMR', 'Protocol', 'MFR', 'Deviation', 'OOS', 'Qualification')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS plants(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS facilities(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_by TEXT NOT NULL, created_at TEXT NOT NULL, plant_id TEXT);
CREATE TABLE IF NOT EXISTS document_classes(id TEXT PRIMARY KEY, facility_id TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(facility_id,name));
CREATE TABLE IF NOT EXISTS facility_documents(id TEXT PRIMARY KEY, facility_id TEXT NOT NULL, class_id TEXT NOT NULL, document_id TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL, UNIQUE(facility_id,document_id,version));
CREATE TABLE IF NOT EXISTS facility_passages(id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, facility_id TEXT NOT NULL, class_id TEXT NOT NULL, ref TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_attachments(id TEXT PRIMARY KEY, record_id TEXT NOT NULL, filename TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL, content BLOB NOT NULL, uploaded_at TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS facility_fts USING fts5(title,text, tokenize='porter unicode61');
'''

def init(con):
    con.executescript(SCHEMA)
    columns = {row[1] for row in con.execute('PRAGMA table_info(facilities)')}
    if 'plant_id' not in columns:
        con.execute('ALTER TABLE facilities ADD COLUMN plant_id TEXT')
    if con.execute("SELECT COUNT(*) FROM facilities WHERE plant_id IS NULL OR plant_id=''").fetchone()[0]:
        row = con.execute("SELECT id FROM plants WHERE name='Existing site'").fetchone()
        plant_id = row['id'] if row else 'PLT-' + uuid.uuid4().hex
        if not row:
            con.execute('INSERT INTO plants VALUES(?,?,?,?)', (plant_id, 'Existing site', 'system', now()))
        con.execute("UPDATE facilities SET plant_id=? WHERE plant_id IS NULL OR plant_id=''", (plant_id,))
    facility_ids = [row['id'] for row in con.execute('SELECT id FROM facilities')]
    for facility_id in facility_ids:
        have = {row['name'] for row in con.execute('SELECT name FROM document_classes WHERE facility_id=?', (facility_id,))}
        for label in DEFAULTS:
            if label not in have:
                con.execute('INSERT INTO document_classes VALUES(?,?,?)', ('CLS-' + uuid.uuid4().hex, facility_id, label))
    con.commit()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def require(con, facility_id):
    row = con.execute('SELECT f.*, p.name AS plant_name FROM facilities f LEFT JOIN plants p ON p.id=f.plant_id WHERE f.id=?', (facility_id,)).fetchone()
    if not row:
        raise ValueError('Unknown facility')
    return dict(row)

def create_plant(con, body, username):
    init(con)
    name = body.get('name')
    if not name:
        name = f'Plant {con.execute("SELECT COUNT(*) FROM plants").fetchone()[0] + 1:02d}'
    name = intake.text({'name': name}, 'name', 200)
    identifier = 'PLT-' + uuid.uuid4().hex
    try:
        with con:
            con.execute('INSERT INTO plants VALUES(?,?,?,?)', (identifier, name, username, now()))
    except sqlite3.IntegrityError:
        raise ValueError('Plant name already exists') from None
    return identifier

def _default_plant(con, username):
    row = con.execute('SELECT id FROM plants ORDER BY created_at, name LIMIT 1').fetchone()
    if row:
        return row['id']
    return create_plant(con, {'name': 'Plant 01'}, username)

def create(con, body, username):
    init(con)
    plant_id = body.get('plant_id') or _default_plant(con, username)
    if not con.execute('SELECT 1 FROM plants WHERE id=?', (plant_id,)).fetchone():
        raise ValueError('Unknown plant')
    name = body.get('name')
    if not name:
        name = f'Facility {con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] + 1:02d}'
    name = intake.text({'name': name}, 'name', 200)
    identifier = 'FAC-' + uuid.uuid4().hex
    try:
        with con:
            con.execute('INSERT INTO facilities(id,name,created_by,created_at,plant_id) VALUES(?,?,?,?,?)', (identifier, name, username, now(), plant_id))
            for label in DEFAULTS:
                con.execute('INSERT INTO document_classes VALUES(?,?,?)', ('CLS-' + uuid.uuid4().hex, identifier, label))
    except sqlite3.IntegrityError:
        raise ValueError('Facility name already exists') from None
    return identifier

def category(con, facility_id, body):
    init(con); require(con, facility_id)
    name = intake.text(body, 'name', 100)
    identifier = 'CLS-' + uuid.uuid4().hex
    try:
        with con:
            con.execute('INSERT INTO document_classes VALUES(?,?,?)', (identifier, facility_id, name))
    except sqlite3.IntegrityError:
        raise ValueError('Category already exists in this facility') from None
    return identifier

def plants(con):
    init(con)
    return [dict(row) for row in con.execute('SELECT p.*,COUNT(f.id) facility_count FROM plants p LEFT JOIN facilities f ON f.plant_id=p.id GROUP BY p.id ORDER BY p.created_at,p.name')]

def listing(con, plant_id=None):
    init(con)
    sql = '''SELECT f.id,f.name,f.created_by,f.created_at,f.plant_id,p.name plant_name,COUNT(d.id) document_count
             FROM facilities f LEFT JOIN plants p ON p.id=f.plant_id
             LEFT JOIN facility_documents d ON d.facility_id=f.id'''
    args = []
    if plant_id:
        sql += ' WHERE f.plant_id=?'
        args.append(plant_id)
    sql += ' GROUP BY f.id ORDER BY f.created_at,f.name'
    return [dict(row) for row in con.execute(sql, args)]

def _class_order(name):
    return (DEFAULTS.index(name) if name in DEFAULTS else len(DEFAULTS), name)

def library(con, facility_id):
    init(con); facility = require(con, facility_id)
    classes = [dict(row) for row in con.execute('SELECT c.*,COUNT(d.id) document_count FROM document_classes c LEFT JOIN facility_documents d ON d.class_id=c.id WHERE c.facility_id=? GROUP BY c.id', (facility_id,))]
    classes.sort(key=lambda item: _class_order(item['name']))
    attachments = {}
    for row in con.execute('''SELECT a.id,a.record_id,a.filename,a.size,a.sha256 FROM document_attachments a
                               JOIN facility_documents d ON d.id=a.record_id WHERE d.facility_id=? ORDER BY a.uploaded_at''', (facility_id,)):
        attachments.setdefault(row['record_id'], []).append({key: row[key] for key in ('id', 'filename', 'size', 'sha256')})
    documents = []
    for row in con.execute('SELECT d.*,c.name class_name FROM facility_documents d JOIN document_classes c ON c.id=d.class_id WHERE d.facility_id=? ORDER BY c.name,d.document_id,d.version', (facility_id,)):
        doc = json.loads(row['payload'])
        documents.append({**{key: row[key] for key in ('id','document_id','class_id','class_name','version','sha256','uploaded_at')}, 'title': doc['title'], 'date': doc['date'], 'status': doc['status'], 'source': doc['source'], 'attachments': attachments.get(row['id'], [])})
    return {'facility': facility, 'classes': classes, 'documents': documents}

def _wrap(text, width=90):
    lines = []
    for block in text.splitlines() or ['']:
        current = ''
        for word in block.split():
            trial = (current + ' ' + word).strip()
            if len(trial) > width and current:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines or ['']

def build_doc(title, paragraphs):
    """Word-readable .doc (RTF) file."""
    def esc(value):
        return value.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')
    body = [r'{\rtf1\ansi\deff0{\fonttbl{\f0 Calibri;}}\f0\fs28\b ' + esc(title) + r'\b0\par\fs22 ']
    for paragraph in paragraphs:
        body.append(esc(paragraph) + r'\par ')
    body.append('}')
    return ''.join(body).encode('latin-1', errors='replace')

def build_pdf(title, paragraphs):
    """Text PDF with a selectable text layer."""
    def esc(value):
        return value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    lines = _wrap(title) + ['']
    for paragraph in paragraphs:
        lines.extend(_wrap(paragraph))
        lines.append('')
    lines = lines[:45]
    commands = ['BT', '/F1 11 Tf', '14 TL', '72 740 Td']
    for index, line in enumerate(lines):
        if index:
            commands.append('T*')
        commands.append('(' + esc(line) + ') Tj')
    commands.append('ET')
    stream = '\n'.join(commands).encode('latin-1', errors='replace')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n'.encode()
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode()
    out += f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    return bytes(out)

def _rtf_text(raw):
    data = raw.decode('latin-1', errors='replace')
    data = re.sub(r'\{\\fonttbl[^{}]*\}', '', data)
    data = data.replace('\\par', '\n').replace('\\line', '\n').replace('\\tab', ' ')
    data = re.sub(r"\\'[0-9a-fA-F]{2}", lambda match: bytes.fromhex(match.group(0)[2:]).decode('latin-1'), data)
    data = re.sub(r'\\[a-zA-Z]+-?\d* ?', '', data)
    text = data.replace('{', '').replace('}', '')
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        raise ValueError('Word document has no extractable text')
    return text

def _pdf_literals(data):
    out, index, size = [], 0, len(data)
    while index < size:
        if data[index:index + 1] != b'(':
            index += 1
            continue
        index += 1
        buf, depth = bytearray(), 1
        while index < size and depth:
            char = data[index]
            if char == 0x5C and index + 1 < size:
                index += 1
                esc = data[index]
                mapped = {ord('n'): 10, ord('r'): 13, ord('t'): 9, ord('b'): 8, ord('f'): 12, ord('('): 40, ord(')'): 41, ord('\\'): 92}
                if esc in mapped:
                    buf.append(mapped[esc])
                elif 48 <= esc <= 55:
                    octal = bytearray([esc])
                    for _ in range(2):
                        if index + 1 < size and 48 <= data[index + 1] <= 55:
                            index += 1
                            octal.append(data[index])
                        else:
                            break
                    buf.append(int(bytes(octal), 8) & 0xFF)
                else:
                    buf.append(esc)
            elif char == 0x28:
                depth += 1
                buf.append(char)
            elif char == 0x29:
                depth -= 1
                if depth:
                    buf.append(char)
            else:
                buf.append(char)
            index += 1
        out.append(buf.decode('latin-1', errors='replace'))
    return '\n'.join(part for part in out if part.strip())

def _pdf_text(raw):
    pieces = []
    for match in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', raw, re.S):
        data = match.group(1)
        if len(data) <= 5000000:
            try:
                data = zlib.decompress(data)
            except zlib.error:
                pass
        if len(data) > 5000000:
            raise ValueError('Expanded PDF is too large')
        pieces.append(_pdf_literals(data))
    if not any(pieces):
        pieces.append(_pdf_literals(raw))
    text = '\n'.join(part for part in pieces if part.strip()).strip()
    if not text:
        raise ValueError('This PDF has no selectable text. Scanned pages need a text-based PDF.')
    return text

def _docx_text(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > 5000000:
            raise ValueError('Expanded document is too large')
        root = ET.fromstring(archive.read(info))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p', ns))

def extract(filename, content):
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, TypeError):
        raise ValueError('Invalid file encoding') from None
    if not 0 < len(raw) <= 3000000:
        raise ValueError('File must be between 1 byte and 3 MB')
    lower = filename.lower()
    if lower.endswith(('.txt', '.md', '.csv')):
        return raw.decode('utf-8-sig')
    if lower.endswith('.pdf'):
        return _pdf_text(raw)
    if lower.endswith('.docx') or (lower.endswith('.doc') and raw[:2] == b'PK'):
        try:
            return _docx_text(raw)
        except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError):
            raise ValueError('Invalid Word document') from None
    if lower.endswith('.doc'):
        return _rtf_text(raw)
    raise ValueError('Upload a Word file (.doc or .docx) or a text-based PDF.')

def file_parts(filename, content, label):
    try:
        text = extract(filename, content)
        raw = base64.b64decode(content, validate=True)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError):
        raise ValueError('Invalid or unsupported DOCX document') from None
    if len(text) > 1000000:
        raise ValueError('Document text exceeds 1 million characters')
    sections = [{'ref': f'{label} {i//12000+1}', 'text': text[i:i+12000]} for i in range(0, len(text), 12000) if text[i:i+12000].strip()]
    if not sections:
        raise ValueError('File has no text to store')
    return sections, raw

def upload(con, facility_id, body, username):
    init(con); require(con, facility_id)
    cls = con.execute('SELECT * FROM document_classes WHERE id=? AND facility_id=?', (body.get('class_id'), facility_id)).fetchone()
    if not cls:
        raise ValueError('Select a category belonging to this facility')
    if not isinstance(body.get('document'), dict):
        raise ValueError('Document metadata is required')
    doc = dict(body['document'])
    stored = []
    if 'file' in body:
        sections, raw = file_parts(intake.text(body, 'filename', 200), body['file'], 'Imported passage')
        doc['sections'] = sections
        stored.append((intake.text(body, 'filename', 200), raw))
    extras = body.get('attachments') or []
    if not isinstance(extras, list) or len(extras) > 12:
        raise ValueError('Add at most 12 attachments')
    extra_sections = []
    for item in extras:
        if not isinstance(item, dict) or 'file' not in item:
            raise ValueError('Each attachment needs a filename and file')
        filename = intake.text(item, 'filename', 200)
        sections, raw = file_parts(filename, item['file'], filename)
        extra_sections.extend(sections)
        stored.append((filename, raw))
    if extra_sections:
        doc['sections'] = list(doc.get('sections') or []) + extra_sections
    if len(doc.get('sections') or []) > 100:
        raise ValueError('Document and attachments exceed 100 passages')
    doc['group'] = cls['name']
    package = {'title':'Library import', 'observation':'Library source record', 'site_name':'Facility', 'product_class':'Library', 'authority':'US FDA', 'synthetic':False, 'documents':[doc]}
    normalized = intake.validate(package)['documents'][0]
    identifier = 'DOC-' + uuid.uuid4().hex
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    try:
        with con:
            con.execute('INSERT INTO facility_documents VALUES(?,?,?,?,?,?,?,?,?)', (identifier,facility_id,cls['id'],doc['id'],doc['version'],payload,digest,username,now()))
            for section in normalized['sections']:
                cur = con.execute('INSERT INTO facility_passages(record_id,facility_id,class_id,ref,text) VALUES(?,?,?,?,?)', (identifier,facility_id,cls['id'],section['ref'],section['text']))
                con.execute('INSERT INTO facility_fts(rowid,title,text) VALUES(?,?,?)', (cur.lastrowid,normalized['title'],section['text']))
            for filename, raw in stored:
                con.execute('INSERT INTO document_attachments VALUES(?,?,?,?,?,?,?)', ('ATT-' + uuid.uuid4().hex, identifier, os.path.basename(filename), hashlib.sha256(raw).hexdigest(), len(raw), raw, now()))
    except sqlite3.IntegrityError:
        raise ValueError('This document ID and version already exist; upload a new version') from None
    return identifier, digest

def search(con, facility_id, query, class_id=None):
    init(con); require(con, facility_id)
    query = intake.text({'query':query}, 'query', 1000)
    tokens = sitedocs.terms(query)[:40]
    if not tokens:
        return {'hits':[], 'workers':[]}
    classes = [dict(row) for row in con.execute('SELECT * FROM document_classes WHERE facility_id=?', (facility_id,)) if not class_id or row['id'] == class_id]
    if class_id and not classes:
        raise ValueError('Unknown facility category')
    path = con.execute('PRAGMA database_list').fetchone()[2]
    match = ' OR '.join('"'+t+'"' for t in tokens)
    def worker(cls):
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute('''SELECT p.record_id,p.ref,p.text,d.document_id,d.version,d.sha256,bm25(facility_fts,2,1) rank FROM facility_fts JOIN facility_passages p ON p.id=facility_fts.rowid JOIN facility_documents d ON d.id=p.record_id WHERE facility_fts MATCH ? AND p.facility_id=? AND p.class_id=? ORDER BY rank LIMIT 20''', (match,facility_id,cls['id'])).fetchall()
            return [{'category':cls['name'], **dict(row)} for row in rows]
        finally:
            connection.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8,len(classes) or 1)) as pool:
        results = list(pool.map(worker,classes))
    hits = sorted([hit for result in results for hit in result], key=lambda hit:hit['rank'])[:40]
    return {'hits':hits, 'workers':[{'name':cls['name']+' search', 'hits':len(result)} for cls,result in zip(classes,results)], 'ranking':'FTS5 BM25; lower rank is better'}

def case(con, facility_id, body, username, library_wide=False):
    init(con); facility = require(con, facility_id)
    ids = body.get('document_ids')
    if not isinstance(ids,list) or not 1 <= len(ids) <= 500 or not all(isinstance(x,str) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('Select 1–500 unique document versions')
    docs, seen_ids = [], set()
    for identifier in ids:
        if library_wide:
            row = con.execute('SELECT * FROM facility_documents WHERE id=?', (identifier,)).fetchone()
        else:
            row = con.execute('SELECT * FROM facility_documents WHERE id=? AND facility_id=?',(identifier,facility_id)).fetchone()
        if not row or hashlib.sha256(row['payload'].encode()).hexdigest() != row['sha256']:
            raise ValueError('Document is missing, belongs to another facility, or failed integrity checks')
        doc = json.loads(row['payload'])
        home = require(con, row['facility_id']) if library_wide else facility
        doc['plant'] = home['plant_name'] or ''
        doc['facility'] = home['name']
        if library_wide:
            place = ' / '.join(part for part in (home['plant_name'], home['name']) if part)
            doc['title'] = f"{place} / {doc['title']}"[:300]
            doc['source'] = f"{place} / {doc.get('source', '')}"[:1000]
            if doc['id'] in seen_ids:
                doc['id'] = f"{row['facility_id'][-6:]}-{doc['id']}"[:100]
        if doc['id'] in seen_ids:
            raise ValueError('Select only one version of each document')
        seen_ids.add(doc['id'])
        docs.append(doc)
    package = {**body, 'site_name':facility['name'], 'authority':'US FDA', 'synthetic':False, 'documents':docs, 'facility_id':facility_id, 'document_records':ids}
    return intake.save(con, package, username)

def attachment(con, facility_id, attachment_id):
    init(con)
    require(con, facility_id)
    row = con.execute('''SELECT a.filename, a.content FROM document_attachments a
                         JOIN facility_documents d ON d.id=a.record_id
                         WHERE a.id=? AND d.facility_id=?''', (attachment_id, facility_id)).fetchone()
    if not row:
        raise ValueError('Attachment not found')
    name = os.path.basename(row['filename']).replace('"', '').replace('\r', '').replace('\n', '') or 'attachment'
    return name, bytes(row['content'])

def latest_documents(con, facility_id):
    chosen, seen = [], set()
    for row in con.execute('SELECT id, document_id FROM facility_documents WHERE facility_id=? ORDER BY uploaded_at DESC', (facility_id,)):
        if row['document_id'] in seen:
            continue
        seen.add(row['document_id'])
        chosen.append(row['id'])
    return chosen

def latest_library(con, home_facility_id=None):
    """Current version of every document, with the queried facility first."""
    init(con)
    rows = list(con.execute('SELECT id, facility_id, document_id FROM facility_documents ORDER BY uploaded_at DESC'))
    chosen, seen = [], set()

    def take(row):
        key = (row['facility_id'], row['document_id'])
        if key in seen or len(chosen) >= 500:
            return
        seen.add(key)
        chosen.append(row['id'])

    if home_facility_id:
        for row in rows:
            if row['facility_id'] == home_facility_id:
                take(row)
    for row in rows:
        take(row)
    return chosen

def batch_items(body):
    """Each item is one observation tied to one facility."""
    if not isinstance(body, dict):
        raise ValueError('Add at least one audit query')
    raw = body.get('items')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 30:
        raise ValueError('Submit between 1 and 30 audit queries')
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError('Each query needs a facility and an observation')
        facility_id = entry.get('facility_id')
        text = entry.get('query')
        product = entry.get('product_class') or body.get('product_class') or 'Vaccine'
        if not isinstance(facility_id, str) or not facility_id.strip():
            raise ValueError('Each query needs a facility')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Each query needs an observation')
        if len(text.strip()) > 2000:
            raise ValueError('Each audit query must be 2000 characters or fewer')
        if not isinstance(product, str) or not product.strip():
            raise ValueError('Each query needs a product')
        items.append({'facility_id': facility_id.strip(), 'queries': [text.strip()], 'product_class': product.strip()[:200]})
    return items

def audit_queries(con, facility_id, body, username):
    init(con)
    facility = require(con, facility_id)
    raw = body.get('queries')
    if isinstance(raw, str):
        items = [line.strip() for line in raw.splitlines() if line.strip()]
    elif isinstance(raw, list):
        items = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    else:
        raise ValueError('Add at least one audit query')
    if not 1 <= len(items) <= 30:
        raise ValueError('Submit between 1 and 30 audit queries')
    if any(len(item) > 2000 for item in items):
        raise ValueError('Each audit query must be 2000 characters or fewer')
    wide = not body.get('document_ids')
    ids = body.get('document_ids') or latest_library(con, facility_id)
    if not ids:
        raise ValueError('No documents are stored yet. Add records before loading audit queries.')
    scope = f" The current version of {len(ids)} stored document(s) from every facility is indexed for this query." if wide else ''
    observation = 'Audit queries for ' + facility['name'] + ':' + scope + '\n' + '\n'.join(f'{index}. {item}' for index, item in enumerate(items, 1))
    title = (body.get('title') or f"Audit queries · {facility['name']}")[:300]
    product = body.get('product_class') or 'Vaccine'
    return case(con, facility_id, {'title': title, 'product_class': product, 'observation': observation, 'document_ids': ids}, username, library_wide=wide)

SAMPLES = {
    'SOP': [
        ('Cleaning of product-contact surfaces', 'Clean product-contact parts with the approved agent, record the dirty-hold time, and meet the residue acceptance limit before the next batch starts.'),
        ('Environmental monitoring of classified rooms', 'Collect settle plates and active air samples each filling shift. Investigate action-limit excursions before batch disposition.'),
    ],
    'STP': [
        ('Assay and impurity method', 'The method states system suitability, the reference standard, and the impurity reporting threshold used before a result is reported.'),
    ],
    'BMR': [
        ('Executed batch record', 'The batch record shows material dispensing, in-process checks, yield reconciliation, chain of identity where it applies, and the reviewer signature.'),
        ('Executed filling record', 'The filling record records line clearance, component lot, fill checks, and the environmental monitoring session.'),
    ],
    'Protocol': [
        ('Cleaning validation protocol', 'The protocol defines worst-case product, swab locations, residue limits, and the acceptance criteria for three consecutive runs.'),
    ],
    'MFR': [
        ('Master formulation record', 'The master formula lists the bill of materials, theoretical yield, process parameters, and the approved manufacturing instructions.'),
    ],
    'Deviation': [
        ('Line clearance deviation', 'Line clearance found retained labels from the previous lot. The lot was quarantined and the investigation recorded product impact.'),
    ],
    'OOS': [
        ('Out-of-specification assay result', 'The initial assay result was outside the specification. The laboratory investigation checked the method, the standard, and the sample preparation before a retest decision.'),
    ],
    'Qualification': [
        ('Equipment IQ OQ PQ summary', 'Installation, operational, and performance qualification of the filler recorded calibration, alarm challenges, and three acceptable media-fill or performance runs.'),
    ],
}

def load_samples(con, username):
    """Insert vaccine and cell-and-gene-therapy sample plants when they are not already stored."""
    init(con)
    counts = {'SOP': 2, 'STP': 1, 'BMR': 2, 'Protocol': 1, 'MFR': 1, 'Deviation': 1, 'OOS': 1, 'Qualification': 1}
    sites = [
        ('Vaccine Manufacturing Plant', [('Formulation and Filling', 'VAX', 'Vaccine'), ('Vaccine Quality Control', 'VQC', 'Vaccine')]),
        ('Cell and Gene Therapy Plant', [('Cell Processing', 'CGT', 'Cell and gene therapy'), ('Vector Manufacturing', 'VEC', 'Cell and gene therapy')]),
    ]
    created = 0
    for plant_name, facilities_spec in sites:
        if con.execute('SELECT 1 FROM plants WHERE name=?', (plant_name,)).fetchone():
            continue
        plant_id = create_plant(con, {'name': plant_name}, username)
        for facility_name, code, product in facilities_spec:
            facility_id = create(con, {'plant_id': plant_id, 'name': facility_name}, username)
            classes = {item['name']: item['id'] for item in library(con, facility_id)['classes']}
            for category, count in counts.items():
                for number, (title, text) in enumerate(SAMPLES[category][:count], 1):
                    passage = f'{facility_name}. {text} Product class: {product}.'
                    attachment = f'Attachment checklist for {code}-{category[:3]}-{number:02d}. Confirm the source record, version, and approval before use.'
                    main_name, main_bytes, extra_name, extra_bytes = office_pair(f'{code}-{category[:3]}-{number:02d}', title, passage, 'Checklist', attachment)
                    upload(con, facility_id, {
                        'class_id': classes[category],
                        'filename': main_name,
                        'file': base64.b64encode(main_bytes).decode(),
                        'attachments': [{'filename': extra_name, 'file': base64.b64encode(extra_bytes).decode()}],
                        'document': {
                            'id': f'{code}-{category[:3]}-{number:02d}',
                            'title': title,
                            'version': '1.0',
                            'date': '2026-03-15',
                            'status': 'Sample',
                            'source': f'Sample library / {plant_name} / {facility_name}',
                        },
                    }, username)
                    created += 1
    return {'created': created > 0, 'documents': created}

def office_pair(stem, title, passage, attachment_title, attachment_text):
    """One Word .doc and one PDF. The main file alternates by record id."""
    main_pdf = sum(ord(char) for char in stem) % 2 == 0
    if main_pdf:
        return stem + '.pdf', build_pdf(title, [passage]), stem + '-checklist.doc', build_doc(attachment_title, [attachment_text])
    return stem + '.doc', build_doc(title, [passage]), stem + '-checklist.pdf', build_pdf(attachment_title, [attachment_text])

def rewrite_sample_files(con, username):
    """Replace sample text files with a Word .doc and a PDF."""
    init(con)
    rows = []
    for row in con.execute('SELECT id, facility_id, class_id, document_id, version, payload FROM facility_documents'):
        doc = json.loads(row['payload'])
        if str(doc.get('source', '')).startswith('Sample library'):
            rows.append((row, doc))
    if not rows:
        return {'replaced': 0}
    with con:
        for row, _doc in rows:
            for passage in con.execute('SELECT id FROM facility_passages WHERE record_id=?', (row['id'],)):
                con.execute('DELETE FROM facility_fts WHERE rowid=?', (passage['id'],))
            con.execute('DELETE FROM facility_passages WHERE record_id=?', (row['id'],))
            con.execute('DELETE FROM document_attachments WHERE record_id=?', (row['id'],))
            con.execute('DELETE FROM facility_documents WHERE id=?', (row['id'],))
    replaced = 0
    for row, doc in rows:
        sections = doc.get('sections') or []
        passage = sections[0]['text'] if sections else doc['title']
        attachment = next((section['text'] for section in sections[1:] if section.get('text')), 'Checklist: confirm the source record, version, and approval before use.')
        main_name, main_bytes, extra_name, extra_bytes = office_pair(doc['id'], doc['title'], passage, 'Checklist', attachment)
        upload(con, row['facility_id'], {
            'class_id': row['class_id'],
            'filename': main_name,
            'file': base64.b64encode(main_bytes).decode(),
            'attachments': [{'filename': extra_name, 'file': base64.b64encode(extra_bytes).decode()}],
            'document': {'id': doc['id'], 'title': doc['title'], 'version': doc['version'], 'date': doc['date'], 'status': doc['status'], 'source': doc['source']},
        }, username)
        replaced += 1
    return {'replaced': replaced}
