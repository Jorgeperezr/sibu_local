"""
API REST de Talleres.

- GET/POST /api/v1/talleres/
- POST     /api/v1/talleres/{id}/participantes/
- POST     /api/v1/talleres/{id}/ejecutar/
- POST     /api/v1/talleres/{id}/cerrar/
- GET      /api/v1/talleres/cobertura/?periodo=2026-1
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.expediente.models import Expediente
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import servicios_del_usuario

from . import services
from .models import Taller
from .serializers import (
    RegistrarParticipanteSerializer,
    TallerParticipanteSerializer,
    TallerSerializer,
)


class TallerViewSet(viewsets.ModelViewSet):
    queryset = (
        Taller.objects.filter(eliminado_en__isnull=True)
        .select_related("servicio", "seccion", "responsable__usuario")
        .prefetch_related("participantes")
        .order_by("-fecha")
    )
    serializer_class = TallerSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        # Un taller no es contenido clínico, pero sí es trabajo de un servicio:
        # cada quien ve los suyos.
        return (
            super().get_queryset().filter(servicio_id__in=servicios_del_usuario(self.request.user))
        )

    def perform_create(self, serializer):
        datos = serializer.validated_data
        try:
            services.crear_taller(
                servicio=datos["servicio"],
                responsable=getattr(self.request.user, "perfil", None),
                tema=datos["tema"],
                fecha=datos["fecha"],
                usuario=self.request.user,
                objetivo=datos.get("objetivo", ""),
                tipo=datos.get("tipo", Taller.Tipo.PREVENTIVO),
                modalidad=datos.get("modalidad", "presencial"),
                lugar=datos.get("lugar", ""),
                poblacion_objetivo=datos.get("poblacion_objetivo", {}),
            )
        except ValidationError as exc:
            from rest_framework.exceptions import ValidationError as DRFError

            raise DRFError({"detail": exc.messages}) from exc

    @action(detail=True, methods=["post"])
    def participantes(self, request, pk=None):
        taller = self.get_object()
        entrada = RegistrarParticipanteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        expediente = None
        if entrada.validated_data.get("expediente"):
            expediente = Expediente.objects.filter(pk=entrada.validated_data["expediente"]).first()
            if expediente is None:
                return Response({"detail": "Expediente no encontrado."}, status=404)
        try:
            participante = services.registrar_participante(
                taller,
                cedula=entrada.validated_data.get("cedula", ""),
                expediente=expediente,
                asistio=entrada.validated_data["asistio"],
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TallerParticipanteSerializer(participante).data, status=201)

    @action(detail=True, methods=["post"])
    def ejecutar(self, request, pk=None):
        taller = self.get_object()
        try:
            services.marcar_ejecutado(taller, usuario=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(taller).data)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        taller = self.get_object()
        try:
            services.cerrar_taller(taller, usuario=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(taller).data)

    @action(detail=False, methods=["get"])
    def cobertura(self, request):
        return Response(services.cobertura(request.query_params.get("periodo", "")))
