from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("", views.transaction_list, name="transaction_list"),
    path("upload/", views.statement_upload, name="upload"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
