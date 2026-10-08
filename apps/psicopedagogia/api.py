"""
API REST de Psicopedagogía.

- POST /api/v1/psicopedagogia/fichas/                    abrir ficha
- GET  /api/v1/psicopedagogia/fichas/{id}/               ver ficha
- POST /api/v1/psicopedagogia/fichas/{id}/seguimientos/  registrar seguimiento
- GET  /api/v1/psicopedagogia/fichas/{id}/impacto/       variación del promedio
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.expediente.models import Atencion, Expediente
from apps.usuarios import rbac
from apps.usuarios.permissions import EsPersonalDeLaUnidad, PuedeVerAtencion

from . import services
from .models import FichaPsicopedagogica
from .serializers import (
    CrearFichaPsicopedagogicaSerializer,
    FichaPsicopedagogicaSerializer,
    RegistrarSeguimientoSerializer,
    SeguimientoAcademicoSerializer,
)


class FichaPsicopedagogicaViewSet(viewsets.ModelViewSet):
    queryset = FichaPsicopedagogica.objects.select_related(
        "atencion__expediente__persona"
    ).order_by("-atencion__fecha_hora")
    serializer_class = FichaPsicopedagogicaSerializer
    permission_classes = [IsAuthenticated, PuedeVerAtencion, EsPersonalDeLaUnidad]

    def get_queryset(self):
        visibles = rbac.atenciones_visibles(self.request.user, Atencion.objects.all())
        return super().get_queryset().filter(atencion__in=visibles)

    def create(self, request, *args, **kwargs):
        entrada = CrearFichaPsicopedagogicaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return Response({"detail": "El usuario no tiene perfil."}, status=403)
        try:
            expediente = Expediente.objects.get(pk=entrada.validated_data["expediente"])
            ficha = services.crear_ficha(
                expediente=expediente,
                profesional=perfil,
                motivo=entrada.validated_data["motivo"],
                usuario=request.user,
            )
        except Expediente.DoesNotExist:
            return Response({"detail": "Expediente no encontrado."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(ficha).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def seguimientos(self, request, pk=None):
        ficha = self.get_object()
        entrada = RegistrarSeguimientoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            seguimiento = services.registrar_seguimiento(
                ficha, entrada.validated_data.pop("periodo"), **entrada.validated_data
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SeguimientoAcademicoSerializer(seguimiento).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"])
    def impacto(self, request, pk=None):
        ficha = self.get_object()
        return Response(services.impacto(ficha))
