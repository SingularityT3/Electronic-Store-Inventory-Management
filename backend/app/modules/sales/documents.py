"""Shared immutable invoice and credit note document rendering."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from fpdf import FPDF


@dataclass(frozen=True)
class Document:
    kind: Literal["invoice", "credit_note"]
    content: dict[str, Any]
    annotation: str | None = None


def _latin1(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("₹", "Rs ")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


class _DocumentPdf(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.cell(0, 6, f"Page {self.page_no()}/{{nb}}", align="C")


def document_pdf(document: Document) -> bytes:
    """Render a stored document snapshot as an A4 portrait PDF."""
    data = document.content
    pdf = _DocumentPdf(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.alias_nb_pages()
    issued = data.get("issued_at") or data.get("created_at")
    if issued:
        parsed = datetime.fromisoformat(str(issued).replace("Z", "+00:00"))
        pdf.set_creation_date(parsed)
    pdf.set_title(_latin1(data.get("invoice_label") or data.get("credit_note_number")))
    pdf.set_creator("ESIMS")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _latin1(data.get("store_name")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    if data.get("store_gstin"):
        pdf.cell(0, 5, _latin1(f"GSTIN: {data['store_gstin']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, _latin1(data.get("location_name")), new_x="LMARGIN", new_y="NEXT")
    if data.get("location_address"):
        pdf.multi_cell(0, 5, _latin1(data["location_address"]))
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    title = "Invoice" if document.kind == "invoice" else "Credit Note"
    number = (
        data.get("invoice_label") if document.kind == "invoice" else data.get("credit_note_number")
    )
    pdf.cell(0, 7, _latin1(f"{title} {number}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    for label, value in (
        ("Date", issued),
        (
            "Cashier",
            data.get("cashier_name")
            or data.get("processor_name")
            or data.get("processor_username"),
        ),
        ("Customer", data.get("customer_name")),
    ):
        if value:
            pdf.cell(0, 5, _latin1(f"{label}: {value}"), new_x="LMARGIN", new_y="NEXT")
    if document.annotation:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _latin1(document.annotation), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    widths = [78, 26, 30, 30]
    headers = ["Item", "Qty", "Unit price", "Amount"]

    def table_header() -> None:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for header, width, align in zip(headers, widths, ["L", "R", "R", "R"], strict=True):
            pdf.cell(width, 7, header, border=1, fill=True, align=align)
        pdf.ln()
        pdf.set_font("Helvetica", size=8)

    table_header()
    for line in data.get("lines", []):
        name = _latin1(f"{line.get('product_name', '')} ({line.get('sku', '')})")
        quantity = line.get("quantity", "")
        unit_price = line.get("unit_price") or line.get("refund_amount") or "0.00"
        amount = line.get("line_total") or line.get("refund_amount") or "0.00"
        cell_height = 5
        wrapped = pdf.multi_cell(widths[0], cell_height, name, dry_run=True, output="LINES")
        height = max(cell_height * len(wrapped), 7)
        if pdf.will_page_break(height):
            pdf.add_page()
            table_header()
        x, y = pdf.get_x(), pdf.get_y()
        pdf.rect(x, y, widths[0], height)
        pdf.multi_cell(widths[0], cell_height, name, new_x="RIGHT", new_y="TOP")
        x += widths[0]
        for value, width in (
            (quantity, widths[1]),
            (f"Rs {unit_price}", widths[2]),
            (f"Rs {amount}", widths[3]),
        ):
            pdf.set_xy(x, y)
            pdf.cell(width, height, _latin1(value), border=1, align="R")
            x += width
        pdf.set_xy(pdf.l_margin, y + height)

    pdf.ln(3)
    pdf.set_font("Helvetica", size=9)
    if document.kind == "invoice":
        for label, value in (
            ("Subtotal", data.get("subtotal")),
            ("Discount", data.get("discount_total")),
            (f"GST ({data.get('gst_rate', '0')}%)", data.get("tax_total")),
            ("Total", data.get("total")),
        ):
            if pdf.will_page_break(7):
                pdf.add_page()
            pdf.cell(135, 7, _latin1(label), align="R")
            pdf.cell(
                0, 7, _latin1(f"Rs {value or '0.00'}"), align="R", new_x="LMARGIN", new_y="NEXT"
            )
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Payments", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)
        for payment in data.get("payments", []):
            payment_text = (
                f"{payment.get('method', '')}: Rs {payment.get('amount', '0.00')} "
                f"{payment.get('reference') or ''}"
            )
            pdf.cell(
                0,
                5,
                _latin1(payment_text),
                new_x="LMARGIN",
                new_y="NEXT",
            )
    else:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(135, 8, "Refund total", align="R")
        pdf.cell(0, 8, _latin1(f"Rs {data.get('refund_total', '0.00')}"), align="R")
        pdf.ln()
        pdf.set_font("Helvetica", size=9)
        if data.get("reason"):
            pdf.multi_cell(0, 5, _latin1(f"Reason: {data['reason']}"))
    return bytes(pdf.output())
