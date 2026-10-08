"""Serializers de Talleres."""

from rest_framework import serializers

from .models import Taller, TallerParticipante


class TallerParticipanteSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(
        source="expediente.persona.nombre_completo", read_only=True, default=""
    )

    class Meta:
        model = TallerParticipante
        fields = [
            "id",
            "expediente",
            "nombre",
            "cedula_digitada",
            "validado",
            "asistio",
            "origen",
            "snapshot_academico",
        ]
        read_only_fields = ["validado", "origen", "snapshot_academico"]


class TallerSerializer(serializers.ModelSerializer):
    responsable_nombre = serializers.CharField(
        source="responsable.usuario.get_full_name", read_only=True, default=""
    )
    servicio_nombre = serializers.CharField(source="servicio.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    total_participantes = serializers.IntegerField(read_only=True)
    participantes = TallerParticipanteSerializer(many=True, read_only=True)

    class Meta:
        model = Taller
        fields = [
            "id",
            "codigo",
            "servicio",
            "servicio_nombre",
            "seccion",
            "tema",
            "objetivo",
            "tipo",
            "responsable",
            "responsable_nombre",
            "fecha",
            "hora_inicio",
            "duracion_min",
            "modalidad",
            "lugar",
            "poblacion_objetivo",
            "estado",
            "estado_display",
            "total_participantes",
            "participantes",
            "observaciones",
        ]
        read_only_fields = ["codigo", "seccion", "estado"]


class RegistrarParticipanteSerializer(serializers.Serializer):
    cedula = serializers.CharField(required=False, allow_blank=True, default="")
    expediente = serializers.IntegerField(required=False, allow_null=True)
    asistio = serializers.BooleanField(default=True)
