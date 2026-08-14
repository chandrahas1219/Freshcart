"""
Order receipt emails.

Generates a simple PDF receipt for a completed order and emails it to the
customer's registered address via SMTP. Designed to fail quietly - if SMTP
isn't configured, or the send fails for any reason, the checkout flow should
NOT break. The order is already saved before this runs.
"""

import io
import smtplib
from email.message import EmailMessage

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from config import Config


def generate_receipt_pdf(customer, order):
    """Build a one-page PDF receipt for an order. Returns raw PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReceiptTitle", parent=styles["Title"], fontSize=20, spaceAfter=2)
    meta_style = ParagraphStyle("ReceiptMeta", parent=styles["Normal"], textColor=colors.grey)

    elements = []
    elements.append(Paragraph("FreshCart", title_style))
    elements.append(Paragraph("Order Receipt", meta_style))
    elements.append(Spacer(1, 10 * mm))

    elements.append(Paragraph(f"<b>Order #</b> {order['order_id']}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date</b> {order['timestamp']}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Billed to</b> {customer.get('Name', '')} ({customer.get('Email', '')})", styles["Normal"]))
    elements.append(Paragraph(f"<b>Payment method</b> {order['payment_method']}", styles["Normal"]))
    elements.append(Spacer(1, 8 * mm))

    table_data = [["Item", "Qty", "Unit", "Unit Price", "Subtotal"]]
    for line in order["line_items"]:
        table_data.append([
            line["name"],
            str(line["quantity"]),
            line["unit"],
            f"Rs. {line['unit_price']:.2f}",
            f"Rs. {line['subtotal']:.2f}",
        ])
    table_data.append(["", "", "", "Total", f"Rs. {order['total']:.2f}"])

    table = Table(table_data, colWidths=[60 * mm, 20 * mm, 20 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -2), 0.4, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f9fafb")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12 * mm))
    elements.append(Paragraph("Thank you for shopping with FreshCart!", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


def send_receipt_email(customer, order):
    """
    Email the receipt PDF to the customer. Returns True on success, False
    otherwise. Never raises - checkout must not fail because of this.
    """
    if not Config.SMTP_HOST or not Config.SMTP_USER or not Config.SMTP_PASSWORD:
        return False

    to_email = (customer.get("Email") or "").strip()
    if not to_email:
        return False

    try:
        pdf_bytes = generate_receipt_pdf(customer, order)

        msg = EmailMessage()
        msg["Subject"] = f"Your FreshCart receipt - Order #{order['order_id']}"
        msg["From"] = Config.SMTP_FROM or Config.SMTP_USER
        msg["To"] = to_email

        first_name = (customer.get("Name") or "there").split(" ")[0]
        msg.set_content(
            f"Hi {first_name},\n\n"
            f"Thanks for your order! Your payment of Rs. {order['total']:.2f} "
            f"was successful (Order #{order['order_id']}, paid via {order['payment_method']}).\n\n"
            f"Your receipt is attached as a PDF for your records.\n\n"
            f"See you again soon!\n"
            f"- The FreshCart Team"
        )

        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"FreshCart_Receipt_Order{order['order_id']}.pdf",
        )

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            if Config.SMTP_USE_TLS:
                server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as exc:
        print(f"[email_utils] Failed to send receipt email to {to_email}: {exc}")
        return False
