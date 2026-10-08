from django.urls import path

from . import views

app_name = "odontologia"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("iniciar/<int:expediente_id>/", views.iniciar_consulta, name="iniciar"),
    path("consulta/<int:pk>/", views.consulta, name="consulta"),
]
