"""
API REST de Derivaciones.

- GET  /api/v1/derivaciones/                       mis derivaciones
- GET  /api/v1/derivaciones/bandeja/?servicio=N    bandeja de entrada
- POST /api/v1/derivaciones/                       derivar
- POST /api/v1/derivaciones/{id}/aceptar/
- POST /api/v1/derivaciones/{id}/rechazar/
- POST /api/v1/derivaciones/{id}/agendar/
- POST /api/v1/derivaciones/{id}/atender/
- POST /api/v1/derivaciones/{id}/retornar/
- GET  /api/v1/derivaciones/trazabilidad/?expediente=N
- POST /api/v1/referencias-externas/
- POST /api/v1/referencias-externas/{id}/contrarreferencia/
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import Servicio
from apps.core.parametros import id_de_consulta
from apps.expediente.models import Atencion, Expediente
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import puede_ver_expediente, servicios_del_usuario

from . import services
from .models import Derivacion, ReferenciaExterna
from .serializers import (
    AtenderSerializer,
    ContrarreferenciaSerializer,
    CrearDerivacionSerializer,
    CrearReferenciaSerializer,
    DerivacionSerializer,
    RechazarSerializer,
    ReferenciaExternaSerializer,
    RegistrarContrarreferenciaSerializer,
    RetornarSerializer,
)


class DerivacionViewSet(viewsets.ModelViewSet):
    queryset = Derivacion.objects.select_related(
        "atencion_origen__expediente__persona",
        "atencion_origen__servicio",
        "servicio_destino",
    ).order_by("-creado_en")
    serializer_class = DerivacionSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        """
        El profesional ve las derivaciones que emitió su servicio y las que
        recibe. No hay filtrado por contenido porque la derivación en sí no lo
        contiene: el retorno de un servicio confidencial ya viene saneado.
        """
        mis_servicios = servicios_del_usuario(self.request.user)
        qs = super().get_queryset()
        return qs.filter(atencion_origen__servicio_id__in=mis_servicios) | qs.filter(
            servicio_destino_id__in=mis_servicios
        )

    def create(self, request, *args, **kwargs):
        entrada = CrearDerivacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            atencion = Atencion.objects.get(pk=entrada.validated_data["atencion_origen"])
            destino = Servicio.objects.get(pk=entrada.validated_data["servicio_destino"])
        except (Atencion.DoesNotExist, Servicio.DoesNotExist):
            return Response({"detail": "Atención o servicio no encontrado."}, status=404)

        if atencion.servicio_id not in servicios_del_usuario(request.user):
            return Response(
                {"detail": "No puede derivar desde un servicio que no es suyo."}, status=403
            )
        try:
            derivacion = services.derivar(
                atencion,
                destino,
                motivo=entrada.validated_data["motivo"],
                resumen=entrada.validated_data["resumen"],
                prioridad=entrada.validated_data["prioridad"],
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(derivacion).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def bandeja(self, request):
        servicio_id = id_de_consulta(request.query_params.get("servicio"), "servicio")
        if not servicio_id:
            return Response({"detail": "Indique el parámetro 'servicio'."}, status=400)
        # `int(servicio_id)` sin red devolvía un 500 con `?servicio=abc`.
        if servicio_id not in servicios_del_usuario(request.user):
            return Response({"detail": "Ese servicio no es suyo."}, status=403)
        servicio = Servicio.objects.filter(pk=servicio_id).first()
        if servicio is None:
            return Response({"detail": "Servicio no encontrado."}, status=404)
        return Response(DerivacionSerializer(services.bandeja_entrada(servicio), many=True).data)

    def _accion(self, request, fn, serializer_cls=None, **kwargs):
        derivacion = self.get_object()
        try:
            fn(derivacion, **kwargs)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(derivacion).data)

    @action(detail=True, methods=["post"])
    def aceptar(self, request, pk=None):
        return self._accion(request, services.aceptar)

    @action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        entrada = RechazarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return self._accion(request, services.rechazar, motivo=entrada.validated_data["motivo"])

    @action(detail=True, methods=["post"])
    def agendar(self, request, pk=None):
        return self._accion(request, services.marcar_agendada)

    @action(detail=True, methods=["post"])
    def atender(self, request, pk=None):
        entrada = AtenderSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        derivacion = self.get_object()
        try:
            atencion = Atencion.objects.get(pk=entrada.validated_data["atencion_destino"])
            services.atender(derivacion, atencion)
        except Atencion.DoesNotExist:
            return Response({"detail": "Atención no encontrada."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(derivacion).data)

    @action(detail=True, methods=["post"])
    def retornar(self, request, pk=None):
        entrada = RetornarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return self._accion(request, services.retornar, texto=entrada.validated_data["texto"])

    @action(detail=False, methods=["get"])
    def trazabilidad(self, request):
        """
        El recorrido del paciente entre servicios.

        No comprobaba nada: bastaba con estar autenticado y pasar cualquier id
        de expediente. La misma puerta que la vista web tenía abierta, por
        duplicado. El filtrado de lo confidencial lo hace el servicio, que sabe
        a qué servicios pertenece quien pregunta.
        """
        expediente_id = id_de_consulta(request.query_params.get("expediente"), "expediente")
        if not expediente_id:
            return Response({"detail": "Indique el parámetro 'expediente'."}, status=400)
        if not puede_ver_expediente(request.user):
            return Response(
                {"detail": "No tiene permisos para consultar expedientes."},
                status=status.HTTP_403_FORBIDDEN,
            )
        expediente = Expediente.objects.filter(pk=expediente_id).first()
        if expediente is None:
            return Response({"detail": "Expediente no encontrado."}, status=404)
        return Response(services.trazabilidad(expediente, request.user))


class ReferenciaExternaViewSet(viewsets.ModelViewSet):
    queryset = ReferenciaExterna.objects.select_related("atencion__servicio").order_by("-creado_en")
    serializer_class = ReferenciaExternaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        mis_servicios = servicios_del_usuario(self.request.user)
        return super().get_queryset().filter(atencion__servicio_id__in=mis_servicios)

    def create(self, request, *args, **kwargs):
        entrada = CrearReferenciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            atencion = Atencion.objects.get(pk=entrada.validated_data["atencion"])
            referencia = services.referir_a_externo(
                atencion,
                institucion=entrada.validated_data["institucion"],
                motivo=entrada.validated_data["motivo"],
                especialidad=entrada.validated_data["especialidad"],
                resumen_clinico=entrada.validated_data["resumen_clinico"],
                usuario=request.user,
            )
        except Atencion.DoesNotExist:
            return Response({"detail": "Atención no encontrada."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(referencia).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def contrarreferencia(self, request, pk=None):
        referencia = self.get_object()
        entrada = RegistrarContrarreferenciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            contra = services.registrar_contrarreferencia(referencia, **entrada.validated_data)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ContrarreferenciaSerializer(contra).data, status=status.HTTP_201_CREATED)
