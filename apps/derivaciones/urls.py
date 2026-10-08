from django.urls import path

from . import views

app_name = "derivaciones"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("derivar/<int:atencion_id>/", views.derivar, name="derivar"),
    path("gestionar/<int:pk>/", views.gestionar, name="gestionar"),
    path("trazabilidad/<int:expediente_id>/", views.trazabilidad, name="trazabilidad"),
]
