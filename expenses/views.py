from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum 
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.dateparse import parse_date
from datetime import date
import json
from .models import Expense, DailyNote, Budget, Category, Loan, LoanPayment
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import IntegrityError
from datetime import datetime
import io
from django.http import FileResponse
from reportlab.pdfgen import canvas
import xlsxwriter
from django.utils.timezone import now
from django.core.paginator import Paginator
import calendar
import datetime
from decimal import Decimal, ROUND_HALF_UP, getcontext
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from reportlab.pdfgen import canvas
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from django.utils.timezone import now




# -------------- Home Page ----------------------
@login_required
def home(request):
    today = datetime.date.today()

    # Filters
    selected_month = request.GET.get("month")
    selected_year = request.GET.get("year")
    month = int(selected_month) if selected_month else today.month
    year = int(selected_year) if selected_year else today.year

    # Filtered Expenses
    expenses = Expense.objects.filter(user=request.user, date__year=year, date__month=month)
    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or 0

    # Total Budget (sum of all budgets for this month/year)
    budgets = Budget.objects.filter(user=request.user, year=year)
    budgets = budgets.filter(Q(month=month) | Q(month__isnull=True))
    total_budget = budgets.aggregate(total=Sum("limit"))["total"] or 0

    # Recent 5 Expenses
    recent_expenses = expenses.order_by("-date")[:5]

    # Recent Notes (current month/year)
    recent_notes = DailyNote.objects.filter(
        user=request.user, 
        date__year=year, 
        date__month=month
    ).order_by("-date")[:5]

    # Category-wise summary
    categories = Category.objects.filter(Q(user=request.user) | Q(user=None))
    category_data = []
    for cat in categories:
        cat_expenses = expenses.filter(category=cat)
        cat_total = cat_expenses.aggregate(total=Sum("amount"))["total"] or 0

        budget_qs = Budget.objects.filter(user=request.user, category=cat, year=year)
        budget_qs = budget_qs.filter(Q(month=month) | Q(month__isnull=True))
        budget_obj = budget_qs.first()
        budget_amount = budget_obj.limit if budget_obj else 0

        category_data.append({
            "id": cat.id,
            "name": cat.name,
            "total": cat_total,
            "budget": budget_amount
        })

    # Overbudget Alerts
    overbudget_alerts = [
        f"⚠️ You are over budget in {c['name']} (Spent ₹{c['total']} / Budget ₹{c['budget']})"
        for c in category_data if c["budget"] > 0 and c["total"] > c["budget"]
    ]
    overbudget_count = len(overbudget_alerts)
    underbudget_count = len(category_data) - overbudget_count

    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]

    context = {
        "total_expenses": total_expenses,
        "total_budget": total_budget,
        "recent_expenses": recent_expenses,
        "recent_notes": recent_notes,
        "category_data": category_data,
        "overbudget_alerts": overbudget_alerts,
        "overbudget_count": overbudget_count,
        "underbudget_count": underbudget_count,
        "selected_month": month,
        "selected_year": year,
        "months_list": months_list,
    }

    return render(request, "home.html", context)

# -------------- Home Page End----------------------





# -------------- User Login ----------------------

def user_login(request):
    if request.method == "POST":
        try:
            username = request.POST.get("username", "").strip()
            password = request.POST.get("password", "").strip()


            if not username or not password:
                messages.error(request, "⚠️ Both username and password are required.")
                return redirect("login")

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f"✅ Welcome back, {user.first_name}!")
                return redirect("dashboard")
            else:
                messages.error(request, "❌ Invalid username or password.")
                return redirect("login")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect("login")

    return render(request, "login.html")

# -------------- User Login End----------------------





# -------------- User Registration ----------------------

def user_register(request):
    if request.method == "POST":
        try:
            first_name = request.POST.get("first_name", "").strip()
            last_name = request.POST.get("last_name", "").strip()
            username = request.POST.get("username", "").strip()
            email = request.POST.get("email", "").strip()
            password = request.POST.get("password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()

            # Validations
            if not username or not email or not password or not confirm_password:
                messages.error(request, "⚠️ Username, email and password are required.")
                return redirect("register")

            if password != confirm_password:
                messages.error(request, "⚠️ Passwords do not match.")
                return redirect("register")

            # Validate email format
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "⚠️ Please enter a valid email address.")
                return redirect("register")

            # Unique username (case-insensitive)
            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, "⚠️ Username already exists. Please choose another.")
                return redirect("register")

            # Unique email (case-insensitive)
            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, "⚠️ An account with this email already exists.")
                return redirect("register")

            # Strong password validation (Django's validators)
            try:
                # Build a temporary user object to run validators with user context
                temp_user = User(username=username, email=email, first_name=first_name, last_name=last_name)
                validate_password(password, user=temp_user)
            except ValidationError as ve:
                for err in ve.messages:
                    messages.error(request, f"⚠️ {err}")
                return redirect("register")

            # Create User
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
                # Require email verification before login
                user.is_active = False
                user.save()

                # Send activation email
                try:
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    token = default_token_generator.make_token(user)
                    activation_link = request.build_absolute_uri(f"/activate/{uid}/{token}/")

                    subject = "Activate your Expense Tracker account"
                    greeting_name = first_name or username
                    message = (
                        f"Hi {greeting_name},\n\n"
                        f"Welcome to Expense Tracker! Please activate your account by clicking the link below:\n"
                        f"{activation_link}\n\n"
                        f"If you did not sign up, you can ignore this email.\n\n"
                        f"Thanks,\nExpense Tracker"
                    )
                    send_mail(subject, message, None, [email], fail_silently=True)
                except Exception:
                    pass

                messages.success(request, "🎉 Account created! Please check your email to activate your account.")
                return redirect("login")

            except IntegrityError:
                messages.error(request, "⚠️ Username already exists.")
                return redirect("register")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect("register")

    return render(request, "register.html")

# ---------------------- User Registration End----------------------

@login_required
def user_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "✅ You have been logged out successfully.")
        return redirect("login")
    return redirect("dashboard")  # GET request ko dashboard pe redirect

import random
from django.conf import settings
from django.contrib.auth.hashers import make_password


# -------------- Password Reset ----------------------
def send_otp(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = User.objects.get(email=email)
            otp = random.randint(100000, 999999)
            request.session["reset_email"] = email
            request.session["reset_otp"] = str(otp)

            # Send email
            send_mail(
                subject="Your OTP for Password Reset",
                message=f"Your OTP is {otp}. It will expire soon.",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email],
            )
            messages.success(request, "OTP sent to your email.")
            return redirect("verify_otp")
        except User.DoesNotExist:
            messages.error(request, "Email not found.")
    return render(request, "send_otp.html")

def verify_otp(request):
    if request.method == "POST":
        otp_entered = request.POST.get("otp")
        otp_session = request.session.get("reset_otp")

        if otp_entered == otp_session:
            messages.success(request, "OTP verified. Please set new password.")
            return redirect("change_password")
        else:
            messages.error(request, "Invalid OTP")
    return render(request, "verify_otp.html")

def change_password(request):
    if request.method == "POST":
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return redirect("change_password")

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect("change_password")

        email = request.session.get("reset_email")
        try:
            user = User.objects.get(email=email)
            user.password = make_password(password1)
            user.save()

            # clear session
            request.session.pop("reset_email", None)
            request.session.pop("reset_otp", None)

            messages.success(request, "Password updated successfully. Please login.")
            return redirect("login")
        except User.DoesNotExist:
            messages.error(request, "Something went wrong.")
    return render(request, "change_password.html")
# -------------- Account Activation ----------------------

def activate_account(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, "✅ Your account has been activated. You can now log in.")
        return redirect("login")
    else:
        messages.error(request, "❌ Activation link is invalid or has expired.")
        return redirect("login")


# ------------- User Registration End----------------------




# -------------- Add Expense ----------------------

@login_required
def add_expense(request):
    if request.method == "POST":
        try:
            amount = request.POST.get("amount")
            category_id = request.POST.get("category")
            desc = request.POST.get("description", "").strip()
            expense_date = request.POST.get("date", str(date.today()))

            # Validate
            if not amount or not category_id:
                messages.error(request, "Amount and Category are required.")
                return redirect("add_expense")

            try:
                amount = float(amount)
                if amount <= 0:
                    messages.error(request, "Amount must be greater than 0.")
                    return redirect("add_expense")
            except ValueError:
                messages.error(request, "Invalid amount.")
                return redirect("add_expense")

            try:
                category = Category.objects.get(id=category_id)
            except ObjectDoesNotExist:
                messages.error(request, "Selected category does not exist.")
                return redirect("add_expense")

            exp_date = parse_date(expense_date) or date.today()

            Expense.objects.create(
                user=request.user,
                category=category,
                description=desc,
                amount=amount,
                date=exp_date,
            )
            messages.success(request, "Expense added successfully ✅")
            return redirect("dashboard")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect("add_expense")

    categories = Category.objects.all()
    return render(request, "add_expense.html", {"categories": categories})

# ------------- Add Expense End----------------------




# ------------- Add Daily Note ----------------------

@login_required
def add_note(request):
    if request.method == "POST":
        try:
            note_text = request.POST.get("note", "").strip()
            note_date = request.POST.get("date", str(date.today()))

            if not note_text:
                messages.error(request, "Note cannot be empty.")
                return redirect("add_note")

            note_date = parse_date(note_date) or date.today()

            DailyNote.objects.create(
                user=request.user,
                note=note_text,
                date=note_date,
            )
            messages.success(request, "Note added successfully ✅")
            return redirect("dashboard")

        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect("add_note")

    return render(request, "add_note.html", {"today": date.today()})

# ------------- Add Daily Note End----------------------




# -------------- Dashboard ----------------------

@login_required
def dashboard(request):
    import calendar, datetime
    from decimal import Decimal
    from django.db.models import Sum
    from django.db.models import Q
    from .models import Expense, Category, Budget

    try:
        # User + global categories
        categories = Category.objects.filter(Q(user=request.user) | Q(user=None))

        # ---- Filters ----
        if request.method == "POST":
            selected_category = request.POST.get("category")
            selected_month = request.POST.get("month")
            selected_year = request.POST.get("year")
        else:
            selected_category = request.GET.get("category")
            selected_month = request.GET.get("month")
            selected_year = request.GET.get("year")

        # Default values
        now = datetime.date.today()
        month = int(selected_month) if selected_month else now.month
        year = int(selected_year) if selected_year else now.year

        # ---- Filtered expenses ----
        expenses = Expense.objects.filter(user=request.user, date__year=year)
        if month:
            expenses = expenses.filter(date__month=month)
        if selected_category:
            expenses = expenses.filter(category_id=selected_category)

        # Recent 5 expenses
        recent_expenses = expenses.order_by("-date")[:5]

        # Totals
        total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or 0
        budgets = Budget.objects.filter(user=request.user, year=year)
        if month:
            budgets = budgets.filter(month=month)
        total_budget = budgets.aggregate(total=Sum("limit"))["total"] or 0

        # Category-wise data
        category_data = []
        overbudget_count = 0
        underbudget_count = 0
        for cat in categories:
            cat_expenses = expenses.filter(category=cat)
            total_expense = cat_expenses.aggregate(total=Sum("amount"))["total"] or 0

            budget_qs = Budget.objects.filter(user=request.user, category=cat, year=year)
            if month:
                budget_qs = budget_qs.filter(month=month)
            budget_obj = budget_qs.first()
            budget_amount = budget_obj.limit if budget_obj else 0

            progress_pct = 0
            if budget_amount > 0:
                try:
                    progress_pct = round((float(total_expense) / float(budget_amount)) * 100, 2)
                except:
                    progress_pct = 0

            over_by = 0
            overbudget = False
            try:
                if budget_amount and total_expense > budget_amount:
                    over_by = (Decimal(total_expense) - Decimal(budget_amount)).quantize(Decimal("0.01"))
                    overbudget = True
            except:
                over_by = 0

            if budget_amount > 0:
                if overbudget:
                    overbudget_count += 1
                else:
                    underbudget_count += 1

            category_data.append({
                "id": cat.id,
                "name": cat.name,
                "total": total_expense,
                "budget": budget_amount,
                "progress_pct": progress_pct,
                "overbudget": overbudget,
                "over_by": over_by,
            })

        # Selected category detail
        selected_category_id = int(selected_category) if selected_category else None
        selected_category_detail = None
        if selected_category_id:
            sel_cat = categories.get(id=selected_category_id)
            sel_expenses = expenses.filter(category=sel_cat)
            sel_total = sel_expenses.aggregate(total=Sum("amount"))["total"] or 0
            sel_budget_qs = Budget.objects.filter(user=request.user, category=sel_cat, year=year)
            if month:
                sel_budget_qs = sel_budget_qs.filter(month=month)
            sel_budget_obj = sel_budget_qs.first()
            sel_budget = sel_budget_obj.limit if sel_budget_obj else 0
            sel_remaining = (sel_budget - sel_total) if sel_budget else 0
            selected_category_detail = {
                "id": sel_cat.id,
                "name": sel_cat.name,
                "total": sel_total,
                "budget": sel_budget,
                "remaining": sel_remaining if sel_budget else None,
                "recent_expenses": list(sel_expenses.order_by("-date")[:10]),
            }

        # Overbudget alerts
        overbudget_alerts = [
            f"⚠️ Over budget in {c['name']} (Spent ₹{c['total']} / Budget ₹{c['budget']})"
            for c in category_data if c["budget"] > 0 and c["total"] > c["budget"]
        ]

        context = {
            "categories": categories,
            "selected_category": int(selected_category) if selected_category else "",
            "selected_month": month,
            "selected_year": year,
            "recent_expenses": recent_expenses,
            "category_data": category_data,
            "overbudget_alerts": overbudget_alerts,
            "overbudget_count": overbudget_count,
            "underbudget_count": underbudget_count,
            "months_list": [(i, calendar.month_name[i]) for i in range(1, 13)],
            "selected_category_detail": selected_category_detail,
            "total_expenses": total_expenses,
            "total_budget": total_budget,
        }

    except Exception as e:
        context = {"error": str(e)}

    return render(request, "dashboard.html", context)


# -------------- Dashboard End----------------------




# -------------- Export Expenses PDF ----------------------

@login_required
def download_pdf(request):
    expenses = Expense.objects.filter(user=request.user).order_by('date')

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="expense_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph("Expense Report", styles['Title'])
    subtitle = Paragraph(f"User: {request.user.username}", styles['Normal'])
    elements.extend([title, Spacer(1, 6), subtitle, Spacer(1, 12)])

    data = [["Date", "Category", "Description", "Amount (₹)"]]
    total_amount = Decimal('0.00')
    for exp in expenses:
        data.append([
            exp.date.strftime("%d-%m-%Y"),
            exp.category.name if exp.category else "—",
            exp.description or "—",
            f"{Decimal(exp.amount):,.2f}"
        ])
        total_amount += Decimal(exp.amount)

    data.append(["", "", "TOTAL", f"{total_amount:,.2f}"])

    table = Table(data, colWidths=[75, 120, 200, 80])
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.HexColor('#ffffff'), colors.HexColor('#f3f4f6')]),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef3c7')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    return response

# ------------------------------- Export Expenses PDF End----------------------



# -------------- Export Expenses Excel ----------------------

@login_required
def download_excel(request):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    ws = workbook.add_worksheet('Expenses')

    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1f2937', 'font_color': 'white', 'border': 1})
    money_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
    text_fmt = workbook.add_format({'border': 1})
    total_fmt = workbook.add_format({'bold': True, 'bg_color': '#fff4cc', 'border': 1})

    headers = ['Date', 'Category', 'Description', 'Amount (₹)']
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)

    expenses = Expense.objects.filter(user=request.user).order_by('date')
    row = 1
    total = Decimal('0.00')
    widths = [len(h) for h in headers]
    for exp in expenses:
        date_str = str(exp.date)
        cat_str = exp.category.name if exp.category else '—'
        desc_str = exp.description or '—'
        amt = Decimal(exp.amount)

        ws.write(row, 0, date_str, text_fmt)
        ws.write(row, 1, cat_str, text_fmt)
        ws.write(row, 2, desc_str, text_fmt)
        ws.write_number(row, 3, float(amt), money_fmt)

        total += amt
        widths[0] = max(widths[0], len(date_str))
        widths[1] = max(widths[1], len(cat_str))
        widths[2] = max(widths[2], len(desc_str))
        widths[3] = max(widths[3], len(f"{amt:,.2f}"))
        row += 1

    ws.write(row, 0, '')
    ws.write(row, 1, '')
    ws.write(row, 2, 'TOTAL', total_fmt)
    ws.write_number(row, 3, float(total), total_fmt)

    for i, w in enumerate(widths):
        ws.set_column(i, i, min(w + 2, 50))

    workbook.close()
    output.seek(0)
    return FileResponse(output, as_attachment=True, filename='expense_report.xlsx')


# ------------------------------- Export Expenses Excel End----------------------





# -------------- Budget Management ----------------------
@login_required
def set_budget(request):
    now = datetime.date.today()
    
    # Month list to pass to template
    months_list = [(1, "January"), (2, "February"), (3, "March"), (4, "April"),
                   (5, "May"), (6, "June"), (7, "July"), (8, "August"),
                   (9, "September"), (10, "October"), (11, "November"), (12, "December")]

    if request.method == "POST":
        category_id = request.POST.get("category")
        limit = request.POST.get("limit")
        month = request.POST.get("month") or None
        year = request.POST.get("year") or now.year

        if category_id and limit and year:
            category = Category.objects.get(id=category_id)
            
            # Convert month and year to int
            month_val = int(month) if month else None
            year_val = int(year)

            budget, created = Budget.objects.update_or_create(
                user=request.user,
                category=category,
                month=month_val,
                year=year_val,
                defaults={"limit": limit}
            )
            messages.success(request, f"Budget set for {category.name} (₹{limit})")
            return redirect("budget")
        else:
            messages.error(request, "Please select category and enter valid limit/year.")

    categories = Category.objects.filter(user=request.user) | Category.objects.filter(user=None)
    budgets = Budget.objects.filter(user=request.user).select_related("category")

    return render(request, "set_budget.html", {
        "categories": categories,
        "budgets": budgets,
        "now": now,
        "months_list": months_list
    })

# -----------------Edit Budget-------------------------
@login_required
def edit_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    now = datetime.date.today()
    
    months_list = [(1, "January"), (2, "February"), (3, "March"), (4, "April"),
                   (5, "May"), (6, "June"), (7, "July"), (8, "August"),
                   (9, "September"), (10, "October"), (11, "November"), (12, "December")]

    categories = Category.objects.filter(user=request.user) | Category.objects.filter(user=None)

    if request.method == "POST":
        category_id = request.POST.get("category")
        limit = request.POST.get("limit")
        month = request.POST.get("month") or None
        year = request.POST.get("year")

        if category_id and limit and year:
            budget.category_id = category_id
            budget.limit = limit
            budget.month = int(month) if month else None
            budget.year = int(year)
            budget.save()

            messages.success(request, "✅ Budget updated successfully!")
            return redirect("budget")
        else:
            messages.error(request, "⚠️ Please fill all required fields.")

    return render(request, "edit_budget.html", {
        "budget": budget,
        "categories": categories,
        "months_list": months_list,
        "now": now
    })

# ---------------- Delete Budget ----------------------
@login_required
def delete_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    budget.delete()
    messages.warning(request, "🗑️ Budget deleted successfully!")
    return redirect("budget")

# -------------- Budget Management End----------------------


# ------------------------------------------------------- Loan Management -----------------------------------------------------------------------

# ---------------- Helper ----------------
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator


# Accurate day difference — exclusive end date
def days_between(start_date, end_date):
    return max((end_date - start_date).days, 0)


def get_days_in_month(d: date) -> int:
    """Get actual number of days in the given month."""
    next_month = d.replace(day=28) + timedelta(days=4)
    return (next_month - timedelta(days=next_month.day)).day


# ---------------- Accurate Due Today (Simple Interest) ----------------
def compute_due_today_simple(loan):
    """
    Finance-accurate simple interest calculation.
    ✅ Uses real month length (28–31 days)
    ✅ No per-step rounding errors
    ✅ End-only quantization
    """
    payments = loan.payments.all().order_by("date")
    remaining_principal = Decimal(loan.amount)
    monthly_rate = Decimal(loan.interest_rate) / Decimal("100")
    start_date = loan.date
    today_local = date.today()

    total_interest = Decimal("0.00")

    for p in payments:
        days_passed = days_between(start_date, p.date)

        # actual days in that month for daily rate
        days_in_month = Decimal(get_days_in_month(start_date))
        daily_rate = monthly_rate / days_in_month

        # no rounding per-step — round at end only
        interest_raw = remaining_principal * daily_rate * Decimal(days_passed)
        total_interest += interest_raw

        remaining_principal += interest_raw - Decimal(p.amount_paid)
        remaining_principal = max(remaining_principal, Decimal("0.00"))
        start_date = p.date

    # interest till today
    if remaining_principal > 0:
        days_passed = days_between(start_date, today_local)
        days_in_month = Decimal(get_days_in_month(start_date))
        daily_rate = monthly_rate / days_in_month
        interest_today_raw = remaining_principal * daily_rate * Decimal(days_passed)
        total_interest += interest_today_raw
    else:
        interest_today_raw = Decimal("0.00")

    total_due_today = remaining_principal + interest_today_raw

    # round only at the end (for finance accuracy)
    return total_due_today.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



# ---------------- Loan Dashboard ----------------
@login_required
def loan_dashboard(request):
    loans = Loan.objects.filter(user=request.user).order_by('-date')

    # 🔹 Filters: Name + Loan Type
    filter_name = request.GET.get('name', '').strip()
    filter_type = request.GET.get('loan_type', '')

    if filter_name:
        loans = loans.filter(name__icontains=filter_name)
    if filter_type:
        loans = loans.filter(type=filter_type)

    loan_summary = []
    total_taken = total_given = total_paid = total_remaining = total_interest = total_due = Decimal('0.00')
    today = date.today()

    for loan in loans:
        payments = loan.payments.all().order_by("date")
        remaining_principal = Decimal(loan.amount)
        monthly_rate = Decimal(loan.interest_rate) / Decimal("100")
        start_date = loan.date
        payments_total = Decimal('0.00')
        total_interest_loan = Decimal('0.00')

        # 🔹 Accurate per-day interest using calendar days
        for p in payments:
            days_passed = days_between(start_date, p.date)
            days_in_month = Decimal(get_days_in_month(start_date))
            daily_rate = monthly_rate / days_in_month

            interest_raw = remaining_principal * daily_rate * Decimal(days_passed)
            total_interest_loan += interest_raw

            remaining_principal += interest_raw - Decimal(p.amount_paid)
            remaining_principal = max(remaining_principal, Decimal('0.00'))
            payments_total += Decimal(p.amount_paid)
            start_date = p.date

        # 🔹 Interest till today (final period)
        if remaining_principal > 0:
            days_passed = days_between(start_date, today)
            days_in_month = Decimal(get_days_in_month(start_date))
            daily_rate = monthly_rate / days_in_month
            interest_today_raw = remaining_principal * daily_rate * Decimal(days_passed)
            total_interest_loan += interest_today_raw
        else:
            interest_today_raw = Decimal('0.00')

        total_due_loan = remaining_principal + interest_today_raw

        # Round at the end
        total_interest_loan = total_interest_loan.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_due_loan = total_due_loan.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        remaining_principal = remaining_principal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        loan_summary.append({
            'loan': loan,
            'paid': payments_total,
            'principal_remaining': remaining_principal,
            'interest': total_interest_loan,
            'total_due': total_due_loan
        })

        # 🔹 Totals
        if loan.type == 'me':
            total_taken += total_due_loan
        elif loan.type == 'others':
            total_given += total_due_loan

        total_paid += payments_total
        total_remaining += remaining_principal
        total_interest += total_interest_loan
        total_due += total_due_loan

    context = {
        'loan_summary': loan_summary,
        'total_taken': total_taken.quantize(Decimal("0.01")),
        'total_given': total_given.quantize(Decimal("0.01")),
        'total_paid': total_paid.quantize(Decimal("0.01")),
        'total_remaining': total_remaining.quantize(Decimal("0.01")),
        'total_interest': total_interest.quantize(Decimal("0.01")),
        'total_due': total_due.quantize(Decimal("0.01")),
        'filter_name': filter_name,
        'filter_type': filter_type,
    }

    return render(request, 'loan_dashboard.html', context)



# ---------------- Accurate Interest Calculations ----------------
def calculate_simple_interest(principal, rate, periods):
    principal = Decimal(principal)
    rate = Decimal(rate)
    interest = principal * rate / Decimal("100") * periods
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_compound_interest(principal, rate, periods, divisor):
    principal = Decimal(principal)
    rate = Decimal(rate)
    base = Decimal("1") + (rate / Decimal("100") / divisor)
    total = principal * (base ** periods)
    interest = total - principal
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



# ---------------- Payment History View ----------------
@login_required
def payment_history(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    payments = loan.payments.all().order_by("date")

    interest_type = request.GET.get("interest_type", "simple")  # simple or compound
    duration = request.GET.get("duration", "day")  # day, month, or year

    principal = Decimal(loan.amount)
    total_interest_paid = Decimal("0")
    total_paid = Decimal("0")
    today = date.today()
    history = []
    loan_clear_date = None

    start_date = loan.date

    # ✅ Initialize to avoid UnboundLocalError
    interest_today = Decimal("0.00")
    total_due_today = Decimal("0.00")

    def periods_between(start_d, end_d, dur):
        days_passed_local = (end_d - start_d).days
        if days_passed_local < 0:
            return Decimal("0")
        if dur == "day":
            return Decimal(days_passed_local) / Decimal("30")
        if dur == "month":
            return Decimal(days_passed_local) / Decimal("30")
        if dur == "year":
            return (Decimal(days_passed_local) / Decimal("365")) * Decimal("12")
        return Decimal(days_passed_local) / Decimal("30")

    for p in payments:
        periods = periods_between(start_date, p.date, duration)
        divisor = Decimal("365") if duration == "day" else (Decimal("12") if duration == "month" else Decimal("1"))

        if interest_type == "simple":
            interest = calculate_simple_interest(principal, loan.interest_rate, periods)
        else:
            interest = calculate_compound_interest(principal, loan.interest_rate, periods, divisor)

        balance_before_payment = principal + interest
        principal = max(balance_before_payment - Decimal(p.amount_paid), Decimal("0"))

        total_interest_paid += interest
        total_paid += Decimal(p.amount_paid)

        # 🔹 Remaining interest till today
        if principal > 0:
            remaining_periods = periods_between(p.date, today, duration)
            divisor_remain = divisor
            if interest_type == "simple":
                interest_today = calculate_simple_interest(principal, loan.interest_rate, remaining_periods)
            else:
                interest_today = calculate_compound_interest(principal, loan.interest_rate, remaining_periods, divisor_remain)
            total_due_today = principal + interest_today
        else:
            # Fully cleared loan
            interest_today = Decimal("0.00")
            total_due_today = Decimal("0.00")
            loan_clear_date = p.date

        history.append({
            "payment": p,
            "interest_accrued": interest,
            "remaining_balance": principal.quantize(Decimal("0.01")),
            "interest_till_today": interest_today.quantize(Decimal("0.01")),
            "total_due": total_due_today.quantize(Decimal("0.01"))
        })

        start_date = p.date

    # 🔹 If no payments but loan still has principal
    if not payments.exists() and principal > 0:
        periods = periods_between(start_date, today, duration)
        divisor = Decimal("365") if duration == "day" else (Decimal("12") if duration == "month" else Decimal("1"))
        if interest_type == "simple":
            interest_today = calculate_simple_interest(principal, loan.interest_rate, periods)
        else:
            interest_today = calculate_compound_interest(principal, loan.interest_rate, periods, divisor)
        total_due_today = principal + interest_today

    total_interest_due = interest_today
    total_paid_plus_remaining = total_paid + total_due_today
    progress_percent = round((total_paid / total_paid_plus_remaining) * 100, 2) if total_paid_plus_remaining > 0 else 0

    page_number = request.GET.get("page", 1)
    paginator = Paginator(history, 10)
    page_obj = paginator.get_page(page_number)

    context = {
        "loan": loan,
        "payments": page_obj,
        "loan_taken_date": loan.date,
        "loan_clear_date": loan_clear_date,
        "total_paid": total_paid.quantize(Decimal("0.01")),
        "total_interest_paid": total_interest_paid.quantize(Decimal("0.01")),
        "total_interest_due": total_interest_due.quantize(Decimal("0.01")),
        "remaining_till_today": total_due_today.quantize(Decimal("0.01")),
        "today": today,
        "progress_percent": progress_percent,
        "interest_type": interest_type,
        "duration": duration,
        "page_obj": page_obj,
        "paginator": paginator,
    }

    return render(request, "payment_history.html", context)


# -------------------End Payment History View -------------------




# ---------------- Add Loan ----------------

@login_required
def add_loan(request):
    current_year = date.today().year
    if request.method == 'POST':
        try:
            name = (request.POST.get('name') or '').strip()
            loan_type = request.POST.get('type')
            amount_raw = request.POST.get('amount')
            interest_raw = request.POST.get('interest_rate') or '0'
            date_str = request.POST.get('date')
            description = request.POST.get('description') or ''

            if not name:
                messages.error(request, "Name is required.")
                return redirect('add_loan')
            if loan_type not in ['me', 'others']:
                messages.error(request, "Invalid loan type.")
                return redirect('add_loan')

            try:
                amount = Decimal(amount_raw)
                if amount <= 0:
                    raise ValueError
            except Exception:
                messages.error(request, "Enter a valid positive amount.")
                return redirect('add_loan')

            try:
                interest_rate = Decimal(interest_raw)
                if interest_rate < 0:
                    raise ValueError
            except Exception:
                messages.error(request, "Enter a valid interest rate (>= 0).")
                return redirect('add_loan')

            try:
                loan_date = parse_date(date_str)
                if loan_date is None:
                    raise ValueError
                if loan_date > date.today():
                    messages.error(request, "Date cannot be in the future.")
                    return redirect('add_loan')
            except Exception:
                messages.error(request, "Enter a valid date.")
                return redirect('add_loan')

            Loan.objects.create(
                user=request.user,
                name=name,
                amount=amount,
                type=loan_type,
                date=loan_date,
                description=description,
                interest_rate=interest_rate
            )
            messages.success(request, "Loan added successfully.")
            return redirect('loan_dashboard')
        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect('add_loan')
    
    return render(request, 'add_loan.html', {'current_year': current_year})

# -----------------------End Add Loan -----------------------

# ------------------- Edit/Delete Loan -----------------------

@login_required
def edit_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    if request.method == 'POST':
        try:
            name = (request.POST.get('name') or '').strip()
            loan_type = request.POST.get('type')
            amount = Decimal(request.POST.get('amount'))
            interest_rate = Decimal(request.POST.get('interest_rate') or '0')
            date_str = request.POST.get('date')
            description = request.POST.get('description') or ''
            loan_date = parse_date(date_str)

            if not name or amount <= 0 or interest_rate < 0 or loan_type not in ['me', 'others'] or loan_date is None:
                messages.error(request, 'Invalid form data.')
                return redirect('edit_loan', loan_id=loan.id)
            if loan_date > date.today():
                messages.error(request, 'Date cannot be in the future.')
                return redirect('edit_loan', loan_id=loan.id)

            loan.name = name
            loan.type = loan_type
            loan.amount = amount
            loan.interest_rate = interest_rate
            loan.date = loan_date
            loan.description = description
            loan.save()
            messages.success(request, 'Loan updated successfully.')
            return redirect('loan_dashboard')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return redirect('edit_loan', loan_id=loan.id)
    return render(request, 'add_loan.html', {'loan': loan, 'current_year': date.today().year})

@login_required
def delete_loan(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    if request.method == 'POST':
        loan.delete()
        messages.success(request, 'Loan deleted successfully.')
        return redirect('loan_dashboard')
    return render(request, 'add_loan.html', {'loan': loan, 'delete_confirm': True})



# ------------------- Edit/Delete Payment -----------------------

@login_required
def edit_payment(request, payment_id):
    payment = get_object_or_404(LoanPayment, id=payment_id, loan__user=request.user)
    loan = payment.loan
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount_paid'))
            date_str = request.POST.get('date')
            note = request.POST.get('note') or ''
            pay_date = parse_date(date_str)
            if amount <= 0 or pay_date is None or pay_date < loan.date or pay_date > date.today():
                messages.error(request, 'Invalid payment data.')
                return redirect('edit_payment', payment_id=payment.id)
            payment.amount_paid = amount
            payment.date = pay_date
            payment.note = note
            payment.save()
            messages.success(request, 'Payment updated successfully.')
            return redirect('loan_dashboard')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return redirect('edit_payment', payment_id=payment.id)
    return render(request, 'add_payment.html', {'loan': loan, 'payment': payment})

@login_required
def delete_payment(request, payment_id):
    payment = get_object_or_404(LoanPayment, id=payment_id, loan__user=request.user)
    loan = payment.loan
    if request.method == 'POST':
        payment.delete()
        messages.success(request, 'Payment deleted successfully.')
        return redirect('loan_dashboard')
    return render(request, 'add_payment.html', {'loan': loan, 'payment': payment, 'delete_confirm': True})

# -----------------------End Edit/Delete Loan -----------------------

# ------------------- Export Loan History -----------------------

@login_required
def export_loan_history_pdf(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    payments = loan.payments.all().order_by('date')

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="loan_{loan.id}_history.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(f"Loan History — {loan.name}", styles['Title'])
    subtitle = Paragraph(f"Amount: ₹{loan.amount} | Rate: {loan.interest_rate}%/month", styles['Normal'])
    elements.extend([title, Spacer(1, 6), subtitle, Spacer(1, 12)])

    data = [["Date", "Amount Paid (₹)", "Note"]]
    for pmt in payments:
        data.append([
            pmt.date.strftime('%d-%m-%Y'),
            f"{Decimal(pmt.amount_paid):,.2f}",
            pmt.note or '—'
        ])

    table = Table(data, colWidths=[90, 120, 270])
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f3f4f6')]),
    ])
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    return response

@login_required
def export_loan_history_excel(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    payments = loan.payments.all().order_by('date')
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output)
    ws = workbook.add_worksheet('History')

    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1f2937', 'font_color': 'white', 'border': 1})
    money_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
    text_fmt = workbook.add_format({'border': 1})

    headers = ['Date', 'Amount Paid (₹)', 'Note']
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)
    row = 1
    for pay in payments:
        ws.write(row, 0, str(pay.date), text_fmt)
        ws.write_number(row, 1, float(pay.amount_paid), money_fmt)
        ws.write(row, 2, pay.note or '-', text_fmt)
        row += 1
    workbook.close()
    output.seek(0)
    return FileResponse(output, as_attachment=True, filename=f'loan_{loan.id}_history.xlsx')

# ------------------- Loan Clearance Receipt -----------------------

@login_required
def export_loan_receipt_pdf(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    payments = loan.payments.all().order_by('date')

    # Simple cleared heuristic: total paid >= principal (note: interest not included here)
    total_paid = sum((p.amount_paid for p in payments), Decimal('0'))
    cleared = total_paid >= Decimal(loan.amount)
    clear_date = payments.last().date if cleared and payments.exists() else None

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="loan_{loan.id}_receipt.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("Loan Clearance Receipt", styles['Title']))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"User: {request.user.username}", styles['Normal']))
    elements.append(Paragraph(f"Loan: {loan.name} | Type: {loan.get_type_display()} | Rate: {loan.interest_rate}%/month", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Summary
    summary_data = [
        ["Loan Amount (₹)", f"{Decimal(loan.amount):,.2f}"],
        ["Loan Date", loan.date.strftime('%d-%m-%Y')],
        ["Total Paid (₹)", f"{Decimal(total_paid):,.2f}"],
        ["Status", "CLEARED" if cleared else "NOT CLEARED"],
    ]
    if clear_date:
        summary_data.append(["Cleared On", clear_date.strftime('%d-%m-%Y')])

    summary = Table(summary_data, colWidths=[200, 300])
    summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.extend([summary, Spacer(1, 12)])

    # Payments
    data = [["Date", "Amount Paid (₹)", "Note"]]
    for p in payments:
        data.append([
            p.date.strftime('%d-%m-%Y'),
            f"{Decimal(p.amount_paid):,.2f}",
            p.note or '—'
        ])
    table = Table(data, colWidths=[90, 120, 290])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f3f4f6')]),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    elements.append(table)

    elements.extend([Spacer(1, 16), Paragraph("This is a system generated receipt.", styles['Italic'])])

    doc.build(elements)
    return response





# ---------------- Add Payment ----------------
from .models import Loan, LoanPayment
from .utils import compute_due_today_simple, create_receipt_if_cleared
from django.utils.dateparse import parse_date

@login_required
def add_payment(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, user=request.user)
    if request.method == 'POST':
        try:
            amount_raw = request.POST.get('amount_paid')
            date_str = request.POST.get('date')
            note = request.POST.get('note') or ''

            # ✅ Validate amount
            try:
                amount = Decimal(amount_raw)
                if amount <= 0:
                    raise ValueError
            except Exception:
                messages.error(request, "Enter a valid positive payment amount.")
                return redirect('add_payment', loan_id=loan.id)

            # ✅ Validate date
            try:
                payment_date = parse_date(date_str)
                if payment_date is None:
                    raise ValueError
                if payment_date < loan.date:
                    messages.error(request, "Payment date cannot be before loan date.")
                    return redirect('add_payment', loan_id=loan.id)
                if payment_date > date.today():
                    messages.error(request, "Payment date cannot be in the future.")
                    return redirect('add_payment', loan_id=loan.id)
            except Exception:
                messages.error(request, "Enter a valid payment date.")
                return redirect('add_payment', loan_id=loan.id)

            # ✅ Create payment
            LoanPayment.objects.create(
                loan=loan,
                amount_paid=amount,
                date=payment_date,
                note=note
            )

            # ✅ Check overpayment using simple interest
            try:
                due_today = compute_due_today_simple(loan)
                overpay = (amount - due_today).quantize(Decimal("0.01"))
                if overpay > 0:
                    messages.success(request, f"Payment added. You overpaid by ₹{overpay}. It may reduce future interest accrual.")
                else:
                    messages.success(request, "Payment added successfully.")
            except Exception:
                messages.success(request, "Payment added successfully.")

            # ✅ Auto-generate receipt if loan cleared
            receipt = create_receipt_if_cleared(loan)
            if receipt:
                messages.success(request, "🎉 Loan cleared! Receipt generated automatically.")

            return redirect('loan_dashboard')
        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
            return redirect('add_payment', loan_id=loan.id)

    return render(request, 'add_payment.html', {'loan': loan})

# ------------------- add_payment end-----------------------








# ------------------- Download Receipt (Updated with Text Wrap & Better Layout) ---------------------------

from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.utils.timezone import now
from django.contrib.auth.decorators import login_required
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from io import BytesIO
import calendar
from datetime import date

from .models import Expense, Category, Budget


@login_required
def download_receipt(request):
    try:
        month = request.GET.get("month")
        month = int(month) if month and month != "None" else None
    except ValueError:
        month = None

    try:
        year = int(request.GET.get("year", date.today().year))
    except ValueError:
        year = date.today().year

    try:
        category_id = request.GET.get("category")
        category_id = int(category_id) if category_id and category_id != "None" else None
    except ValueError:
        category_id = None

    # ----- Filtered Expenses -----
    expenses = Expense.objects.filter(user=request.user, date__year=year)
    if month:
        expenses = expenses.filter(date__month=month)
    if category_id:
        expenses = expenses.filter(category_id=category_id)

    # ----- PDF Setup -----
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleFont", fontSize=14, leading=18, spaceAfter=10, alignment=1))
    styles.add(ParagraphStyle(name="NormalSmall", fontSize=9, leading=12))
    desc_style = ParagraphStyle(
        name="desc_style",
        fontSize=9,
        leading=12,
        wordWrap='LTR',
    )

    # ----- Title -----
    title_text = f"Expense Report - {year}"
    if month:
        title_text += f" ({calendar.month_name[month]})"
    if category_id:
        cat_obj = get_object_or_404(Category, id=category_id)
        title_text += f" - {cat_obj.name}"

    elements.append(Paragraph(title_text, styles['TitleFont']))
    elements.append(Spacer(1, 10))

    # ----- Expense Table -----
    table_data = [["Date", "Category", "Description", "Amount (₹)"]]

    for exp in expenses.order_by("-date"):
        table_data.append([
            exp.date.strftime("%d-%m-%Y"),
            Paragraph(exp.category.name if exp.category else "-", styles['NormalSmall']),
            Paragraph(exp.description or "-", desc_style),
            f"₹{exp.amount:,.2f}",
        ])

    exp_table = Table(table_data, colWidths=[70, 100, 220, 70], repeatRows=1)
    exp_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))

    # Alternate row background color
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            bg_color = colors.whitesmoke
        else:
            bg_color = colors.lightgrey
        exp_table.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), bg_color)]))

    elements.append(exp_table)
    elements.append(Spacer(1, 20))

    # ----- Category Summary -----
    elements.append(Paragraph("Category Summary", styles['TitleFont']))
    cat_data = [["Category", "Total Expense (₹)", "Budget (₹)", "Remaining (₹)"]]

    categories = Category.objects.filter(id__in=expenses.values_list("category_id", flat=True))

    for cat in categories:
        cat_exp = expenses.filter(category=cat)
        total = sum(exp.amount for exp in cat_exp)

        budget_qs = Budget.objects.filter(user=request.user, category=cat, year=year)
        budget_obj = budget_qs.first()
        budget_limit = budget_obj.limit if budget_obj else 0
        remaining = budget_limit - total if budget_obj else None

        cat_data.append([
            cat.name,
            f"₹{total:,.2f}",
            f"₹{budget_limit:,.2f}" if budget_obj else "-",
            f"₹{remaining:,.2f}" if remaining is not None else "-"
        ])

    cat_table = Table(cat_data, colWidths=[150, 120, 120, 120], repeatRows=1)
    cat_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#34495e")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(cat_table)

    # ----- Build PDF -----
    doc.build(elements)
    buffer.seek(0)

    filename = f"expense_report_{year}"
    if month:
        filename += f"_{month}"
    if category_id:
        filename += f"_{category_id}"
    filename += ".pdf"

    return FileResponse(buffer, as_attachment=True, filename=filename)

# ------------------- Download Receipt End ---------------------------




# ----------------------Expense History--------------------------


@login_required
def expense_history(request):
    import calendar
    from datetime import date

    months = [(i, calendar.month_name[i]) for i in range(1, 13)]
    current_year = date.today().year

    # filters
    data = request.POST if request.method == "POST" else request.GET
    selected_month = data.get("month")
    selected_year = int(data.get("year", current_year))
    selected_category = data.get("category")

    expenses = Expense.objects.filter(
    user=request.user,
    date__year=selected_year
    ).order_by('-date', '-id')

    # convert month to int if present
    if selected_month:
        try:
            selected_month = int(selected_month)
            expenses = expenses.filter(date__month=selected_month)
        except ValueError:
            pass

    if selected_category:
        expenses = expenses.filter(category_id=selected_category)

    categories = Category.objects.all()

    # category summary
    category_data = []
    for cat in categories:
        cat_expenses = expenses.filter(category=cat)
        total = sum(e.amount for e in cat_expenses)
        budget_obj = Budget.objects.filter(user=request.user, category=cat, year=selected_year).first()
        budget = budget_obj.limit if budget_obj else 0
        overbudget = total > budget if budget else False
        category_data.append({
            "category": cat,
            "total": total,
            "budget": budget,
            "overbudget": overbudget,
        })

    return render(request, "history.html", {
        "expenses": expenses,
        "categories": categories,
        "months": months,
        "selected_month": selected_month,
        "selected_year": selected_year,
        "selected_category": selected_category,
        "category_data": category_data,
        "current_year": current_year,
    })


# ----------------------Expense History End--------------------------


# ---------------------- Edit Expense ----------------------

@login_required
def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)
    categories = Category.objects.filter(user=request.user) | Category.objects.filter(user=None)

    if request.method == "POST":
        category_id = request.POST.get("category")
        description = request.POST.get("description")
        amount = request.POST.get("amount")
        date = request.POST.get("date")

        if category_id and amount and date:
            expense.category_id = category_id
            expense.description = description
            expense.amount = amount
            expense.date = date
            expense.save()

            messages.success(request, "✅ Expense updated successfully!")
            return redirect("expense_history")  # aapka expense list page ka url name
        else:
            messages.error(request, "⚠️ Please fill all required fields.")

    return render(request, "edit_expense_form.html", {
        "expense": expense,
        "categories": categories
    })

# ---------------------- Edit Expense End ----------------------


# ---------------- Delete Expense ------------------------------

@login_required
def delete_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, user=request.user)

    if request.method == "POST":
        expense.delete()
        messages.warning(request, "🗑️ Expense deleted successfully!")
        return redirect("expense_history")  # aapka expense list page ka url name

    # Agar GET request aayi, redirect back
    return redirect("expense_history")

#   ---------------- Delete Expense End --------------------------





