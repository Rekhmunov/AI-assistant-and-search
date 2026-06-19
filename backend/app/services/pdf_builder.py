"""Сборка .pdf из структуры DocumentStructure (сохраняет заголовки и абзацы)."""

from __future__ import annotations

import io
from pathlib import Path

from fpdf import FPDF

from app.services.doc_gen_schema import DocumentStructure

LEGAL_DISCLAIMER = (
    "Документ подготовлен на основе общедоступных материалов и сформированных моделью данных. "
    "Он не является результатом юридической консультации и не заменяет помощь квалифицированного специалиста."
)

GLOSIX_FOOTER = "Подготовлено в Glosix"

_FONT_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _font_path() -> str:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return str(path)
    raise RuntimeError("DejaVuSans.ttf not found for PDF export")


class _DocPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("DejaVu", size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"{self.page_no()}", align="C")


def build_pdf_bytes(
    structure: DocumentStructure,
    *,
    show_glosix_footer: bool,
) -> bytes:
    pdf = _DocPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    font = _font_path()
    pdf.add_font("DejaVu", "", font)
    pdf.add_font("DejaVu", "B", font)

    w = pdf.epw  # эффективная ширина страницы
    pdf.set_font("DejaVu", "B", 16)
    pdf.multi_cell(w, 9, structure.title)
    pdf.ln(4)

    for section in structure.sections:
        if section.heading:
            pdf.set_font("DejaVu", "B", 13)
            pdf.ln(3)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, 7, section.heading)
            pdf.ln(1)
        pdf.set_font("DejaVu", "", 11)
        for para in section.paragraphs:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, 6, para)
            pdf.ln(2)

    for table_def in structure.tables:
        if table_def.caption:
            pdf.set_font("DejaVu", "B", 11)
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, 6, table_def.caption)
        if table_def.headers:
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, 6, " | ".join(table_def.headers))
        pdf.set_font("DejaVu", "", 10)
        for row in table_def.rows:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(w, 6, " | ".join(row))
            pdf.ln(2)

    pdf.ln(4)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(w, 5, LEGAL_DISCLAIMER)
    if show_glosix_footer:
        pdf.ln(2)
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(0, 6, GLOSIX_FOOTER, align="C")

    out = pdf.output()
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
