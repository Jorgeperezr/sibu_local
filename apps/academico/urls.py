from django.urls import path

from . import views

app_name = "academico"

urlpatterns = [
    path("carga/asistente/", views.asistente, name="asistente"),
    path("carga/plantilla.csv", views.plantilla, name="plantilla"),
    path("carga/diccionario/", views.diccionario, name="diccionario"),
    path("padron/", views.padron, name="padron"),
    path("autocompletar/", views.autocompletar, name="autocompletar"),
]
