"""Serializers DRF del módulo de citas."""

from rest_framework import serializers

from .models import Agenda, BloqueoAgenda, Cita


class AgendaSerializer(serializers.ModelSerializer):
    dia_semana_display = serializers.CharField(source="get_dia_semana_display", read_only=True)

    class Meta:
        model = Agenda
        fields = [
            "id",
            "profesional",
            "servicio",
            "dia_semana",
            "dia_semana_display",
            "hora_inicio",
            "hora_fin",
            "duracion_turno_min",
            "vigente_desde",
            "vigente_hasta",
            "activa",
        ]


class BloqueoAgendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BloqueoAgenda
        fields = ["id", "profesional", "fecha_inicio", "fecha_fin", "motivo"]


class CitaSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(source="expediente.persona.nombre_completo", read_only=True)
    cedula = serializers.CharField(source="expediente.persona.cedula", read_only=True)
    servicio_nombre = serializers.CharField(source="servicio.nombre", read_only=True)
    profesional_nombre = serializers.CharField(
        source="profesional.usuario.get_full_name", read_only=True
    )
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = Cita
        fields = [
            "id",
            "expediente",
            "paciente",
            "cedula",
            "servicio",
            "servicio_nombre",
            "profesional",
            "profesional_nombre",
            "fecha_hora",
            "duracion_min",
            "estado",
            "estado_display",
            "origen",
            "motivo",
            "cita_origen",
            "llegada_en",
            "atendida_en",
            "observaciones",
        ]
        read_only_fields = ["estado", "cita_origen", "llegada_en", "atendida_en"]


class ReservaCitaSerializer(serializers.Serializer):
    """Entrada para reservar: valida y luego delega a services.reservar_cita."""

    expediente = serializers.IntegerField()
    servicio = serializers.IntegerField()
    profesional = serializers.IntegerField()
    fecha_hora = serializers.DateTimeField()
    # Sin `default`: omitirla significa «la que tenga configurada el
    # profesional». Con `default=20` el valor llegaba siempre relleno y la
    # agenda no podía decidir nunca.
    duracion_min = serializers.IntegerField(
        required=False, allow_null=True, min_value=5, max_value=240
    )
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=255)
    origen = serializers.CharField(required=False, default=Cita.Origen.VENTANILLA)


class ReprogramacionSerializer(serializers.Serializer):
    fecha_hora = serializers.DateTimeField()
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CancelacionSerializer(serializers.Serializer):
    motivo = serializers.CharField(min_length=3, max_length=255)


class CambioEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Cita.Estado.choices)


class DisponibilidadQuerySerializer(serializers.Serializer):
    profesional = serializers.IntegerField()
    servicio = serializers.IntegerField()
    fecha = serializers.DateField()
