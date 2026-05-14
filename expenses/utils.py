from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from decimal import Decimal
from datetime import date
import os

from .models import Loan, LoanPayment, LoanReceipt


def evaluate_loan(loan: Loan):
    """
    Calculate total interest, principal, paid, and due.
    Returns summary dict for receipt or dashboard.
    """
    today = date.today()
    principal_remaining = loan.amount
    total_interest = Decimal("0.00")
    total_paid = Decimal("0.00")
    last_date = loan.date
    payments = loan.payments.order_by("date")

    for p in payments:
        months = loan.get_month_diff(last_date, p.date)
        interest = (principal_remaining * loan.interest_rate * months) / 100
        total_interest += interest

        payment_amount = p.amount_paid
        total_paid += payment_amount

        # Adjust principal
        if payment_amount >= interest:
            payment_amount -= interest
            principal_remaining -= payment_amount
        else:
            principal_remaining += (interest - payment_amount)

        last_date = p.date

    # Final interest till today if loan not cleared
    if principal_remaining > 0:
        months = loan.get_month_diff(last_date, today)
        remaining_interest = (principal_remaining * loan.interest_rate * months) / 100
    else:
        remaining_interest = Decimal("0.00")

    total_due = principal_remaining + remaining_interest

    return {
        "loan": loan,
        "principal_remaining": round(principal_remaining, 2),
        "total_interest": round(total_interest, 2),
        "total_paid": round(total_paid, 2),
        "total_due": round(total_due, 2),
        "is_cleared": principal_remaining <= 0,
        "clear_date": last_date if principal_remaining <= 0 else None,
    }


def generate_loan_receipt_pdf(loan: Loan, data: dict, file_path: str):
    """
    Generate a clean loan receipt PDF using ReportLab.
    """

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'title_style',
        parent=styles['Heading1'],
        fontSize=16,
        alignment=1,
        spaceAfter=10
    )
    normal = styles['Normal']

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    elements = []

    elements.append(Paragraph("🧾 Loan Clearance Receipt", title_style))
    elements.append(Spacer(1, 6))

    info_data = [
        ["Name", loan.name],
        ["Loan Type", loan.get_type_display()],
        ["Principal Amount", f"₹{loan.amount}"],
        ["Interest Rate", f"{loan.interest_rate}% per month"],
        ["Start Date", loan.date.strftime("%d-%m-%Y")],
        ["Clear Date", data.get("clear_date").strftime("%d-%m-%Y") if data.get("clear_date") else "—"],
    ]
    info_table = Table(info_data, hAlign="LEFT", colWidths=[120, 300])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    summary_data = [
        ["Total Principal", f"₹{loan.amount}"],
        ["Total Interest Paid", f"₹{data['total_interest']}"],
        ["Total Amount Paid", f"₹{data['total_paid']}"],
        ["Remaining Due", f"₹{data['total_due']}"],
    ]
    summary_table = Table(summary_data, hAlign="LEFT", colWidths=[200, 200])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 16))

    elements.append(Paragraph(
        "This is a computer-generated loan receipt confirming that the loan has been completely settled. "
        "Keep this receipt for your records.", normal
    ))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Signature ____________________", normal))

    doc.build(elements)

    return file_path


def create_receipt_if_cleared(loan: Loan):
    """
    Check if loan is cleared, then create LoanReceipt and PDF.
    """
    data = evaluate_loan(loan)
    if not data["is_cleared"]:
        return None

    receipt, created = LoanReceipt.objects.get_or_create(
        loan=loan,
        user=loan.user,
        defaults={
            "total_principal": loan.amount,
            "total_interest": data["total_interest"],
            "total_paid": data["total_paid"],
            "clear_date": data["clear_date"],
        }
    )

    # Generate PDF file
    receipts_dir = "media/receipts/"
    os.makedirs(receipts_dir, exist_ok=True)
    file_path = os.path.join(receipts_dir, f"receipt_{loan.id}.pdf")

    generate_loan_receipt_pdf(loan, data, file_path)

    receipt.file.name = file_path.replace("media/", "")
    receipt.save()

    return receipt


from decimal import Decimal
from datetime import date, timedelta

def days_between(start_date, end_date):
    return max((end_date - start_date).days, 0)

def get_days_in_month(d: date) -> int:
    next_month = d.replace(day=28) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day)).day

def compute_due_today_simple(loan):
    payments = loan.payments.all().order_by("date")
    remaining_principal = Decimal(loan.amount)
    monthly_rate = Decimal(loan.interest_rate) / Decimal("100")
    start_date = loan.date
    today_local = date.today()
    total_interest = Decimal("0.00")

    for p in payments:
        days_passed = days_between(start_date, p.date)
        days_in_month = Decimal(get_days_in_month(start_date))
        daily_rate = monthly_rate / days_in_month
        interest_raw = remaining_principal * daily_rate * Decimal(days_passed)
        total_interest += interest_raw
        remaining_principal += interest_raw - Decimal(p.amount_paid)
        remaining_principal = max(remaining_principal, Decimal("0.00"))
        start_date = p.date

    if remaining_principal > 0:
        days_passed = days_between(start_date, today_local)
        days_in_month = Decimal(get_days_in_month(start_date))
        daily_rate = monthly_rate / days_in_month
        interest_today_raw = remaining_principal * daily_rate * Decimal(days_passed)
        total_interest += interest_today_raw
    else:
        interest_today_raw = Decimal("0.00")

    total_due_today = remaining_principal + interest_today_raw
    return total_due_today.quantize(Decimal("0.01"))
