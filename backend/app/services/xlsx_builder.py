"""Сборка .xlsx из структуры DocumentStructure."""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.services.doc_gen_schema import DocumentStructure

# ─────────────────────────────────────────────────────────────────────────────
# Цвета для секторов диаграммы
# ─────────────────────────────────────────────────────────────────────────────
_PIE_COLORS = [
    "4472C4", "ED7D31", "A9D18E", "FF0000", "FFC000",
    "9DC3E6", "F4B183", "C9E0B3", "FF7070", "FFE070",
    "5B9BD5", "E06C3A", "70AD47", "D94040", "FFA400",
    "2E75B6", "C55A11", "538135", "C00000", "FF8C00",
]


def build_secretary_report_xlsx(
    records: list[dict],
    period_label: str,
) -> bytes:
    """
    Формирует Excel-отчёт агента «Учёт затрат»:
    - Таблица данных (Дата / Категория / Сумма / Примечание)
    - Круговая диаграмма по категориям правее таблицы
    - Список категорий с итогами правее диаграммы
    """
    # openpyxl chart imports are done inline where used below

    wb = Workbook()
    ws = wb.active
    ws.title = (period_label or "Отчёт")[:31]

    # ── Агрегация по категориям ───────────────────────────────────────────────
    totals: dict[str, int] = defaultdict(int)
    for r in records:
        cat = str(r.get("category") or "Прочие")
        try:
            totals[cat] += int(r.get("amount") or 0)
        except (TypeError, ValueError):
            pass
    cats_sorted = sorted(totals.items(), key=lambda x: -x[1])
    total_all = sum(v for _, v in cats_sorted) or 1

    # ── Стили ─────────────────────────────────────────────────────────────────
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="2E75B6")
    border_thin = Border(
        left=Side(style="thin", color="D0D0D0"),
        right=Side(style="thin", color="D0D0D0"),
        top=Side(style="thin", color="D0D0D0"),
        bottom=Side(style="thin", color="D0D0D0"),
    )
    center = Alignment(horizontal="center", vertical="center")

    def _hdr(ws, row, col, val):
        c = ws.cell(row=row, column=col, value=val)
        c.font = header_font
        c.fill = header_fill
        c.border = border_thin
        c.alignment = center
        return c

    def _cell(ws, row, col, val, bold=False, align="left", num_format=None):
        c = ws.cell(row=row, column=col, value=val)
        c.font = Font(bold=bold, size=10)
        c.border = border_thin
        c.alignment = Alignment(horizontal=align, vertical="center")
        if num_format:
            c.number_format = num_format
        return c

    # ── 1. Таблица данных (A–D) ───────────────────────────────────────────────
    ROW_HDR = 1
    _hdr(ws, ROW_HDR, 1, "Дата")
    _hdr(ws, ROW_HDR, 2, "Категория")
    _hdr(ws, ROW_HDR, 3, "Сумма")
    _hdr(ws, ROW_HDR, 4, "Примечание")

    for i, r in enumerate(records, 2):
        raw_at = r.get("at", "")
        try:
            at_fmt = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00")).strftime("%d.%m.%Y")
        except Exception:
            at_fmt = str(raw_at)[:10]
        _cell(ws, i, 1, at_fmt, align="center")
        _cell(ws, i, 2, str(r.get("category") or ""))
        try:
            amount_val = int(r.get("amount") or 0)
        except (TypeError, ValueError):
            amount_val = 0
        _cell(ws, i, 3, amount_val, align="right", num_format='# ##0')
        _cell(ws, i, 4, str(r.get("note") or ""))

    data_end_row = max(len(records) + 1, ROW_HDR + 1)

    # Ширина столбцов таблицы
    ws.column_dimensions["A"].width = 13
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 22

    # ── 2. Данные для диаграммы (F–G) ────────────────────────────────────────
    # Эти ячейки питают PieChart; они видимы и служат частью макета.
    CHART_DATA_COL_CAT = 6   # F
    CHART_DATA_COL_AMT = 7   # G
    _hdr(ws, ROW_HDR, CHART_DATA_COL_CAT, "Категория")
    _hdr(ws, ROW_HDR, CHART_DATA_COL_AMT, "Итого")

    for i, (cat, total) in enumerate(cats_sorted, 2):
        _cell(ws, i, CHART_DATA_COL_CAT, cat)
        _cell(ws, i, CHART_DATA_COL_AMT, total, align="right", num_format='# ##0')

    chart_data_end_row = max(len(cats_sorted) + 1, ROW_HDR + 1)
    ws.column_dimensions["F"].width = 25
    ws.column_dimensions["G"].width = 12

    # ── 3. Горизонтальная столбчатая диаграмма (якорь H1) ────────────────────
    # BarChart вместо PieChart: категории на оси Y не накладываются,
    # текст всегда читаем независимо от количества категорий.
    if cats_sorted:
        from openpyxl.chart import BarChart, Reference
        from openpyxl.chart.series import DataPoint
        from openpyxl.chart.label import DataLabelList

        bar = BarChart()
        bar.type = "bar"          # горизонтальные полосы
        bar.grouping = "clustered"
        bar.title = f"Затраты по категориям — {period_label}"
        bar.style = 10
        bar.width  = 16           # cm — достаточно для подписей
        bar.height = max(8, min(len(cats_sorted) * 1.2 + 2, 18))  # высота под кол-во категорий

        # Данные берём из уже заполненных ячеек F–G (cat, amount)
        # Порядок: самая большая категория — вверху (cats_sorted уже отсортирован desc)
        data_ref = Reference(
            ws,
            min_col=CHART_DATA_COL_AMT,
            min_row=ROW_HDR,
            max_row=chart_data_end_row,
        )
        cats_ref = Reference(
            ws,
            min_col=CHART_DATA_COL_CAT,
            min_row=ROW_HDR + 1,
            max_row=chart_data_end_row,
        )
        bar.add_data(data_ref, titles_from_data=True)
        bar.set_categories(cats_ref)

        # Подписи значений на полосах — только сумма, без переполнения
        dlbls = DataLabelList()
        dlbls.showVal = True
        dlbls.showCatName = False
        dlbls.showPercent = False
        dlbls.showLegendKey = False
        bar.series[0].dLbls = dlbls

        # Цвет всех полос — единый фирменный (проще и не перегружает восприятие)
        bar.series[0].graphicalProperties.solidFill = "2E75B6"
        bar.series[0].graphicalProperties.line.solidFill = "1A4F82"

        # Убираем легенду серий — она не нужна для одной серии
        bar.legend = None

        # Подписи осей
        bar.y_axis.title = "Категория"
        bar.x_axis.title = "Сумма (руб.)"
        bar.x_axis.numFmt = '# ##0'

        ws.add_chart(bar, "H1")

    # ── 4. Итоговая таблица правее диаграммы (P–R) ───────────────────────────
    # Диаграмма ~16 см ≈ 8 столбцов → якорь H + 8 = P (col 16)
    LEGEND_COL_CAT = 16   # P
    LEGEND_COL_AMT = 17   # Q
    LEGEND_COL_PCT = 18   # R

    _hdr(ws, ROW_HDR, LEGEND_COL_CAT, "Категория")
    _hdr(ws, ROW_HDR, LEGEND_COL_AMT, "Сумма")
    _hdr(ws, ROW_HDR, LEGEND_COL_PCT, "%")

    for i, (cat, total) in enumerate(cats_sorted, 2):
        color_hex = _PIE_COLORS[(i - 2) % len(_PIE_COLORS)]
        cat_cell = _cell(ws, i, LEGEND_COL_CAT, cat)
        cat_cell.fill = PatternFill("solid", fgColor=color_hex)
        cat_cell.font = Font(color="FFFFFF", bold=True, size=10)
        _cell(ws, i, LEGEND_COL_AMT, total, align="right", num_format='# ##0')
        pct = round(total / total_all * 100, 1)
        _cell(ws, i, LEGEND_COL_PCT, f"{pct}%", align="center")

    # Итого
    if cats_sorted:
        total_row = len(cats_sorted) + 2
        c = ws.cell(row=total_row, column=LEGEND_COL_CAT, value="ИТОГО")
        c.fill = PatternFill("solid", fgColor="2E75B6")
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.border = border_thin
        amt_c = ws.cell(row=total_row, column=LEGEND_COL_AMT, value=total_all)
        amt_c.font = Font(bold=True, size=10)
        amt_c.border = border_thin
        amt_c.number_format = '# ##0'
        amt_c.alignment = Alignment(horizontal="right")
        pct_c = ws.cell(row=total_row, column=LEGEND_COL_PCT, value="100%")
        pct_c.border = border_thin
        pct_c.font = Font(bold=True, size=10)
        pct_c.alignment = Alignment(horizontal="center")

    ws.column_dimensions[get_column_letter(LEGEND_COL_CAT)].width = 25
    ws.column_dimensions[get_column_letter(LEGEND_COL_AMT)].width = 12
    ws.column_dimensions[get_column_letter(LEGEND_COL_PCT)].width = 8

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
