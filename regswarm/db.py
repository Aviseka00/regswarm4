"""SQLite corpus + audit store. Standard library only.

Corpus model (regulation text is stored at paragraph level so citations can be
verified down to (c)(10)(iv) rather than just the section):

  sources   one row per ingested document (e.g. "21 CFR Part 211") with the
            currency date the text was current as of
  sections  one row per section ("21 CFR 211.42"), status = active | reserved
  paras     one row per paragraph with its label path ("c/10/iv")
  paras_fts FTS5 (BM25) index over paragraph text + section heading
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("REGSWARM_DB", os.path.join(ROOT, "data", "corpus.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  doc_id TEXT PRIMARY KEY,      -- e.g. '21 CFR Part 211'
  authority TEXT,               -- e.g. 'US FDA'
  title TEXT,
  as_of TEXT,                   -- eCFR currency date (YYYY-MM-DD)
  fetched_at TEXT,
  url TEXT
);
CREATE TABLE IF NOT EXISTS sections(
  id TEXT PRIMARY KEY,          -- '21 CFR 211.42'
  doc_id TEXT,
  section TEXT,                 -- '211.42'
  heading TEXT,
  status TEXT,                  -- active | reserved
  cita TEXT,                    -- source / amendment citation line
  as_of TEXT,
  url TEXT,
  full_text TEXT
);
CREATE TABLE IF NOT EXISTS paras(
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  section_id TEXT,
  ord INTEGER,
  path TEXT,                    -- '' (lead-in) or 'c/10/iv'
  text TEXT
);
CREATE INDEX IF NOT EXISTS paras_section ON paras(section_id, ord);
CREATE VIRTUAL TABLE IF NOT EXISTS paras_fts USING fts5(
  text, heading, section_id UNINDEXED, path UNINDEXED,
  tokenize='porter unicode61'
);
"""

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT,
  case_id TEXT,
  actor TEXT,                   -- agent name or human user
  action TEXT,
  detail TEXT,                  -- JSON
  prev_hash TEXT,
  hash TEXT
);
"""


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    con.executescript(SCHEMA)
    con.executescript(AUDIT_SCHEMA)
    return con


def corpus_stats(con):
    return {
        "documents": con.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "sections": con.execute("SELECT COUNT(*) FROM sections WHERE status='active'").fetchone()[0],
        "paragraphs": con.execute("SELECT COUNT(*) FROM paras").fetchone()[0],
        "sources": [dict(r) for r in con.execute(
            "SELECT doc_id, authority, as_of, fetched_at FROM sources ORDER BY doc_id")],
    }
