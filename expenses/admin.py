from django.contrib import admin
from .models import Category, Expense, DailyNote, Budget, Loan, LoanPayment

# ---------------- Basic Admin ----------------
admin.site.register(Category)
admin.site.register(Expense)
admin.site.register(DailyNote)

# ---------------- Budget Admin ----------------
@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "limit", "month", "year")
    list_filter = ("user", "category", "year", "month")
    search_fields = ("category__name", "user__username")
    ordering = ("-year", "month")


# ---------------- Loan Admin ----------------
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'name', 'type', 'amount', 'interest_rate',
        'total_due_display', 'interest_display', 'principal_remaining_display',
        'date', 'month', 'year'
    )
    list_filter = ('type', 'month', 'year', 'date', 'user')
    search_fields = ('name', 'description', 'user__username')
    ordering = ('-date',)
    readonly_fields = ('created_at',)

    # Calculated fields display
    def total_due_display(self, obj):
        return obj.calculate_total_due()['total_due']
    total_due_display.short_description = 'Total Due (₹)'

    def interest_display(self, obj):
        return obj.calculate_total_due()['interest']
    interest_display.short_description = 'Interest (₹)'

    def principal_remaining_display(self, obj):
        return obj.calculate_total_due()['principal_remaining']
    principal_remaining_display.short_description = 'Remaining Principal (₹)'


# ---------------- LoanPayment Admin ----------------
@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'amount_paid', 'date', 'note', 'created_at')
    list_filter = ('date', 'loan__type', 'loan__user')
    search_fields = ('loan__name', 'note', 'loan__user__username')
    ordering = ('-date',)
    readonly_fields = ('created_at',)
