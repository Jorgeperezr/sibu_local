"""Serializers DRF del módulo académico."""

from rest_framework import serializers

from .models import CargaInstitucional, DatoAcademico


class CargaInstitucionalSerializer(serializers.ModelSerializer):
    periodo_codigo = serializers.CharField(source="periodo.codigo", read_only=True)

    class Meta:
        model = CargaInstitucional
        fields = [
            "id",
            "periodo",
            "periodo_codigo",
            "nombre_archivo",
            "formato",
            "estado",
            "total_filas",
            "altas",
            "actualizaciones",
            "errores",
            "bitacora",
            "creado_en",
        ]
        read_only_fields = [
            "estado",
            "total_filas",
            "altas",
            "actualizaciones",
            "errores",
            "bitacora",
            "creado_en",
            "nombre_archivo",
            "formato",
        ]


class DatoAcademicoSerializer(serializers.ModelSerializer):
    cedula = serializers.CharField(source="persona.cedula", read_only=True)
    nombre_completo = serializers.CharField(source="persona.nombre_completo", read_only=True)

    class Meta:
        model = DatoAcademico
        fields = [
            "id",
            "cedula",
            "nombre_completo",
            "periodo",
            "facultad",
            "carrera",
            "nivel",
            "modalidad",
            "ciclo",
            "jornada",
            "paralelo",
            "estado",
            "email_institucional",
        ]


class ConsultaPersonaSerializer(serializers.Serializer):
    """Salida del autocompletado por cédula (sección 7.5)."""

    cedula = serializers.CharField()
    nombres = serializers.CharField()
    apellidos = serializers.CharField()
    tipo_vinculo = serializers.CharField()
    facultad = serializers.CharField(allow_blank=True)
    carrera = serializers.CharField(allow_blank=True)
    ciclo = serializers.CharField(allow_blank=True)
    modalidad = serializers.CharField(allow_blank=True)
    jornada = serializers.CharField(allow_blank=True)
    estado = serializers.CharField(allow_blank=True)
    email_institucional = serializers.CharField(allow_blank=True)
    periodo = serializers.CharField(allow_blank=True)
