"""Serializers del módulo de Laboratorio."""

from rest_framework import serializers

from .models import (
    Examen,
    OrdenExamen,
    OrdenLaboratorio,
    ParametroExamen,
    ResultadoParametro,
)


class ParametroExamenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametroExamen
        fields = [
            "id",
            "nombre",
            "unidad",
            "tipo_valor",
            "sexo",
            "edad_min",
            "edad_max",
            "ref_min",
            "ref_max",
            "orden",
        ]


class ExamenSerializer(serializers.ModelSerializer):
    parametros = ParametroExamenSerializer(many=True, read_only=True)

    class Meta:
        model = Examen
        fields = [
            "id",
            "codigo",
            "nombre",
            "perfil",
            "indicaciones_preparacion",
            "activo",
            "parametros",
        ]


class ResultadoParametroSerializer(serializers.ModelSerializer):
    parametro_nombre = serializers.CharField(source="parametro.nombre", read_only=True)
    marcador_display = serializers.CharField(source="get_marcador_display", read_only=True)

    class Meta:
        model = ResultadoParametro
        fields = [
            "id",
            "parametro",
            "parametro_nombre",
            "valor",
            "unidad",
            "ref_min",
            "ref_max",
            "marcador",
            "marcador_display",
            "observacion",
            "registrado_en",
        ]


class OrdenExamenSerializer(serializers.ModelSerializer):
    examen_nombre = serializers.CharField(source="examen.nombre", read_only=True)
    resultados = ResultadoParametroSerializer(many=True, read_only=True)

    class Meta:
        model = OrdenExamen
        fields = ["id", "examen", "examen_nombre", "resultados"]


class OrdenLaboratorioSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True
    )
    cedula = serializers.CharField(source="atencion.expediente.persona.cedula", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    examenes = OrdenExamenSerializer(many=True, read_only=True)
    tiene_criticos = serializers.BooleanField(read_only=True)

    class Meta:
        model = OrdenLaboratorio
        fields = [
            "id",
            "atencion",
            "paciente",
            "cedula",
            "prioridad",
            "diagnostico_presuntivo",
            "estado",
            "estado_display",
            "fecha_toma_muestra",
            "tipo_muestra",
            "codigo_barras",
            "motivo_rechazo",
            "validado_en",
            "publicado_en",
            "enviado_correo_paciente",
            "tiene_criticos",
            "examenes",
            "creado_en",
        ]


class TomarMuestraSerializer(serializers.Serializer):
    tipo_muestra = serializers.CharField(max_length=60, required=False, allow_blank=True)
    codigo_barras = serializers.CharField(max_length=40, required=False, allow_blank=True)


class RechazarMuestraSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255, min_length=5)


class RegistrarResultadoSerializer(serializers.Serializer):
    orden_examen = serializers.IntegerField()
    parametro = serializers.IntegerField()
    valor = serializers.CharField(max_length=60)
    observacion = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PublicarSerializer(serializers.Serializer):
    enviar_correo = serializers.BooleanField(default=True)
