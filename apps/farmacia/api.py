"""
API REST de Farmacia.

- GET  /api/v1/farmacia/medicamentos/          catálogo con stock disponible
- GET  /api/v1/farmacia/lotes/                 inventario por lote
- POST /api/v1/farmacia/lotes/ingresar/        ingreso de stock
- GET  /api/v1/farmacia/recetas/pendientes/    cola de despacho
- POST /api/v1/farmacia/recetas/{id}/despachar-item/
- POST /api/v1/farmacia/recetas/{id}/despachar-todo/
- POST /api/v1/farmacia/recetas/{id}/anular/
- GET  /api/v1/farmacia/alertas/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import numeros
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import visible_para_personal

from . import services
from .models import Lote, Medicamento, Receta, RecetaDetalle
from .serializers import (
    AnularRecetaSerializer,
    DespacharItemSerializer,
    IngresoLoteSerializer,
    LoteSerializer,
    MedicamentoSerializer,
    MovimientoInventarioSerializer,
    RecetaSerializer,
)


def _perfil_o_none(request):
    return getattr(request.user, "perfil", None)


class MedicamentoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Medicamento.objects.filter(activo=True)
    serializer_class = MedicamentoSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["requiere_receta"]
    search_fields = ["codigo", "dci", "nombre_comercial"]


class LoteViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lote.objects.select_related("medicamento").order_by("fecha_caducidad")
    serializer_class = LoteSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["medicamento"]

    def get_queryset(self):
        """Inventario: no es de pacientes, pero tampoco es público."""
        return visible_para_personal(self.request.user, super().get_queryset())

    @action(detail=False, methods=["post"])
    def ingresar(self, request):
        s = IngresoLoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        perfil = _perfil_o_none(request)
        if perfil is None:
            return Response(
                {"detalle": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            lote = services.ingresar_lote(
                Medicamento.objects.get(pk=s.validated_data["medicamento"]),
                s.validated_data["numero_lote"],
                s.validated_data["cantidad"],
                s.validated_data["fecha_caducidad"],
                usuario=perfil,
                costo_unitario=s.validated_data.get("costo_unitario", 0),
                proveedor=s.validated_data.get("proveedor", ""),
                referencia_doc=s.validated_data.get("referencia_doc", ""),
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LoteSerializer(lote).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def movimientos(self, request, pk=None):
        """Bitácora del lote: permite reconstruir el saldo."""
        lote = self.get_object()
        movimientos = lote.movimientos.order_by("id")
        return Response(MovimientoInventarioSerializer(movimientos, many=True).data)


class RecetaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Receta.objects.select_related("atencion__expediente__persona").prefetch_related(
        "detalles__medicamento", "detalles__dispensaciones__lote"
    )
    serializer_class = RecetaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["estado"]

    def get_queryset(self):
        """Una receta lleva el paciente y qué se le prescribió."""
        return visible_para_personal(
            self.request.user, super().get_queryset(), campo_servicio="atencion__servicio"
        )

    @action(detail=False, methods=["get"])
    def pendientes(self, request):
        """Cola de despacho: recetas vigentes sin despachar del todo."""
        return Response(RecetaSerializer(services.recetas_pendientes(), many=True).data)

    @action(detail=True, methods=["post"], url_path="despachar-item")
    def despachar_item(self, request, pk=None):
        receta = self.get_object()
        s = DespacharItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        perfil = _perfil_o_none(request)
        if perfil is None:
            return Response(
                {"detalle": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            detalle = RecetaDetalle.objects.get(pk=s.validated_data["detalle"], receta=receta)
            dispensaciones = services.despachar_item(
                detalle, s.validated_data["cantidad"], usuario=perfil
            )
        except RecetaDetalle.DoesNotExist:
            return Response(
                {"detalle": "El ítem no pertenece a esta receta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        receta.refresh_from_db()
        return Response(
            {
                "lotes_consumidos": [
                    {
                        "lote": d.lote.numero_lote,
                        "cantidad": d.cantidad_despachada,
                        "caducidad": d.lote.fecha_caducidad,
                    }
                    for d in dispensaciones
                ],
                "receta": RecetaSerializer(receta).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="despachar-todo")
    def despachar_todo(self, request, pk=None):
        receta = self.get_object()
        perfil = _perfil_o_none(request)
        if perfil is None:
            return Response(
                {"detalle": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            resumen = services.despachar_receta_completa(receta, usuario=perfil)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        receta.refresh_from_db()
        return Response({"resumen": resumen, "receta": RecetaSerializer(receta).data})

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        receta = self.get_object()
        s = AnularRecetaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.anular_receta(receta, s.validated_data["motivo"])
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RecetaSerializer(receta).data)


class AlertasFarmaciaView(APIView):
    """Alertas de gestión: stock bajo mínimo y lotes próximos a caducar."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # `int(...)` sin red: `?dias=abc` devolvía un 500. Un parámetro de la
        # URL puede traer cualquier cosa, y una cifra ilegible es una consulta
        # mal escrita, no una avería del servidor.
        dias = numeros.a_entero(request.query_params.get("dias"), 90)
        return Response(
            {
                "stock_bajo": [
                    {
                        "medicamento": str(a["medicamento"]),
                        "medicamento_id": a["medicamento"].id,
                        "disponible": a["disponible"],
                        "minimo": a["minimo"],
                        "critico": a["critico"],
                    }
                    for a in services.alertas_stock()
                ],
                "por_caducar": [
                    {
                        "medicamento": str(lote.medicamento),
                        "lote": lote.numero_lote,
                        "caducidad": lote.fecha_caducidad,
                        "cantidad": lote.cantidad_actual,
                    }
                    for lote in services.alertas_caducidad(dias)
                ],
            }
        )
