"""Serializers de Psicopedagogía."""

from rest_framework import serializers

from .models import FichaPsicopedagogica, SeguimientoAcademico


class SeguimientoAcademicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeguimientoAcademico
        fields = ["id", "periodo", "promedio_antes", "promedio_despues", "observaciones"]


class FichaPsicopedagogicaSerializer(serializers.ModelSerializer):
    seguimientos = SeguimientoAcademicoSerializer(many=True, read_only=True)
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True, default=""
    )

    class Meta:
        model = FichaPsicopedagogica
        fields = [
            "atencion",
            "paciente",
            "motivo",
            "historial_academico",
            "estilos_aprendizaje",
            "plan_intervencion",
            "seguimientos",
        ]
        read_only_fields = ["atencion", "historial_academico"]


class CrearFichaPsicopedagogicaSerializer(serializers.Serializer):
    expediente = serializers.IntegerField()
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class RegistrarSeguimientoSerializer(serializers.Serializer):
    periodo = serializers.CharField()
    promedio_antes = serializers.DecimalField(
        max_digits=4, decimal_places=2, required=False, allow_null=True
    )
    promedio_despues = serializers.DecimalField(
        max_digits=4, decimal_places=2, required=False, allow_null=True
    )
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
