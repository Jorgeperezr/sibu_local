from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("vincular/", views.vincular, name="vincular"),
    path("citas/", views.citas, name="citas"),
]
