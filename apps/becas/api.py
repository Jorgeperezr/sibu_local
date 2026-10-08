"""
API REST de Becas (fase 1).

- GET/POST /api/v1/becas/beneficiarios/
- POST     /api/v1/becas/beneficiarios/{id}/seguimientos/
- POST     /api/v1/becas/beneficiarios/{id}/verificar-matricula/
- POST     /api/v1/becas/beneficiarios/{id}/estado/
- GET      /api/v1/becas/beneficiarios/vigentes/?periodo=N
- GET      /api/v1/becas/tipos/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import PeriodoAcademico
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import visible_para_personal

from . import services
from .models import BecaBeneficiario, TipoBeca
from .serializers import (
    BecaBeneficiarioSerializer,
    CambiarEstadoSerializer,
    RegistrarSeguimientoSerializer,
    SeguimientoBecaSerializer,
    TipoBecaSerializer,
)


class TipoBecaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoBeca.objects.all().order_by("nombre")
    serializer_class = TipoBecaSerializer
    permission_classes = [IsAuthenticated]


class BecaBeneficiarioViewSet(viewsets.ModelViewSet):
    queryset = (
        BecaBeneficiario.objects.filter(eliminado_en__isnull=True)
        .select_related("expediente__persona", "tipo_beca", "periodo_desde")
        .order_by("-creado_en")
    )
    serializer_class = BecaBeneficiarioSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        """Quién recibe una beca es dato socioeconómico de una persona."""
        return visible_para_personal(self.request.user, super().get_queryset())

    def perform_create(self, serializer):
        datos = serializer.validated_data
        try:
            services.registrar_beneficiario(
                expediente=datos["expediente"],
                tipo_beca=datos["tipo_beca"],
                periodo_desde=datos["periodo_desde"],
                periodo_hasta=datos.get("periodo_hasta"),
                profesional=getattr(self.request.user, "perfil", None),
                monto_o_porcentaje=datos.get("monto_o_porcentaje", ""),
                resolucion=datos.get("resolucion", ""),
                origen=datos.get("origen", BecaBeneficiario.Origen.MANUAL),
                id_externo=datos.get("id_externo", ""),
                usuario=self.request.user,
            )
        except ValidationError as exc:
            from rest_framework.exceptions import ValidationError as DRFError

            raise DRFError({"detail": exc.messages}) from exc

    @action(detail=True, methods=["post"])
    def seguimientos(self, request, pk=None):
        beneficiario = self.get_object()
        entrada = RegistrarSeguimientoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        periodo = PeriodoAcademico.objects.filter(pk=entrada.validated_data["periodo"]).first()
        if periodo is None:
            return Response({"detail": "Periodo no encontrado."}, status=404)
        try:
            seguimiento = services.registrar_seguimiento(
                beneficiario,
                periodo=periodo,
                tipo=entrada.validated_data["tipo"],
                detalle=entrada.validated_data["detalle"],
                profesional=request.user.perfil,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SeguimientoBecaSerializer(seguimiento).data, status=201)

    @action(detail=True, methods=["post"], url_path="verificar-matricula")
    def verificar_matricula(self, request, pk=None):
        beneficiario = self.get_object()
        periodo = PeriodoAcademico.objects.filter(vigente=True).first()
        if periodo is None:
            return Response({"detail": "No hay periodo vigente."}, status=400)
        seguimiento = services.verificar_matricula(beneficiario, periodo, request.user.perfil)
        return Response(SeguimientoBecaSerializer(seguimiento).data, status=201)

    @action(detail=True, methods=["post"])
    def estado(self, request, pk=None):
        beneficiario = self.get_object()
        entrada = CambiarEstadoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.cambiar_estado(
                beneficiario,
                entrada.validated_data["estado"],
                causal=entrada.validated_data["causal"],
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(beneficiario).data)

    @action(detail=False, methods=["get"])
    def vigentes(self, request):
        periodo_id = request.query_params.get("periodo")
        periodo = (
            PeriodoAcademico.objects.filter(pk=periodo_id).first()
            if periodo_id
            else PeriodoAcademico.objects.filter(vigente=True).first()
        )
        if periodo is None:
            return Response({"detail": "Periodo no encontrado."}, status=404)
        return Response(
            {
                "periodo": periodo.codigo,
                "total": services.beneficiarios_vigentes(periodo).count(),
                "por_tipo": services.resumen_por_tipo(periodo),
                "beneficiarios": BecaBeneficiarioSerializer(
                    services.beneficiarios_vigentes(periodo), many=True
                ).data,
            }
        )
