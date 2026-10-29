"""Render a tabular report as CSV or PDF.

Both formats are built from the same `ReportTable`, so an export always has the rows and columns
shown on screen.
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from fpdf import FPDF

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
PDF_MEDIA_TYPE = "application/pdf"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class ReportTable:
    title: str
    columns: list[str]
    rows: list[list[str]]
    filters: dict[str, str] = field(default_factory=dict)
    summary: dict[str, str] = field(default_factory=dict)
    # Relative widths of the PDF columns; equal when empty.
    widths: list[float] = field(default_factory=list)


def export_filename(title: str, generated_at: datetime, extension: str) -> str:
    """`Stock Valuation Report` on 2026-09-07 -> `Stock_Valuation_Report_2026-09-07.pdf`."""
    stem = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return f"{stem}_{generated_at:%Y-%m-%d}.{extension}"


def _safe_csv_cell(value: str) -> str:
    # Spreadsheets run cells that start with these characters as formulas.
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def csv_chunks(table: ReportTable) -> Iterator[str]:
    """Yield the CSV in chunks so a large report is never held as one string."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    # The byte order mark lets Excel read UTF-8 names correctly.
    buffer.write("﻿")
    writer.writerow(table.columns)
    for number, row in enumerate(table.rows, 1):
        writer.writerow([_safe_csv_cell(cell) for cell in row])
        if number % 500 == 0:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
    for label, value in table.summary.items():
        writer.writerow([_safe_csv_cell(label), _safe_csv_cell(value)])
    yield buffer.getvalue()


def _latin1(text: str) -> str:
    # PDF core fonts only cover Latin-1, so anything else prints as "?".
    return text.replace("₹", "Rs ").encode("latin-1", "replace").decode("latin-1")


class _ReportPdf(FPDF):
    def __init__(self, table: ReportTable, generated_at: datetime) -> None:
        super().__init__(orientation="L", unit="mm", format="A4")
        self.table_title = _latin1(table.title)
        self.set_auto_page_break(auto=True, margin=15)
        self.set_title(table.title)
        self.set_creator("ESIMS")

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.cell(0, 6, f"{self.table_title} - page {self.page_no()}/{{nb}}", align="C")


def pdf_bytes(table: ReportTable, generated_at: datetime) -> bytes:
    """Build the PDF: title, generation time and filters on top, then the table."""
    pdf = _ReportPdf(table, generated_at)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _latin1(table.title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        0,
        6,
        f"Generated: {generated_at:%Y-%m-%d %H:%M:%S} UTC",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    filters = ", ".join(f"{name}: {value}" for name, value in table.filters.items())
    pdf.cell(0, 6, _latin1(f"Filters: {filters or 'None'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    weights = table.widths or [1.0] * len(table.columns)
    scale = pdf.epw / sum(weights)
    widths = [weight * scale for weight in weights]
    line_height = 5.5

    def draw_header() -> None:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for name, width in zip(table.columns, widths, strict=True):
            pdf.cell(width, 7, _latin1(name), border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", size=8)

    draw_header()
    for row in table.rows:
        texts = [_latin1(cell) for cell in row]
        wrapped = [
            pdf.multi_cell(width, line_height, text, dry_run=True, output="LINES")
            for text, width in zip(texts, widths, strict=True)
        ]
        height = max(len(lines) for lines in wrapped) * line_height
        if pdf.will_page_break(height):
            pdf.add_page()
            draw_header()
        x, y = pdf.get_x(), pdf.get_y()
        for lines, width in zip(wrapped, widths, strict=True):
            pdf.rect(x, y, width, height)
            pdf.set_xy(x, y)
            pdf.multi_cell(width, line_height, "\n".join(lines), new_x="RIGHT", new_y="TOP")
            x += width
        pdf.set_xy(pdf.l_margin, y + height)
    if not table.rows:
        pdf.cell(0, 7, "No data for the selected filters.", border=1)
        pdf.ln()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    for label, value in table.summary.items():
        pdf.cell(0, 6, _latin1(f"{label}: {value}"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
