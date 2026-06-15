"""Сборка .xlsx из структуры DocumentStructure."""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Font

from app.services.doc_gen_schema import DocumentStructure


def build_report_xlsx_bytes(headers: list[str], rows: list[list[str]], sheet_name: str = "Отчёт") -> bytes:
    """
    Упрощённый builder для табличных отчётов — без заголовка документа и подписи таблицы.
    Первая строка = жирные заголовки столбцов, далее данные.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)

    for row_idx, row in enumerate(rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_xlsx_bytes(structure: DocumentStructure) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = (structure.title or "Документ")[:31]

    row = 1
    title_cell = ws.cell(row=row, column=1, value=structure.title or "Документ")
    title_cell.font = Font(bold=True, size=14)
    row += 2

    for section in structure.sections:
        if section.heading:
            heading_cell = ws.cell(row=row, column=1, value=section.heading)
            heading_cell.font = Font(bold=True)
            row += 1
        for para in section.paragraphs:
            if para.strip():
                ws.cell(row=row, column=1, value=para.strip())
                row += 1
        row += 1

    for table_def in structure.tables:
        if table_def.caption:
            cap_cell = ws.cell(row=row, column=1, value=table_def.caption)
            cap_cell.font = Font(bold=True)
            row += 1
        col_count = max(len(table_def.headers), max((len(r) for r in table_def.rows), default=0))
        if col_count < 1:
            continue
        for col_idx in range(col_count):
            header = table_def.headers[col_idx] if col_idx < len(table_def.headers) else ""
            cell = ws.cell(row=row, column=col_idx + 1, value=header)
            cell.font = Font(bold=True)
        row += 1
        for table_row in table_def.rows:
            for col_idx in range(col_count):
                value = table_row[col_idx] if col_idx < len(table_row) else ""
                ws.cell(row=row, column=col_idx + 1, value=value)
            row += 1
        row += 2

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
