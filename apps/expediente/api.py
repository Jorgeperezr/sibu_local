"""
API del expediente único con filtrado RBAC.

- PersonaViewSet: búsqueda por cédula.
- ExpedienteViewSet: detalle + línea de tiempo filtrada; acción break-the-glass.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios import rbac
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import visible_para_personal
from apps.usuarios.services import registrar_break_glass

from .models import Expediente, Persona
from .selectors import timeline
from .serializers import (
    AtencionResumenSerializer,
    BreakGlassSerializer,
    ExpedienteSerializer,
    PersonaSerializer,
)
from .services import resolver_por_cedula


class PersonaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Persona.objects.all()
    serializer_class = PersonaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    lookup_field = "cedula"

    def get_queryset(self):
        """La lista era el padrón entero: nombre y cédula de cada persona atendida."""
        return visible_para_personal(self.request.user, super().get_queryset())

    def retrieve(self, request, cedula=None):
        """
        Resuelve por cédula (base local o proveedor académico).

        La comprobación no es cosmética: `resolver_por_cedula` consulta la
        fuente institucional y CREA la persona y su expediente si no existían.
        Sin ella, cualquiera con sesión abría expediente a quien quisiera con
        solo teclear una cédula. Es el defecto que ya se corrigió en la vista
        web `buscar` y que seguía vivo por aquí.
        """
        if not rbac.puede_ver_expediente(request.user):
            return Response(
                {"detalle": "No tiene permisos para consultar expedientes."},
                status=status.HTTP_403_FORBIDDEN,
            )
        resultado = resolver_por_cedula(cedula, usuario=request.user)
        if resultado is None:
            return Response(
                {"detalle": "No existe en la base institucional. Registre como externo."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "persona": PersonaSerializer(resultado["persona"]).data,
                "expediente_id": resultado["expediente"].id if resultado["expediente"] else None,
                "institucional": resultado["institucional"],
            }
        )


class ExpedienteViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Expediente.objects.select_related("persona")
    serializer_class = ExpedienteSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        """`retrieve` ya lo comprobaba; `list` se quedó sin comprobar nada."""
        return visible_para_personal(self.request.user, super().get_queryset())

    def retrieve(self, request, *args, **kwargs):
        if not rbac.puede_ver_expediente(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """Línea de tiempo de atenciones visibles para el rol del usuario."""
        expediente = self.get_object()
        break_glass = request.query_params.get("break_glass") == "1"
        atenciones = timeline(expediente, request.user, break_glass=break_glass)
        return Response(AtencionResumenSerializer(atenciones, many=True).data)

    @action(detail=True, methods=["post"])
    def break_glass(self, request, pk=None):
        """Registra un acceso de emergencia justificado y devuelve la línea de tiempo ampliada."""
        expediente = self.get_object()
        serializer = BreakGlassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registrar_break_glass(
            request.user,
            expediente.id,
            serializer.validated_data["motivo"],
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        atenciones = timeline(expediente, request.user, break_glass=True)
        return Response(
            {
                "detalle": "Acceso de emergencia registrado y auditado.",
                "atenciones": AtencionResumenSerializer(atenciones, many=True).data,
            }
        )
