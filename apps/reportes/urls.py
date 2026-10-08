from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.tablero, name="tablero"),
    path("exportar/", views.exportar_csv, name="exportar"),
    path("exportar/pdf/", views.exportar_pdf, name="exportar_pdf"),
    path("exportar/hoja/", views.exportar_hoja, name="exportar_hoja"),
    path("informe-servicio/", views.informe_servicio, name="informe_servicio"),
    path("informe-servicio/pdf/", views.informe_servicio_pdf, name="informe_servicio_pdf"),
    path("informe-servicio/xlsx/", views.informe_servicio_xlsx, name="informe_servicio_xlsx"),
]
