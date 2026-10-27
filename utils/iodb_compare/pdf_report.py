"""A4 PDF report for an IODB comparison result (reportlab platypus; real document, not a screen print)."""
from __future__ import annotations

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

KINDS = ("summary", "detailed", "complete")
NAVY = colors.HexColor("#1f3a5f")
GREY = colors.HexColor("#f2f4f7")
LINE = colors.HexColor("#b8c0cc")
RED = colors.HexColor("#9b1c1c")
GREEN = colors.HexColor("#166534")
AMBER = colors.HexColor("#92400e")

_FONT, _FONT_B = "Helvetica", "Helvetica-Bold"
_UNICODE = False


def _register_fonts():
    """Use DejaVu (full Latin/Cyrillic coverage) when the host has it; otherwise Helvetica."""
    global _FONT, _FONT_B, _UNICODE
    if _UNICODE:
        return
    cands = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for reg, bold in cands:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("IEZ", reg))
                pdfmetrics.registerFont(TTFont("IEZ-B", bold))
                _FONT, _FONT_B, _UNICODE = "IEZ", "IEZ-B", True
                return
            except Exception:
                continue


def _plain(s: str) -> str:
    return s if _UNICODE else s.encode("latin-1", "replace").decode("latin-1")


def _t(v) -> str:
    """Safe paragraph text: XML-escaped; characters Helvetica cannot draw become '?' (never crash)."""
    s = "" if v is None else str(v)
    if not _UNICODE:
        s = s.encode("latin-1", "replace").decode("latin-1")
    return escape(s)


class _NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so the footer can say 'Page X of Y'."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._footer(total)
            super().showPage()
        super().save()

    def _footer(self, total):
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        self.setFont(_FONT, 8)
        self.setFillColor(colors.HexColor("#444444"))
        self.drawString(18 * mm, 9.5 * mm, "iEZ – IODB Comparison & Revision Report" if _UNICODE else "iEZ - IODB Comparison & Revision Report")
        self.drawRightString(A4[0] - 18 * mm, 9.5 * mm, f"Page {self._pageNumber} of {total}")


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["Normal"], fontName=_FONT, fontSize=9, leading=12, alignment=TA_LEFT)
    return {
        "body": base,
        "small": ParagraphStyle("s", parent=base, fontSize=8, leading=10),
        "cell": ParagraphStyle("c", parent=base, fontSize=8, leading=10, splitLongWords=1),
        "cellb": ParagraphStyle("cb", parent=base, fontName=_FONT_B, fontSize=8, leading=10, textColor=colors.white),
        "h1": ParagraphStyle("h1", parent=base, fontName=_FONT_B, fontSize=13, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName=_FONT_B, fontSize=10.5, leading=13, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName=_FONT_B, fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=2),
        "title": ParagraphStyle("t", parent=base, fontName=_FONT_B, fontSize=18, leading=22, textColor=NAVY),
        "brand": ParagraphStyle("br", parent=base, fontName=_FONT_B, fontSize=11, textColor=colors.HexColor("#555555")),
        "banner": ParagraphStyle("bn", parent=base, fontName=_FONT_B, fontSize=11, leading=14, textColor=RED),
    }


def _table(data, widths, st, *, zebra=True, extra=None):
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GREY]))
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def _P(text, st, style="cell"):
    return Paragraph(_t(text), st[style])


def _head(cols, st):
    return [Paragraph(_t(c), st["cellb"]) for c in cols]


def _kv_table(rows, st, widths=(62 * mm, 100 * mm)):
    t = Table([[Paragraph(f"<b>{_t(k)}</b>", st["body"]), Paragraph(_t(v), st["body"])] for k, v in rows], colWidths=widths)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


# ------------------------------------------------------------- sections ----
def _cover(r, st, user, project):
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    out = [Paragraph("iEZ", st["brand"]), Spacer(1, 2 * mm),
           Paragraph("IODB COMPARISON &amp; REVISION REPORT", st["title"]), Spacer(1, 4 * mm)]
    rows = [("Project", project or "-"), ("IODB 1 (older / reference)", r["file1"]["name"]),
            ("IODB 2 (newer / current)", r["file2"]["name"]), ("Comparison date", now), ("Generated by", user or "-")]
    out += [_kv_table(rows, st), Spacer(1, 4 * mm)]
    return out


def _summary(r, st, num="1"):
    c, t = r["counts"], r["totals"]
    out = [Paragraph(f"{num}. SUMMARY", st["h1"])]
    if r["totally_different"]:
        out += [Paragraph("IODB DATASETS ARE TOTALLY DIFFERENT", st["banner"]), Spacer(1, 2 * mm),
                _kv_table([("IODB 1 Total Instruments", t["iodb1"]), ("IODB 2 Total Instruments", t["iodb2"]),
                           ("Common TAG NOs", 0)], st),
                Spacer(1, 2 * mm),
                Paragraph(_t("No common instrument TAGs were identified between the two uploaded IODB files. Therefore, the "
                             "files cannot be treated as revisions of the same IODB dataset."), st["body"]),
                Spacer(1, 2 * mm),
                _kv_table([("Instruments only in IODB 2 (listed as added)", c["added"]),
                           ("Instruments only in IODB 1 (listed as deleted)", c["deleted"])], st)]
        return out
    out.append(Paragraph(_t(f"The comparison between {r['file1']['name']} and {r['file2']['name']} identified the following changes:"),
                         st["body"]))
    out.append(Spacer(1, 2 * mm))
    out.append(_kv_table([("Total instruments – IODB 1", t["iodb1"]), ("Total instruments – IODB 2", t["iodb2"]),
                          ("Added instruments", c["added"]), ("Deleted instruments", c["deleted"]),
                          ("Modified instruments", c["modified"]), ("Unchanged instruments", c["unchanged"]),
                          ("Total common instruments", t["common"]), ("Total field-level changes", t["field_changes"])]
                         + ([("Duplicate TAGs needing review", c["review"])] if c["review"] else []), st))
    out += [Spacer(1, 3 * mm), Paragraph(_t(r["summary_text"]), st["body"])]
    return out


def _tag_rows(items, st, with_area=True):
    head = ["TAG NO", "Instrument Type", "P&ID NO.", "Service"] + (["Area"] if with_area else []) + ["Status"]
    data = [_head(head, st)]
    for it in items:
        row = [it["shown_tag"] or it["tag"], it["type"], it["pid"], it["service"]] + ([it["area"]] if with_area else []) + [it["status"]]
        data.append([_P(v, st) for v in row])
    return data


def _list_table(items, st, status_label, with_area=True):
    if not items:
        return [Paragraph("None.", st["body"])]
    data = _tag_rows(items, st, with_area)
    n = len(data[0])
    w = [34, 40, 30, 36, 24, 18][:n] if with_area else [36, 48, 36, 44, 18]
    scale = (A4[0] - 36 * mm) / (sum(w) * mm)
    t = _table(data, [x * mm * scale for x in w], st)
    return [t]


def _comparison_result(r, st, include_unchanged=True):
    rec = r["records"]
    out = [Paragraph("2. COMPARISON RESULT", st["h1"])]
    if r["totally_different"]:
        out.append(Paragraph(_t("The files share no TAG NO; the lists below are the contents of each file, not revision changes."),
                             st["small"]))
    out.append(Paragraph(f"2.1 Added Instruments ({len(rec['added'])})", st["h2"]))
    out += _list_table(rec["added"], st, "ADDED")
    out.append(Paragraph(f"2.2 Deleted Instruments ({len(rec['deleted'])})", st["h2"]))
    out += _list_table(rec["deleted"], st, "DELETED")
    out.append(Paragraph(f"2.3 Modified Instruments ({len(rec['modified'])})", st["h2"]))
    if rec["modified"]:
        data = [_head(["TAG NO", "P&ID NO.", "Instrument Type", "Changed Fields"], st)]
        for it in rec["modified"]:
            names = ", ".join(dict.fromkeys(ch["column"] for ch in it["changes"]))
            data.append([_P(it["shown_tag"] or it["tag"], st), _P(it["pid"], st), _P(it["type"], st),
                         _P(f"{it['n_changes']}: {names}", st)])
        w = [32, 28, 36, 74]
        scale = (A4[0] - 36 * mm) / (sum(w) * mm)
        out.append(_table(data, [x * mm * scale for x in w], st))
    else:
        out.append(Paragraph("None.", st["body"]))
    if include_unchanged:
        out.append(Paragraph(f"2.4 Unchanged Instruments ({len(rec['unchanged'])})", st["h2"]))
        out += _list_table(rec["unchanged"], st, "UNCHANGED")
    if rec["review"]:
        out.append(Paragraph(f"2.5 Needs Review – Duplicate TAG NO ({len(rec['review'])})", st["h2"]))
        data = [_head(["TAG NO", "Times in IODB 1", "Times in IODB 2", "Instrument Type", "P&ID NO."], st)]
        for it in rec["review"]:
            data.append([_P(it["shown_tag"] or it["tag"], st), _P(it["count_1"], st), _P(it["count_2"], st),
                         _P(it["type"], st), _P(it["pid"], st)])
        w = [40, 24, 24, 44, 38]
        scale = (A4[0] - 36 * mm) / (sum(w) * mm)
        out.append(_table(data, [x * mm * scale for x in w], st))
    return out


def _field_changes(r, st):
    out = [Paragraph("3. FIELD-LEVEL CHANGES", st["h1"])]
    mods = r["records"]["modified"]
    if not mods:
        return out + [Paragraph("No field-level changes were identified.", st["body"])]
    cat = {c["code"]: c["name"] for c in r["category_counts"]}
    w = [44, 38, 44, 44]
    scale = (A4[0] - 36 * mm) / (sum(w) * mm)
    for it in mods:
        title = Paragraph(f"TAG NO: {_t(it['shown_tag'] or it['tag'])} &nbsp;&nbsp; Status: MODIFIED – {it['n_changes']} "
                          f"change{'s' if it['n_changes'] != 1 else ''}", st["h3"])
        data = [_head(["Field", "Category", "IODB 1 (OLD VALUE)", "IODB 2 (NEW VALUE)"], st)]
        for ch in it["changes"]:
            data.append([_P(ch["column"], st), _P(cat.get(ch["category"], ""), st),
                         _P(ch["old"] if ch["old"] != "" else "(empty)", st), _P(ch["new"] if ch["new"] != "" else "(empty)", st)])
        tbl = _table(data, [x * mm * scale for x in w], st)
        # keep the heading with at least the first rows of its table
        out.append(KeepTogether([title, tbl]) if len(data) <= 14 else title)
        if len(data) > 14:
            out.append(tbl)
        out.append(Spacer(1, 2 * mm))
    return out


def _chart(rows):
    rows = [x for x in rows if x["count"] > 0]
    if not rows:
        return None
    h = 18 * mm + 7 * mm * len(rows)
    d = Drawing(A4[0] - 36 * mm, h)
    ch = HorizontalBarChart()
    ch.x, ch.y, ch.width, ch.height = 62 * mm, 8 * mm, 85 * mm, h - 14 * mm
    ch.data = [[x["count"] for x in reversed(rows)]]
    ch.categoryAxis.categoryNames = [f"{x['code']} {x['name'] if len(x['name']) <= 30 else x['name'][:28] + '..'}" for x in reversed(rows)]
    ch.categoryAxis.labels.fontName = _FONT
    ch.categoryAxis.labels.fontSize = 7
    ch.categoryAxis.labels.dx = -2
    ch.valueAxis.valueMin = 0
    ch.valueAxis.labels.fontName = _FONT
    ch.valueAxis.labels.fontSize = 7
    ch.bars[0].fillColor = NAVY
    ch.barLabelFormat = "%d"
    ch.barLabels.fontName = _FONT
    ch.barLabels.fontSize = 7
    ch.barLabels.nudge = 7
    ch.barWidth = 6
    d.add(ch)
    return d


def _categories(r, st, num="4"):
    out = [Paragraph(f"{num}. ENGINEERING CHANGE CATEGORY SUMMARY", st["h1"])]
    rows = r["category_counts"]
    data = [_head(["Code", "Category", "Field-level changes"], st)]
    for x in rows:
        data.append([_P(x["code"], st), _P(x["name"], st), _P(x["count"], st)])
    data.append([_P("", st), Paragraph(f"<b>Total</b>", st["cell"]), Paragraph(f"<b>{r['totals']['field_changes']}</b>", st["cell"])])
    out.append(_table(data, [18 * mm, 110 * mm, 36 * mm], st))
    ch = _chart(rows)
    if ch is not None:
        out += [Spacer(1, 4 * mm), ch]
    top = r["field_counts"][:10]
    if top:
        out.append(Paragraph("Most frequently changed fields", st["h2"]))
        data = [_head(["Field", "Instruments changed"], st)] + [[_P(x["column"], st), _P(x["count"], st)] for x in top]
        out.append(_table(data, [120 * mm, 44 * mm], st))
    return out


def _validation(r, st, num="5"):
    out = [Paragraph(f"{num}. VALIDATION &amp; WARNINGS", st["h1"])]
    d1, d2 = r["duplicates"]["iodb1"], r["duplicates"]["iodb2"]

    def dup_text(d):
        return "None" if not d else "; ".join(f"{t} ({n} times)" for t, n in list(d.items())[:40]) + \
            (f" ... and {len(d) - 40} more" if len(d) > 40 else "")
    rows = [("Duplicate TAGs – IODB 1", dup_text(d1)), ("Duplicate TAGs – IODB 2", dup_text(d2)),
            ("Missing TAG NO – IODB 1", f"{r['missing_tag']['iodb1']} record(s)" if r["missing_tag"]["iodb1"] else "None"),
            ("Missing TAG NO – IODB 2", f"{r['missing_tag']['iodb2']} record(s)" if r["missing_tag"]["iodb2"] else "None"),
            ("Common TAGs", r["totals"]["common"]), ("IODB 1 records", r["totals"]["iodb1"]),
            ("IODB 2 records", r["totals"]["iodb2"]), ("Columns compared", len(r["compared_columns"])),
            ("Case differences", "ignored" if r["options"]["ignore_case"] else "reported"),
            ("Treated as empty", "blank, '-', 'N/A', 'NIL' (equivalent empty values)"),
            ("Ignored columns", ", ".join(r["options"]["ignored_columns"]) + " (sorting artefact, not an engineering value)")]
    out.append(_kv_table(rows, st))
    others = [w for w in r["warnings"] if w["code"] not in ("DUPLICATE_TAG",)]
    if others:
        out.append(Paragraph("Notes", st["h2"]))
        for w in others:
            out.append(Paragraph("• " + _t(w["message"]), st["body"]))
    return out


# ----------------------------------------------------------------- build ----
def build_pdf(result: dict, kind: str = "complete", *, user: str = "", project: str = "") -> bytes:
    if kind not in KINDS:
        raise ValueError(f"Unknown report kind: {kind}")
    _register_fonts()
    st = _styles()
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                          title="IODB Comparison & Revision Report", author=user or "iEZ")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)

    def header(canv, _doc):
        if canv.getPageNumber() > 1:
            canv.setFont(_FONT_B, 8)
            canv.setFillColor(NAVY)
            canv.drawString(18 * mm, A4[1] - 12 * mm, "iEZ")
            canv.setFont(_FONT, 8)
            canv.setFillColor(colors.HexColor("#444444"))
            canv.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm,
                                 _plain(f"{result['file1']['name']}  vs  {result['file2']['name']}"[:110]))
            canv.setStrokeColor(LINE)
            canv.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)

    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=header)])

    story = _cover(result, st, user, project) + _summary(result, st)
    if kind == "summary":
        story += [Spacer(1, 2 * mm)] + _categories(result, st, "2") + _validation(result, st, "3")
    elif kind == "detailed":
        story += [PageBreak()] + _comparison_result(result, st) + [PageBreak()] + _field_changes(result, st) \
                 + [PageBreak()] + _validation(result, st, "4")
    else:
        story += [PageBreak()] + _comparison_result(result, st) + [PageBreak()] + _field_changes(result, st) \
                 + [PageBreak()] + _categories(result, st) + _validation(result, st)
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()
