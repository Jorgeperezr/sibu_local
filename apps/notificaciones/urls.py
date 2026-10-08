from django.urls import path

from . import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("<int:pk>/leer/", views.leer, name="leer"),
    path("leer-todas/", views.leer_todas, name="leer_todas"),
]
