"""Serializers del módulo de Odontología."""

from rest_framework import serializers

from .models import (
    AtencionOdontologia,
    CatalogoProcedimiento,
    EstadoPieza,
    OdontogramaDetalle,
    Procedimiento,
)


class CatalogoProcedimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoProcedimiento
        fields = ["id", "codigo", "nombre", "requiere_pieza", "estado_resultante", "activo"]


class OdontogramaDetalleSerializer(serializers.ModelSerializer):
    estado_display = serializers.CharField(source="get_estado_codigo_display", read_only=True)

    class Meta:
        model = OdontogramaDetalle
        fields = [
            "id",
            "pieza_fdi",
            "superficie",
            "estado_codigo",
            "estado_display",
            "tipo",
            "observacion",
            "registrado_en",
        ]


class ProcedimientoSerializer(serializers.ModelSerializer):
    catalogo_nombre = serializers.CharField(source="catalogo.nombre", read_only=True)
    ejecutado_por_nombre = serializers.CharField(
        source="ejecutado_por.usuario.get_full_name", read_only=True
    )

    class Meta:
        model = Procedimiento
        fields = [
            "id",
            "catalogo",
            "catalogo_nombre",
            "pieza_fdi",
            "superficie",
            "ejecutado_por_nombre",
            "observacion",
            "creado_en",
        ]


class AtencionOdontologiaSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True
    )
    cedula = serializers.CharField(source="atencion.expediente.persona.cedula", read_only=True)
    estado = serializers.CharField(source="atencion.estado", read_only=True)
    odontograma = serializers.SerializerMethodField()
    procedimientos = serializers.SerializerMethodField()
    indices_actuales = serializers.SerializerMethodField()

    class Meta:
        model = AtencionOdontologia
        fields = [
            "atencion",
            "paciente",
            "cedula",
            "estado",
            "examen_estomatognatico",
            "indices",
            "indices_actuales",
            "plan_tratamiento",
            "indicaciones",
            "proxima_cita_sugerida",
            "odontograma",
            "procedimientos",
        ]
        read_only_fields = ["atencion", "indices"]

    def get_odontograma(self, obj):
        from .services import odontograma_vigente

        vigente = odontograma_vigente(obj.atencion.expediente)
        return OdontogramaDetalleSerializer(vigente.values(), many=True).data

    def get_procedimientos(self, obj):
        return ProcedimientoSerializer(obj.atencion.procedimientos_odonto.all(), many=True).data

    def get_indices_actuales(self, obj):
        from .services import calcular_indices

        return calcular_indices(obj.atencion.expediente)


class CrearAtencionOdontologiaSerializer(serializers.Serializer):
    expediente = serializers.IntegerField()
    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True)


class RegistrarPiezaSerializer(serializers.Serializer):
    pieza_fdi = serializers.CharField(max_length=2)
    estado = serializers.ChoiceField(choices=EstadoPieza.choices)
    superficie = serializers.CharField(max_length=2, required=False, allow_blank=True)
    tipo = serializers.ChoiceField(
        choices=OdontogramaDetalle.TipoRegistro.choices,
        default=OdontogramaDetalle.TipoRegistro.INICIAL,
    )
    observacion = serializers.CharField(max_length=255, required=False, allow_blank=True)


class EjecutarProcedimientoSerializer(serializers.Serializer):
    catalogo = serializers.CharField(max_length=20, help_text="Código del catálogo")
    pieza_fdi = serializers.CharField(max_length=2, required=False, allow_blank=True)
    superficie = serializers.CharField(max_length=2, required=False, allow_blank=True)
    observacion = serializers.CharField(max_length=255, required=False, allow_blank=True)
