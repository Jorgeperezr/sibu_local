from django.urls import path

from . import views

app_name = "becas"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("ficha/<int:pk>/", views.ficha, name="ficha"),
]
