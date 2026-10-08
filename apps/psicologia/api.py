"""
API REST de Psicología.

- GET  /api/v1/psicologia/escalas/                      catálogo de escalas
- POST /api/v1/psicologia/fichas/                        abrir proceso
- GET  /api/v1/psicologia/fichas/                        mis fichas (solo del servicio)
- GET  /api/v1/psicologia/fichas/{id}/                   ver ficha
- POST /api/v1/psicologia/fichas/{id}/sesiones/          registrar sesión
- POST /api/v1/psicologia/fichas/{id}/escalas/           aplicar escala
- POST /api/v1/psicologia/fichas/{id}/riesgo/            marcar riesgo
- POST /api/v1/psicologia/fichas/{id}/cerrar/            cerrar proceso

SELLO: la API es una superficie nueva. Se protege por partida doble:
  1. `get_queryset` filtra con `rbac.atenciones_visibles` -> la lista nunca
     incluye fichas de otros; para quien no es del servicio, sale vacía.
  2. `PuedeVerAtencion` aplica `rbac.puede_ver_atencion` al objeto -> el
     detalle devuelve 404/403 aunque alguien adivine el id.

Un fallo en cualquiera de las dos capas no basta para filtrar contenido.
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
from .models import EscalaPsicometrica, FichaPsicologica
from .serializers import (
    AplicarEscalaSerializer,
    CerrarProcesoSerializer,
    CrearFichaPsicologicaSerializer,
    EscalaPsicometricaSerializer,
    FichaPsicologicaSerializer,
    MarcarRiesgoSerializer,
    RegistrarSesionSerializer,
)


class EscalaPsicometricaViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo de escalas. No contiene datos de pacientes."""

    queryset = EscalaPsicometrica.objects.filter(activo=True)
    serializer_class = EscalaPsicometricaSerializer
    permission_classes = [IsAuthenticated]


class FichaPsicologicaViewSet(viewsets.ModelViewSet):
    # El orden explícito es necesario: sin él la paginación puede repetir u
    # omitir registros entre páginas (UnorderedObjectListWarning).
    queryset = FichaPsicologica.objects.select_related(
        "atencion__expediente__persona", "atencion__servicio"
    ).order_by("-atencion__fecha_hora")
    serializer_class = FichaPsicologicaSerializer
    permission_classes = [IsAuthenticated, PuedeVerAtencion, EsPersonalDeLaUnidad]

    def get_queryset(self):
        # Capa 1: solo lo que el RBAC deja ver. Para quien no es de Psicología
        # esto ya devuelve vacío.
        visibles = rbac.atenciones_visibles(self.request.user, Atencion.objects.all())
        return super().get_queryset().filter(atencion__in=visibles)

    def create(self, request, *args, **kwargs):
        entrada = CrearFichaPsicologicaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return Response(
                {"detail": "El usuario no tiene perfil profesional."},
                status=status.HTTP_403_FORBIDDEN,
            )
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

        ficha.modalidad = entrada.validated_data["modalidad"]
        ficha.save(update_fields=["modalidad"])
        return Response(self.get_serializer(ficha).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def sesiones(self, request, pk=None):
        ficha = self.get_object()  # aplica PuedeVerAtencion
        entrada = RegistrarSesionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            sesion = services.registrar_sesion(
                ficha, profesional=request.user.perfil, **entrada.validated_data
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        from .serializers import SesionPsicologicaSerializer

        return Response(SesionPsicologicaSerializer(sesion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def escalas(self, request, pk=None):
        ficha = self.get_object()
        entrada = AplicarEscalaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            aplicacion = services.aplicar_escala(
                ficha,
                entrada.validated_data["escala"],
                entrada.validated_data["puntaje"],
                aplicado_por=getattr(request.user, "perfil", None),
            )
        except EscalaPsicometrica.DoesNotExist:
            return Response({"detail": "Escala no encontrada o inactiva."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        from .serializers import AplicacionEscalaSerializer

        ficha.refresh_from_db()
        datos = AplicacionEscalaSerializer(aplicacion).data
        datos["riesgo_nivel"] = ficha.riesgo_nivel
        return Response(datos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def riesgo(self, request, pk=None):
        ficha = self.get_object()
        entrada = MarcarRiesgoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.marcar_riesgo(
                ficha, entrada.validated_data["nivel"], entrada.validated_data["nota"]
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(ficha).data)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        ficha = self.get_object()
        entrada = CerrarProcesoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            services.cerrar_proceso(ficha, entrada.validated_data["estado"])
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(ficha).data)
