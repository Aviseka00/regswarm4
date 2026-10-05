"""Hybrid-ready retrieval over the corpus. MVP uses SQLite FTS5 (BM25) at
paragraph level, then rolls hits up to sections. Exact clause lookup is by
reference. Standard library only."""
import re

STOP = set("""a an and are as at be been by for from has have in into is it its of on or that the
their there these this those to was were which with within shall such any all not no per etc
during while under over than then also only other more most may can could should would""".split())


def _fts_query(text):
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower()) if w not in STOP]
    seen, out = set(), []
    for w in words:
        w = w.replace("-", " ")
        if w not in seen:
            seen.add(w)
            out.append(f'"{w}"')
    return " OR ".join(out)


def search(con, query, k=6, doc_prefix=None):
    """Return the top-k sections (best paragraph per section) for a free-text query."""
    q = _fts_query(query)
    if not q:
        return []
    sql = """
      SELECT p.section_id, p.path, p.text, s.heading, s.as_of, s.url,
             bm25(paras_fts, 1.0, 0.4) AS rank
      FROM paras_fts JOIN paras p ON p.rowid = paras_fts.rowid
      JOIN sections s ON s.id = p.section_id
      WHERE paras_fts MATCH ? AND s.status='active' {flt}
      ORDER BY rank LIMIT 60"""
    flt, args = "", [q]
    if doc_prefix:
        flt, args = "AND s.id LIKE ?", [q, doc_prefix + "%"]
    rows = con.execute(sql.format(flt=flt), args).fetchall()
    best, order = {}, []
    for r in rows:
        if r["section_id"] not in best:
            best[r["section_id"]] = r
            order.append(r["section_id"])
    hits = []
    for sid in order[:k]:
        r = best[sid]
        shown = "".join(f"({x})" for x in r["path"].split("/")) if r["path"] else ""
        hits.append({
            "ref": f"{sid}{shown}", "section_id": sid, "path": r["path"], "heading": r["heading"],
            "snippet": r["text"][:420], "text": r["text"][:1500], "score": round(-r["rank"], 2),
            "as_of": r["as_of"], "url": r["url"],
        })
    return hits


def lookup(con, ref):
    """Exact lookup by reference; returns the same shape as a search hit or None."""
    from .verifier import parse_ref, _path_text
    p = parse_ref(ref)
    if not p:
        return None
    sid, path = p
    s = con.execute("SELECT * FROM sections WHERE id=?", (sid,)).fetchone()
    if not s or s["status"] != "active":
        return None
    txt = _path_text(con, sid, path)
    if not txt:
        return None
    shown = "".join(f"({x})" for x in path.split("/")) if path else ""
    return {"ref": f"{sid}{shown}", "section_id": sid, "path": path, "heading": s["heading"],
            "snippet": txt[:420], "text": txt[:1500], "score": None, "as_of": s["as_of"], "url": s["url"]}
