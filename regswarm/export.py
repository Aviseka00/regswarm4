"""Export the response as a Word (.docx) file using only the standard library
(a .docx is a zip of small XML parts)."""
import io
import zipfile
from xml.sax.saxutils import escape

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="200"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:color w:val="1F2A8C"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="1F2A8C"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="480"/></w:pPr><w:rPr><w:i/><w:color w:val="555555"/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Banner"><w:name w:val="Banner"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="B00020"/><w:sz w:val="19"/></w:rPr></w:style>
</w:styles>"""


def _p(text, style=None, bold=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def build_docx(doc, signature=None, corpus_note=""):
    body = []
    if doc.get("synthetic"):
        body.append(_p("SYNTHETIC DEMONSTRATION - not a real submission. Site data and observation are invented.", "Banner"))
    status = "APPROVED - LOCKED" if signature and signature.get("doc_sha256") else "DRAFT - NOT APPROVED - HUMAN REVIEW REQUIRED BEFORE USE"
    body.append(_p(doc["title"], "Title"))
    body.append(_p(f"Case {doc['case_id']} · Version {doc['version']} · {status}", "Banner"))
    body.append(_p("Observation", "Heading1"))
    for para in doc["observation"].split("\n\n"):
        body.append(_p(para))
    refs = []
    for s in doc["sections"]:
        body.append(_p(s["title"], "Heading1"))
        for cl in s["claims"]:
            tag = {"regulatory": "[regulatory] ", "site_fact": "[site record] ", "action": "[commitment - to be confirmed] "}.get(cl.get("kind"), "")
            body.append(_p(tag + cl["text"]))
            for ct in cl.get("cites", []):
                q = f' "{ct["quote"]}"' if ct.get("quote") else ""
                body.append(_p(f"{ct['ref']}{q}", "Quote"))
                if ct["ref"] not in refs:
                    refs.append(ct["ref"])
            if cl.get("evidence"):
                body.append(_p("Evidence: " + ", ".join(cl["evidence"][:6]) + (" ..." if len(cl["evidence"]) > 6 else ""), "Quote"))
    body.append(_p("Citations verified against the regulatory corpus", "Heading1"))
    if corpus_note:
        body.append(_p(corpus_note))
    body.append(_p("; ".join(refs)))
    body.append(_p("Approval", "Heading1"))
    if signature and signature.get("doc_sha256"):
        body.append(_p(f"{signature['meaning']} by {signature['name']} on {signature['timestamp']}"))
        body.append(_p(f"Document SHA-256: {signature['doc_sha256']}"))
        if signature.get("comment"):
            body.append(_p(f"Reviewer comment: {signature['comment']}"))
    else:
        body.append(_p("Not yet approved. This draft is decision support only; a qualified QA head must review, edit and approve it."))
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>'
                + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1200" w:right="1200" w:bottom="1200" w:left="1200"/></w:sectPr></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
    return buf.getvalue()
