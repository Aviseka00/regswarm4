"""Parse eCFR 'full' XML into sections and label-path paragraphs.

eCFR XML nests the hierarchy as DIVn elements; a regulation section is the
element with TYPE="SECTION" (usually DIV8) whose N attribute looks like
"§ 211.22". Paragraph text lives in <P> children that begin with markers such
as "(a)", "(1)", "(i)", "(A)". We reconstruct the label path (e.g. c/10/iv) so
citations can be verified at paragraph level.

Standard library only.
"""
import re
import xml.etree.ElementTree as ET

ROMAN = re.compile(r"^(?=[ivxl]+$)(?:xl|l?x{0,3})(?:ix|iv|v?i{0,3})$")
LEAD = re.compile(r"^\s*((?:\([A-Za-z0-9]{1,5}\)\s*)+)")
MARK = re.compile(r"\(([A-Za-z0-9]{1,5})\)")


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _cls(m):
    if m.isdigit():
        return "d"
    if m.isupper():
        return "U"
    return "l"


def _level_of(marker, stack):
    """Hierarchy level: 0=(a) 1=(1) 2=(i) 3=(A) 4=(1)-italic.

    Disambiguates letter vs roman numeral using the open stack: a single letter
    that is the successor of the top-level marker continues level 0
    ((h) then (i)); otherwise a roman numeral nests under a numbered paragraph.
    """
    c = _cls(marker)
    if c == "d":
        return 4 if len(stack) >= 4 and _cls(stack[3]) == "U" else 1
    if c == "U":
        return 3
    if not ROMAN.match(marker):
        return 0
    if not stack:
        return 0
    if len(marker) == 1 and len(stack[0]) == 1 and ord(marker) == ord(stack[0]) + 1:
        return 0
    return 2 if len(stack) >= 2 else 0


def split_markers(text):
    m = LEAD.match(text)
    if not m:
        return [], text
    marks = MARK.findall(m.group(1))
    return marks, text[m.end():].strip()


def parse_section(sec_el):
    """Return dict(section, heading, status, cita, paras[list of (path,text)])."""
    n = sec_el.get("N", "").replace("§", "").strip()
    head_el = sec_el.find("HEAD")
    heading = _text(head_el) if head_el is not None else ""
    heading = re.sub(r"^§+\s*[\d.a-zA-Z\-–]+\s*", "", heading).strip()

    paras, cita = [], ""
    stack = []
    for child in list(sec_el):
        tag = child.tag
        if tag == "HEAD":
            continue
        if tag in ("CITA", "SECAUTH", "EDNOTE"):
            cita = (cita + " " + _text(child)).strip()
            continue
        if tag in ("P", "FP", "EXTRACT", "GPOTABLE", "TABLE", "NOTE", "EXAMPLE"):
            full = _text(child)
            if not full:
                continue
            marks, rest = split_markers(full)
            if marks and tag == "P":
                for mk in marks:
                    lvl = _level_of(mk, stack)
                    stack = stack[:min(lvl, len(stack))] + [mk]
                path = "/".join(stack)
            else:
                path = "/".join(stack) if stack and tag != "P" else (
                    "/".join(stack) if stack else "")
            paras.append((path, full))
    status = "active"
    body = " ".join(t for _, t in paras)
    if (not paras) or re.fullmatch(r"\s*\[Reserved\]\s*", body or "[Reserved]"):
        status = "reserved"
    if "[Reserved]" in heading or re.search(r"\[Reserved\]", n):
        status = "reserved"
    return {"section": n, "heading": heading, "status": status, "cita": cita, "paras": paras}


def parse_xml(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if el.get("TYPE") == "SECTION":
            s = parse_section(el)
            if s["section"]:
                out.append(s)
    return out
