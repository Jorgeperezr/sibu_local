"""
API REST de citas.

Endpoints principales:
- GET/POST /api/v1/citas/
- POST /api/v1/citas/{id}/reprogramar/
- POST /api/v1/citas/{id}/cancelar/
- POST /api/v1/citas/{id}/cambiar_estado/
- GET  /api/v1/citas/disponibilidad/?profesional=&servicio=&fecha=
"""

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import Servicio
from apps.core.parametros import id_de_consulta
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional
from apps.usuarios.permissions import EsPersonalDeLaUnidad
from apps.usuarios.rbac import visible_para_personal

from . import services
from .models import Agenda, BloqueoAgenda, Cita
from .selectors import citas_visibles, proximas_del_expediente
from .serializers import (
    AgendaSerializer,
    BloqueoAgendaSerializer,
    CambioEstadoSerializer,
    CancelacionSerializer,
    CitaSerializer,
    DisponibilidadQuerySerializer,
    ReprogramacionSerializer,
    ReservaCitaSerializer,
)


class AgendaViewSet(viewsets.ModelViewSet):
    queryset = Agenda.objects.select_related("profesional__usuario", "servicio")
    serializer_class = AgendaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["profesional", "servicio", "dia_semana", "activa"]

    def get_queryset(self):
        """Quién atiende, cuándo y en qué servicio: operación interna."""
        return visible_para_personal(
            self.request.user, super().get_queryset(), campo_servicio="servicio"
        )


class BloqueoAgendaViewSet(viewsets.ModelViewSet):
    queryset = BloqueoAgenda.objects.all()
    serializer_class = BloqueoAgendaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["profesional"]

    def get_queryset(self):
        """Igual que la agenda de la que cuelga."""
        return visible_para_personal(self.request.user, super().get_queryset())


class CitaViewSet(viewsets.ModelViewSet):
    queryset = Cita.objects.select_related(
        "expediente__persona", "servicio", "profesional__usuario"
    )
    serializer_class = CitaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]
    filterset_fields = ["servicio", "profesional", "estado", "expediente"]

    def get_queryset(self):
        """
        Sin esto la lista era la tabla entera, y con `servicio` entre los
        filtros bastaba una petición —`?servicio=<psicología>`— para sacar el
        nombre, la cédula y el motivo de cada paciente del servicio sellado.
        Filtrar aquí cubre también el detalle por id: lo que no está en el
        queryset devuelve 404 aunque se adivine el número.
        """
        return citas_visibles(self.request.user, super().get_queryset()).distinct()

    def create(self, request, *args, **kwargs):
        serializer = ReservaCitaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            cita = services.reservar_cita(
                expediente=Expediente.objects.get(pk=data["expediente"]),
                servicio=Servicio.objects.get(pk=data["servicio"]),
                profesional=PerfilProfesional.objects.get(pk=data["profesional"]),
                fecha_hora=data["fecha_hora"],
                duracion_min=data.get("duracion_min"),
                motivo=data.get("motivo", ""),
                origen=data.get("origen", Cita.Origen.VENTANILLA),
                usuario=request.user if request.user.is_authenticated else None,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reprogramar(self, request, pk=None):
        cita = self.get_object()
        s = ReprogramacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            nueva = services.reprogramar(
                cita,
                s.validated_data["fecha_hora"],
                motivo_reprogramacion=s.validated_data.get("motivo", ""),
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(nueva).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        cita = self.get_object()
        s = CancelacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.cancelar(cita, motivo=s.validated_data["motivo"], usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data)

    @action(detail=True, methods=["post"], url_path="cambiar_estado")
    def cambiar_estado(self, request, pk=None):
        cita = self.get_object()
        s = CambioEstadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.cambiar_estado(cita, s.validated_data["estado"], usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data)

    @action(detail=False, methods=["get"])
    def disponibilidad(self, request):
        s = DisponibilidadQuerySerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        turnos = services.turnos_disponibles(
            PerfilProfesional.objects.get(pk=s.validated_data["profesional"]),
            Servicio.objects.get(pk=s.validated_data["servicio"]),
            s.validated_data["fecha"],
        )
        # La etiqueta la compone el servidor. El navegador la sacaba de
        # `toLocaleString`, que usa la zona horaria DEL EQUIPO: en uno mal
        # configurado el desplegable ofrecía «02:00 p. m.» para el turno de las
        # 09:00 y, al guardar, el aviso confirmaba «09:00». La misma cita con
        # dos horas distintas en la misma pantalla, y quien elige no tiene cómo
        # saber cuál es la buena. La agenda se define en hora de Loja, así que
        # es el servidor —que ya la conoce— quien tiene que decir la hora.
        return Response(
            {
                "turnos": [t.isoformat() for t in turnos],
                "etiquetas": [timezone.localtime(t).strftime("%H:%M") for t in turnos],
            }
        )

    @action(detail=False, methods=["get"])
    def proximas(self, request):
        exp_id = id_de_consulta(request.query_params.get("expediente"), "expediente")
        if not exp_id:
            return Response(
                {"detalle": "Parámetro 'expediente' requerido."}, status=status.HTTP_400_BAD_REQUEST
            )
        # `.get()` sobre un id inexistente lanzaba DoesNotExist sin capturar:
        # preguntar por un expediente que no está es un 404, no un 500.
        expediente = Expediente.objects.filter(pk=exp_id).first()
        if expediente is None:
            return Response(
                {"detalle": "No existe ese expediente."}, status=status.HTTP_404_NOT_FOUND
            )
        citas = proximas_del_expediente(expediente)
        return Response(CitaSerializer(citas, many=True).data)
