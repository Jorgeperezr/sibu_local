"""Serializers del expediente único."""

from rest_framework import serializers

from .models import AlertaClinica, Atencion, Expediente, Persona


class PersonaSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.CharField(read_only=True)

    class Meta:
        model = Persona
        fields = [
            "id",
            "cedula",
            "nombres",
            "apellidos",
            "nombre_completo",
            "sexo",
            "genero",
            "fecha_nacimiento",
            "tipo_vinculo",
            "correo_institucional",
            "celular",
            "telefono",
        ]


class AlertaClinicaSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = AlertaClinica
        fields = ["id", "tipo", "tipo_display", "descripcion", "activa"]


class AtencionResumenSerializer(serializers.ModelSerializer):
    servicio = serializers.CharField(source="servicio.nombre", read_only=True)
    profesional = serializers.CharField(source="profesional.usuario.get_full_name", read_only=True)

    class Meta:
        model = Atencion
        fields = [
            "id",
            "servicio",
            "profesional",
            "fecha_hora",
            "tipo",
            "estado",
            "motivo_consulta",
        ]


class ExpedienteSerializer(serializers.ModelSerializer):
    persona = PersonaSerializer(read_only=True)
    alertas = serializers.SerializerMethodField()

    class Meta:
        model = Expediente
        fields = [
            "id",
            "numero_expediente",
            "persona",
            "grupo_sanguineo",
            "discapacidad_tipo",
            "discapacidad_porcentaje",
            "fecha_apertura",
            "alertas",
        ]

    def get_alertas(self, obj):
        activas = obj.alertas.filter(activa=True)
        return AlertaClinicaSerializer(activas, many=True).data


class BreakGlassSerializer(serializers.Serializer):
    motivo = serializers.CharField(min_length=10, help_text="Justificación obligatoria.")
