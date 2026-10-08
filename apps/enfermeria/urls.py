from django.urls import path

from . import views

app_name = "enfermeria"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("triaje/<int:expediente_id>/", views.triaje, name="triaje"),
]
