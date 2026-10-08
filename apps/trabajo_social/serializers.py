"""Serializers de Trabajo Social."""

from rest_framework import serializers

from .models import FichaSocioeconomica, VisitaDomiciliaria


class FichaSocioeconomicaSerializer(serializers.ModelSerializer):
    origen_display = serializers.CharField(source="get_origen_display", read_only=True)

    class Meta:
        model = FichaSocioeconomica
        fields = [
            "id",
            "expediente",
            "version",
            "vigente",
            "origen",
            "origen_display",
            "ingresos",
            "egresos",
            "ingresos_totales",
            "egresos_totales",
            "vivienda_estudiante",
            "vivienda_familiar",
            "convivencia",
            "situacion_laboral",
            "salud_familiar",
            "puntaje",
            "estrato",
            "creado_en",
        ]
        read_only_fields = [
            "version",
            "vigente",
            "origen",
            "ingresos_totales",
            "egresos_totales",
            "puntaje",
            "estrato",
            "creado_en",
        ]


class VerificarFichaSerializer(serializers.Serializer):
    expediente = serializers.IntegerField()
    ingresos = serializers.DictField(required=False)
    egresos = serializers.DictField(required=False)
    vivienda_estudiante = serializers.DictField(required=False)
    vivienda_familiar = serializers.DictField(required=False)
    convivencia = serializers.DictField(required=False)
    situacion_laboral = serializers.DictField(required=False)
    salud_familiar = serializers.DictField(required=False)


class VisitaDomiciliariaSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitaDomiciliaria
        fields = [
            "id",
            "atencion",
            "fecha",
            "condiciones_verificadas",
            "georreferencia",
            "observaciones",
        ]
        read_only_fields = ["atencion"]
