"""Facility libraries with immutable versions and indexed, category-scoped search."""
import base64
import concurrent.futures
import datetime
import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
import xml.etree.ElementTree as ET
from . import intake, sitedocs

DEFAULTS = ('SOP', 'STP', 'Protocol', 'BMR', 'Deviation', 'CAPA', 'Change control', 'Risk assessment')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS facilities(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_classes(id TEXT PRIMARY KEY, facility_id TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(facility_id,name));
CREATE TABLE IF NOT EXISTS facility_documents(id TEXT PRIMARY KEY, facility_id TEXT NOT NULL, class_id TEXT NOT NULL, document_id TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, uploaded_by TEXT NOT NULL, uploaded_at TEXT NOT NULL, UNIQUE(facility_id,document_id,version));
CREATE TABLE IF NOT EXISTS facility_passages(id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, facility_id TEXT NOT NULL, class_id TEXT NOT NULL, ref TEXT NOT NULL, text TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS facility_fts USING fts5(title,text, tokenize='porter unicode61');
'''

def init(con):
    con.executescript(SCHEMA)

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def require(con, facility_id):
    row = con.execute('SELECT * FROM facilities WHERE id=?', (facility_id,)).fetchone()
    if not row:
        raise ValueError('Unknown facility')
    return dict(row)

def create(con, body, username):
    init(con)
    name = body.get('name')
    if not name:
        name = f'Facility {con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] + 1:02d}'
    name = intake.text({'name': name}, 'name', 200)
    identifier = 'FAC-' + uuid.uuid4().hex
    try:
        with con:
            con.execute('INSERT INTO facilities VALUES(?,?,?,?)', (identifier, name, username, now()))
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

def listing(con):
    init(con)
    return [dict(row) for row in con.execute('SELECT f.*,COUNT(d.id) document_count FROM facilities f LEFT JOIN facility_documents d ON d.facility_id=f.id GROUP BY f.id ORDER BY f.created_at,f.name')]

def library(con, facility_id):
    init(con); facility = require(con, facility_id)
    classes = [dict(row) for row in con.execute('SELECT c.*,COUNT(d.id) document_count FROM document_classes c LEFT JOIN facility_documents d ON d.class_id=c.id WHERE c.facility_id=? GROUP BY c.id ORDER BY c.name', (facility_id,))]
    documents = []
    for row in con.execute('SELECT d.*,c.name class_name FROM facility_documents d JOIN document_classes c ON c.id=d.class_id WHERE d.facility_id=? ORDER BY d.uploaded_at DESC', (facility_id,)):
        doc = json.loads(row['payload'])
        documents.append({**{key: row[key] for key in ('id','document_id','class_id','class_name','version','sha256','uploaded_at')}, 'title': doc['title'], 'date': doc['date'], 'status': doc['status'], 'source': doc['source']})
    return {'facility': facility, 'classes': classes, 'documents': documents}

def extract(filename, content):
    try:
        raw = base64.b64decode(content, validate=True)
    except (ValueError, TypeError):
        raise ValueError('Invalid file encoding') from None
    if not 0 < len(raw) <= 3000000:
        raise ValueError('File must be between 1 byte and 3 MB')
    if filename.lower().endswith(('.txt', '.md', '.csv')):
        return raw.decode('utf-8-sig')
    if filename.lower().endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.getinfo('word/document.xml')
            if info.file_size > 5000000:
                raise ValueError('Expanded document is too large')
            root = ET.fromstring(archive.read(info))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p', ns))
    raise ValueError('Supported files: UTF-8 TXT, MD, CSV and DOCX. Export scanned or PDF evidence to verified text first.')

def upload(con, facility_id, body, username):
    init(con); require(con, facility_id)
    cls = con.execute('SELECT * FROM document_classes WHERE id=? AND facility_id=?', (body.get('class_id'), facility_id)).fetchone()
    if not cls:
        raise ValueError('Select a category belonging to this facility')
    if not isinstance(body.get('document'), dict):
        raise ValueError('Document metadata is required')
    doc = dict(body['document'])
    if 'file' in body:
        try:
            text = extract(intake.text(body, 'filename', 200), body['file'])
        except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError):
            raise ValueError('Invalid or unsupported DOCX document') from None
        if len(text) > 1000000:
            raise ValueError('Document text exceeds 1 million characters')
        doc['sections'] = [{'ref': f'Imported passage {i//12000+1}', 'text': text[i:i+12000]} for i in range(0,len(text),12000) if text[i:i+12000].strip()]
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

def case(con, facility_id, body, username):
    init(con); facility = require(con, facility_id)
    ids = body.get('document_ids')
    if not isinstance(ids,list) or not 1 <= len(ids) <= 500 or not all(isinstance(x,str) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('Select 1–500 unique document versions')
    docs = []
    for identifier in ids:
        row = con.execute('SELECT * FROM facility_documents WHERE id=? AND facility_id=?',(identifier,facility_id)).fetchone()
        if not row or hashlib.sha256(row['payload'].encode()).hexdigest() != row['sha256']:
            raise ValueError('Document is missing, belongs to another facility, or failed integrity checks')
        docs.append(json.loads(row['payload']))
    if len({d['id'] for d in docs}) != len(docs):
        raise ValueError('Select only one version of each document')
    package = {**body, 'site_name':facility['name'], 'authority':'US FDA', 'synthetic':False, 'documents':docs, 'facility_id':facility_id, 'document_records':ids}
    return intake.save(con, package, username)
