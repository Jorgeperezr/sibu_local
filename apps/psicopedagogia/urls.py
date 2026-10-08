from django.urls import path

from . import views

app_name = "psicopedagogia"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("iniciar/<int:expediente_id>/", views.iniciar, name="iniciar"),
    path("ficha/<int:pk>/", views.ficha, name="ficha"),
]
