"""
API REST de Odontología.

- POST /api/v1/atenciones/odontologia/              crear HC
- GET  /api/v1/atenciones/odontologia/{id}/         ver HC + odontograma vigente
- POST /api/v1/atenciones/odontologia/{id}/piezas/  registrar estado de pieza
- POST /api/v1/atenciones/odontologia/{id}/procedimientos/
- POST /api/v1/atenciones/odontologia/{id}/cerrar/
- GET  /api/v1/odontologia/catalogo/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.expediente.models import Atencion, Expediente
from apps.usuarios import rbac
from apps.usuarios.permissions import EsPersonalDeLaUnidad

from . import services
from .models import AtencionOdontologia, CatalogoProcedimiento
from .serializers import (
    AtencionOdontologiaSerializer,
    CatalogoProcedimientoSerializer,
    CrearAtencionOdontologiaSerializer,
    EjecutarProcedimientoSerializer,
    OdontogramaDetalleSerializer,
    ProcedimientoSerializer,
    RegistrarPiezaSerializer,
)


class CatalogoProcedimientoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CatalogoProcedimiento.objects.filter(activo=True)
    serializer_class = CatalogoProcedimientoSerializer
    permission_classes = [IsAuthenticated]


class AtencionOdontologiaViewSet(viewsets.ModelViewSet):
    queryset = AtencionOdontologia.objects.select_related(
        "atencion__expediente__persona", "atencion__servicio"
    )
    serializer_class = AtencionOdontologiaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        """Filtrado RBAC: solo atenciones visibles para el rol del usuario."""
        visibles = rbac.atenciones_visibles(self.request.user, Atencion.objects.all())
        return super().get_queryset().filter(atencion__in=visibles)

    def create(self, request, *args, **kwargs):
        s = CrearAtencionOdontologiaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return Response(
                {"detalle": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            hc = services.crear_atencion_odontologia(
                expediente=Expediente.objects.get(pk=s.validated_data["expediente"]),
                profesional=perfil,
                motivo=s.validated_data.get("motivo", ""),
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AtencionOdontologiaSerializer(hc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def piezas(self, request, pk=None):
        hc = self.get_object()
        s = RegistrarPiezaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            registro = services.registrar_estado_pieza(
                hc.atencion,
                s.validated_data["pieza_fdi"],
                s.validated_data["estado"],
                superficie=s.validated_data.get("superficie", ""),
                tipo=s.validated_data["tipo"],
                observacion=s.validated_data.get("observacion", ""),
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OdontogramaDetalleSerializer(registro).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def procedimientos(self, request, pk=None):
        hc = self.get_object()
        s = EjecutarProcedimientoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        perfil = getattr(request.user, "perfil", None)
        try:
            procedimiento = services.ejecutar_procedimiento(
                hc.atencion,
                s.validated_data["catalogo"],
                ejecutado_por=perfil,
                pieza_fdi=s.validated_data.get("pieza_fdi", ""),
                superficie=s.validated_data.get("superficie", ""),
                observacion=s.validated_data.get("observacion", ""),
            )
        except CatalogoProcedimiento.DoesNotExist:
            return Response(
                {"detalle": "Procedimiento no encontrado en el catálogo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProcedimientoSerializer(procedimiento).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        hc = self.get_object()
        try:
            services.cerrar_atencion(hc.atencion, usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        hc.refresh_from_db()
        return Response(AtencionOdontologiaSerializer(hc).data)
