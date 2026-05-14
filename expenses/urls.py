from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.user_login, name="login"),
    path("register/", views.user_register, name="register"),
    path("logout/", views.user_logout, name="logout"),

    # Password reset URLs
    path("password-reset/send-otp/", views.send_otp, name="send_otp"),
    path("password-reset/verify-otp/", views.verify_otp, name="verify_otp"),
    path("password-reset/change-password/", views.change_password, name="change_password"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("add-expense/", views.add_expense, name="add_expense"),
    path("add-note/", views.add_note, name="add_note"),
    path("expenses/add/", views.add_expense, name="add_expense"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("download_pdf/", views.download_pdf, name="download_pdf"),
    path("download_excel/", views.download_excel, name="download_excel"),
    path("budget/", views.set_budget, name="budget"),
    path("budget/edit/<int:budget_id>/", views.edit_budget, name="edit_budget"),
    path("budget/delete/<int:budget_id>/", views.delete_budget, name="delete_budget"),
    
      # Loan URLs
    path('loans/', views.loan_dashboard, name='loan_dashboard'),
    path('loans/add/', views.add_loan, name='add_loan'),
    path('loans/<int:loan_id>/edit/', views.edit_loan, name='edit_loan'),
    path('loans/<int:loan_id>/delete/', views.delete_loan, name='delete_loan'),
    path('loans/<int:loan_id>/payment/', views.add_payment, name='add_payment'),
    path('payments/<int:payment_id>/edit/', views.edit_payment, name='edit_payment'),
    path('payments/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),
    path("loans/<int:loan_id>/history/", views.payment_history, name="payment_history"),
    path('loans/<int:loan_id>/history/export/pdf/', views.export_loan_history_pdf, name='export_loan_history_pdf'),
    path('loans/<int:loan_id>/history/export/excel/', views.export_loan_history_excel, name='export_loan_history_excel'),
    path('loans/<int:loan_id>/receipt/', views.export_loan_receipt_pdf, name='export_loan_receipt_pdf'),
    path("history/", views.expense_history, name="expense_history"),
    path('expense/<int:expense_id>/edit/', views.edit_expense, name='edit_expense'),
    path('expense/<int:expense_id>/delete/', views.delete_expense, name='delete_expense'),
    path("history/download/", views.download_receipt, name="download_receipt"),
    # Account activation
    path("activate/<uidb64>/<token>/", views.activate_account, name="activate_account"),
    path('loan/<int:loan_id>/payment/add/', views.add_payment, name='add_payment'),
    path('receipt/<int:receipt_id>/download/', views.download_receipt, name='download_receipt'),
]
