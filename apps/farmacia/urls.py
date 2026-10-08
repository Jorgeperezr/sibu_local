from django.urls import path

from . import views

app_name = "farmacia"

urlpatterns = [
    path("", views.mostrador, name="mostrador"),
    path("inventario/", views.inventario, name="inventario"),
    path("receta/<int:pk>/", views.despachar, name="despachar"),
]
