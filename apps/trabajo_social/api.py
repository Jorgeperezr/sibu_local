"""
API REST de Trabajo Social.

- GET  /api/v1/trabajo-social/fichas/?expediente=N   historial de versiones
- POST /api/v1/trabajo-social/fichas/prepoblar/      crear v1 desde matrícula
- POST /api/v1/trabajo-social/fichas/verificar/      crear v(n+1) verificada
- POST /api/v1/trabajo-social/visitas/               registrar visita
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.parametros import id_de_consulta
from apps.expediente.models import Expediente
from apps.usuarios.permissions import EsPersonalDeLaUnidad

from . import services
from .models import FichaSocioeconomica, VisitaDomiciliaria
from .serializers import (
    FichaSocioeconomicaSerializer,
    VerificarFichaSerializer,
    VisitaDomiciliariaSerializer,
)


class FichaSocioeconomicaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FichaSocioeconomica.objects.select_related("expediente__persona")
    serializer_class = FichaSocioeconomicaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        qs = super().get_queryset()
        # `filter(expediente_id="abc")` lanza ValueError y salía un 500. Se
        # responde 400 y no «sin filtro»: ignorar un filtro ilegible
        # devolvería las fichas de TODAS las personas a quien pidió las de una.
        expediente = id_de_consulta(self.request.query_params.get("expediente"), "expediente")
        if expediente:
            qs = qs.filter(expediente_id=expediente)
        return qs.order_by("-version")

    @action(detail=False, methods=["post"])
    def prepoblar(self, request):
        try:
            expediente = Expediente.objects.get(pk=request.data.get("expediente"))
            ficha = services.prepoblar_desde_matricula(expediente, usuario=request.user)
        except Expediente.DoesNotExist:
            return Response({"detail": "Expediente no encontrado."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FichaSocioeconomicaSerializer(ficha).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def verificar(self, request):
        entrada = VerificarFichaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = dict(entrada.validated_data)
        expediente_id = datos.pop("expediente")
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return Response({"detail": "El usuario no tiene perfil."}, status=403)
        try:
            expediente = Expediente.objects.get(pk=expediente_id)
            ficha = services.verificar_ficha(
                expediente, datos, profesional=perfil, usuario=request.user
            )
        except Expediente.DoesNotExist:
            return Response({"detail": "Expediente no encontrado."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FichaSocioeconomicaSerializer(ficha).data, status=status.HTTP_201_CREATED)


class VisitaDomiciliariaViewSet(viewsets.ModelViewSet):
    queryset = VisitaDomiciliaria.objects.select_related("atencion").order_by("-fecha")
    serializer_class = VisitaDomiciliariaSerializer
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def create(self, request, *args, **kwargs):
        from apps.expediente.models import Atencion

        try:
            atencion = Atencion.objects.get(pk=request.data.get("atencion"))
            visita = services.registrar_visita(
                atencion,
                fecha=request.data.get("fecha"),
                condiciones=request.data.get("condiciones_verificadas"),
                georreferencia=request.data.get("georreferencia"),
                observaciones=request.data.get("observaciones", ""),
            )
        except Atencion.DoesNotExist:
            return Response({"detail": "Atención no encontrada."}, status=404)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VisitaDomiciliariaSerializer(visita).data, status=status.HTTP_201_CREATED)
