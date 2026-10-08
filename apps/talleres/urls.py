from django.urls import path

from . import views

app_name = "talleres"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("<int:pk>/", views.detalle, name="detalle"),
]
