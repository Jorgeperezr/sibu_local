"""Serializers del módulo de Medicina."""

from rest_framework import serializers

from apps.enfermeria.models import SignosVitales

from .models import AtencionMedicina, Diagnostico


class SignosVitalesResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignosVitales
        fields = [
            "id",
            "fecha_hora",
            "temperatura",
            "fc",
            "fr",
            "pa_sistolica",
            "pa_diastolica",
            "sat_o2",
            "peso",
            "talla",
            "imc",
            "glicemia_capilar",
        ]


class DiagnosticoSerializer(serializers.ModelSerializer):
    cie10_descripcion = serializers.CharField(source="cie10.descripcion", read_only=True)

    class Meta:
        model = Diagnostico
        fields = [
            "id",
            "atencion",
            "cie10",
            "cie10_descripcion",
            "tipo",
            "condicion",
            "principal",
            "observacion",
        ]
        read_only_fields = ["atencion"]


class AtencionMedicinaSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True
    )
    cedula = serializers.CharField(source="atencion.expediente.persona.cedula", read_only=True)
    estado = serializers.CharField(source="atencion.estado", read_only=True)
    fecha_hora = serializers.DateTimeField(source="atencion.fecha_hora", read_only=True)
    diagnosticos = serializers.SerializerMethodField()
    triaje = serializers.SerializerMethodField()

    class Meta:
        model = AtencionMedicina
        fields = [
            "atencion",
            "paciente",
            "cedula",
            "estado",
            "fecha_hora",
            "enfermedad_actual",
            "revision_sistemas",
            "examen_fisico",
            "plan_tratamiento",
            "indicaciones",
            "dias_reposo",
            "proxima_cita_sugerida",
            "observaciones",
            "diagnosticos",
            "triaje",
        ]
        read_only_fields = ["atencion"]

    def get_diagnosticos(self, obj):
        return DiagnosticoSerializer(obj.atencion.diagnosticos.all(), many=True).data

    def get_triaje(self, obj):
        """Signos vitales heredados del triaje de Enfermería, si existen."""
        from apps.enfermeria.services import ultimo_triaje

        signos = ultimo_triaje(obj.atencion.expediente)
        return SignosVitalesResumenSerializer(signos).data if signos else None


class CrearAtencionMedicinaSerializer(serializers.Serializer):
    expediente = serializers.IntegerField()
    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True)
    cita = serializers.IntegerField(required=False, allow_null=True)


class AgregarDiagnosticoSerializer(serializers.Serializer):
    cie10 = serializers.CharField(max_length=10)
    tipo = serializers.ChoiceField(
        choices=Diagnostico.TipoDx.choices, default=Diagnostico.TipoDx.PRESUNTIVO
    )
    condicion = serializers.ChoiceField(
        choices=Diagnostico.Condicion.choices, default=Diagnostico.Condicion.PRIMERA
    )
    principal = serializers.BooleanField(default=False)
    observacion = serializers.CharField(max_length=255, required=False, allow_blank=True)


class ItemRecetaSerializer(serializers.Serializer):
    medicamento_id = serializers.IntegerField()
    cantidad_prescrita = serializers.IntegerField(min_value=1)
    dosis = serializers.CharField(max_length=120, required=False, allow_blank=True)
    via = serializers.CharField(max_length=40, required=False, allow_blank=True)
    frecuencia = serializers.CharField(max_length=60, required=False, allow_blank=True)
    duracion = serializers.CharField(max_length=60, required=False, allow_blank=True)
    indicaciones = serializers.CharField(max_length=255, required=False, allow_blank=True)


class EmitirRecetaSerializer(serializers.Serializer):
    items = ItemRecetaSerializer(many=True)


class SolicitarExamenesSerializer(serializers.Serializer):
    examenes = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    prioridad = serializers.ChoiceField(
        choices=[("rutina", "Rutina"), ("urgente", "Urgente")], default="rutina"
    )
    diagnostico_presuntivo = serializers.CharField(max_length=255, required=False, allow_blank=True)
