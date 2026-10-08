from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    path("", views.mi_agenda, name="mi_agenda"),
    path("calendario/", views.calendario, name="calendario"),
    path("mi-horario/", views.mi_horario, name="mi_horario"),
    path("reservar/", views.reservar, name="reservar"),
    path("<int:pk>/estado/", views.cambiar_estado_web, name="cambiar_estado"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/reprogramar/", views.reprogramar, name="reprogramar"),
    path("_persona/", views.buscar_persona_json, name="_persona"),
    path("_profesionales/", views.profesionales_json, name="_profesionales"),
]
