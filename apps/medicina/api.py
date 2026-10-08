"""
API REST de la consulta médica.

Endpoints:
- POST /api/v1/atenciones/medicina/          crear HC
- GET  /api/v1/atenciones/medicina/{id}/     ver HC (con triaje heredado)
- PATCH /api/v1/atenciones/medicina/{id}/    actualizar anamnesis/plan
- POST /api/v1/atenciones/medicina/{id}/diagnosticos/
- POST /api/v1/atenciones/medicina/{id}/receta/
- POST /api/v1/atenciones/medicina/{id}/ordenes-laboratorio/
- POST /api/v1/atenciones/medicina/{id}/cerrar/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.expediente.models import Expediente
from apps.farmacia import services as farmacia_services
from apps.laboratorio import services as lab_services
from apps.usuarios import rbac
from apps.usuarios.permissions import EsPersonalDeLaUnidad

from . import services
from .models import AtencionMedicina
from .serializers import (
    AgregarDiagnosticoSerializer,
    AtencionMedicinaSerializer,
    CrearAtencionMedicinaSerializer,
    DiagnosticoSerializer,
    EmitirRecetaSerializer,
    SolicitarExamenesSerializer,
)


class AtencionMedicinaViewSet(viewsets.ModelViewSet):
    queryset = AtencionMedicina.objects.select_related(
        "atencion__expediente__persona", "atencion__servicio", "atencion__profesional"
    )
    serializer_class = AtencionMedicinaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        """Filtrado RBAC: solo atenciones que el rol del usuario puede ver."""
        from apps.expediente.models import Atencion

        visibles = rbac.atenciones_visibles(self.request.user, Atencion.objects.all())
        return super().get_queryset().filter(atencion__in=visibles)

    def create(self, request, *args, **kwargs):
        s = CrearAtencionMedicinaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return Response(
                {"detalle": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            hc = services.crear_atencion_medicina(
                expediente=Expediente.objects.get(pk=s.validated_data["expediente"]),
                profesional=perfil,
                motivo=s.validated_data.get("motivo", ""),
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AtencionMedicinaSerializer(hc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def diagnosticos(self, request, pk=None):
        hc = self.get_object()
        s = AgregarDiagnosticoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            dx = services.agregar_diagnostico(
                hc.atencion,
                s.validated_data["cie10"],
                tipo=s.validated_data["tipo"],
                condicion=s.validated_data["condicion"],
                principal=s.validated_data["principal"],
                observacion=s.validated_data.get("observacion", ""),
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DiagnosticoSerializer(dx).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def receta(self, request, pk=None):
        hc = self.get_object()
        s = EmitirRecetaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            receta = farmacia_services.emitir_receta(
                hc.atencion, s.validated_data["items"], usuario=request.user
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "numero": receta.numero,
                "valida_hasta": receta.valida_hasta,
                "items": receta.detalles.count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="ordenes-laboratorio")
    def ordenes_laboratorio(self, request, pk=None):
        hc = self.get_object()
        s = SolicitarExamenesSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            orden = lab_services.crear_orden(
                hc.atencion,
                s.validated_data["examenes"],
                prioridad=s.validated_data["prioridad"],
                diagnostico_presuntivo=s.validated_data.get("diagnostico_presuntivo", ""),
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"id": orden.id, "estado": orden.estado, "examenes": orden.examenes.count()},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        hc = self.get_object()
        try:
            services.cerrar_atencion(hc.atencion, usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AtencionMedicinaSerializer(hc).data)
