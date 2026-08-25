from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("upload/", views.upload, name="upload"),
]
