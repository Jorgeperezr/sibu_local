"""
API REST de Laboratorio.

- GET  /api/v1/laboratorio/ordenes/           bandeja (filtrable)
- GET  /api/v1/laboratorio/ordenes/pendientes/
- POST /api/v1/laboratorio/ordenes/{id}/tomar-muestra/
- POST /api/v1/laboratorio/ordenes/{id}/rechazar-muestra/
- POST /api/v1/laboratorio/ordenes/{id}/resultados/
- POST /api/v1/laboratorio/ordenes/{id}/completar/
- POST /api/v1/laboratorio/ordenes/{id}/validar/
- POST /api/v1/laboratorio/ordenes/{id}/publicar/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import visible_para_personal

from . import services
from .models import Examen, OrdenExamen, OrdenLaboratorio, ParametroExamen
from .serializers import (
    ExamenSerializer,
    OrdenLaboratorioSerializer,
    PublicarSerializer,
    RechazarMuestraSerializer,
    RegistrarResultadoSerializer,
    ResultadoParametroSerializer,
    TomarMuestraSerializer,
)


def _perfil_o_error(request):
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise ValidationError("El usuario no tiene perfil profesional asignado.")
    return perfil


class ExamenViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo de exámenes con sus parámetros y valores de referencia."""

    queryset = Examen.objects.filter(activo=True).prefetch_related("parametros")
    serializer_class = ExamenSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["perfil"]


class OrdenLaboratorioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdenLaboratorio.objects.select_related(
        "atencion__expediente__persona"
    ).prefetch_related("examenes__resultados")
    serializer_class = OrdenLaboratorioSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["estado", "prioridad", "enviado_correo_paciente"]

    def get_queryset(self):
        """Una orden lleva el paciente y qué se le pidió: es contenido clínico."""
        return visible_para_personal(
            self.request.user, super().get_queryset(), campo_servicio="atencion__servicio"
        )

    @action(detail=False, methods=["get"])
    def pendientes(self, request):
        """Cola de trabajo: órdenes por procesar, urgentes primero."""
        ordenes = services.ordenes_pendientes()
        return Response(OrdenLaboratorioSerializer(ordenes, many=True).data)

    @action(detail=True, methods=["post"], url_path="tomar-muestra")
    def tomar_muestra(self, request, pk=None):
        orden = self.get_object()
        s = TomarMuestraSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            orden = services.tomar_muestra(
                orden,
                _perfil_o_error(request),
                tipo_muestra=s.validated_data.get("tipo_muestra", ""),
                codigo_barras=s.validated_data.get("codigo_barras", ""),
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrdenLaboratorioSerializer(orden).data)

    @action(detail=True, methods=["post"], url_path="rechazar-muestra")
    def rechazar_muestra(self, request, pk=None):
        orden = self.get_object()
        s = RechazarMuestraSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            orden = services.rechazar_muestra(orden, s.validated_data["motivo"])
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrdenLaboratorioSerializer(orden).data)

    @action(detail=True, methods=["post"])
    def resultados(self, request, pk=None):
        orden = self.get_object()
        s = RegistrarResultadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            orden_examen = OrdenExamen.objects.get(pk=s.validated_data["orden_examen"], orden=orden)
            resultado = services.registrar_resultado(
                orden_examen,
                ParametroExamen.objects.get(pk=s.validated_data["parametro"]),
                s.validated_data["valor"],
                registrado_por=_perfil_o_error(request),
                observacion=s.validated_data.get("observacion", ""),
            )
        except OrdenExamen.DoesNotExist:
            return Response(
                {"detalle": "El examen no pertenece a esta orden."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ResultadoParametroSerializer(resultado).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def completar(self, request, pk=None):
        """El técnico declara terminado el registro de resultados."""
        orden = self.get_object()
        try:
            orden = services.marcar_resultado_completo(orden)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrdenLaboratorioSerializer(orden).data)

    @action(detail=True, methods=["post"])
    def validar(self, request, pk=None):
        orden = self.get_object()
        try:
            orden = services.validar_orden(orden, _perfil_o_error(request))
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrdenLaboratorioSerializer(orden).data)

    @action(detail=True, methods=["post"])
    def publicar(self, request, pk=None):
        orden = self.get_object()
        s = PublicarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            orden = services.publicar_orden(orden, enviar_correo=s.validated_data["enviar_correo"])
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrdenLaboratorioSerializer(orden).data)
