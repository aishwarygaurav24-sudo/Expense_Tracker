from django.db import models
from django.contrib.auth.models import User
from datetime import date


class Category(models.Model):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Category owner (null = global category)"
    )

    class Meta:
        unique_together = ('name', 'user')  # Prevent duplicate category names per user

    def __str__(self):
        return self.name


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,   # Protect so you can’t delete category with expenses
        null=False,                 # Category is now required
        blank=False
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | {self.category} | {self.amount}"


class DailyNote(models.Model):
    MOOD_CHOICES = [
        ('happy', '🙂 Happy'),
        ('neutral', '😐 Neutral'),
        ('sad', '☹️ Sad'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    note = models.TextField()
    mood = models.CharField(max_length=10, choices=MOOD_CHOICES, default='neutral')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | {self.date}"


class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Budget limit for this category"
    )
    month = models.PositiveIntegerField(null=True, blank=True, help_text="1-12 for monthly budget, leave blank for yearly")
    year = models.PositiveIntegerField(default=2025, help_text="Year for this budget (required)")

    def __str__(self):
        if self.month:
            return f"{self.user.username} | {self.category.name} : {self.limit} (Month: {self.month}/{self.year})"
        return f"{self.user.username} | {self.category.name} : {self.limit} (Year: {self.year})"
    




# ---------------- Loan ----------------


class Loan(models.Model):
    LOAN_TYPE_CHOICES = [('me', 'Loan Taken by Me'), ('others', 'Loan Given to Others')]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=LOAN_TYPE_CHOICES)
    date = models.DateField()
    month = models.PositiveIntegerField(null=True, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, help_text="Monthly interest rate %")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} | {self.name} | ₹{self.amount}"

    def get_month_diff(self, from_date, to_date):
        """Returns full months difference between two dates."""
        return max(0, (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month))

    def calculate_total_due(self):
        """
        Calculates remaining principal + interest.
        Payments first cover interest, then principal.
        Interest is applied month-wise.
        """
        today = date.today()
        principal_remaining = self.amount
        payments = self.payments.order_by('date')
        last_date = self.date

        for payment in payments:
            months = self.get_month_diff(last_date, payment.date)
            interest = (principal_remaining * self.interest_rate * months) / 100
            total_due = principal_remaining + interest

            payment_amount = payment.amount_paid
            if payment_amount >= interest:
                payment_amount -= interest
                principal_remaining -= payment_amount
            else:
                # Partial payment less than interest
                principal_remaining += interest - payment_amount
            last_date = payment.date

        # Remaining interest till today
        months = self.get_month_diff(last_date, today)
        interest = (principal_remaining * self.interest_rate * months) / 100
        total_due = principal_remaining + interest

        return {
            'principal_remaining': round(principal_remaining, 2),
            'interest': round(interest, 2),
            'total_due': round(total_due, 2)
        }


# ---------------- LoanPayment ----------------
class LoanPayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.loan.name} | Paid: ₹{self.amount_paid} on {self.date}"
    


# ---------------- LoanReceipt ----------------
class LoanReceipt(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_principal = models.DecimalField(max_digits=12, decimal_places=2)
    total_interest = models.DecimalField(max_digits=12, decimal_places=2)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2)
    clear_date = models.DateField()
    file = models.FileField(upload_to='receipts/', null=True, blank=True)  # PDF receipt file
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt | {self.loan.name} | {self.user.username} | {self.clear_date}"
