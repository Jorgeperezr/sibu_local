"""Serializers de Becas. Los datos bancarios NO se exponen: no se almacenan."""

from rest_framework import serializers

from .models import BecaBeneficiario, SeguimientoBeca, TipoBeca


class TipoBecaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoBeca
        fields = ["id", "codigo", "nombre", "descripcion"]


class SeguimientoBecaSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = SeguimientoBeca
        fields = [
            "id",
            "periodo",
            "fecha",
            "tipo",
            "tipo_display",
            "detalle",
            "matricula_vigente",
        ]
        read_only_fields = ["fecha", "matricula_vigente"]


class BecaBeneficiarioSerializer(serializers.ModelSerializer):
    beneficiario = serializers.CharField(
        source="expediente.persona.nombre_completo", read_only=True
    )
    tipo_beca_nombre = serializers.CharField(source="tipo_beca.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    seguimientos = SeguimientoBecaSerializer(many=True, read_only=True)

    class Meta:
        model = BecaBeneficiario
        # datos_bancarios_cifrados queda fuera a propósito: SIBU no los guarda.
        fields = [
            "id",
            "expediente",
            "beneficiario",
            "tipo_beca",
            "tipo_beca_nombre",
            "periodo_desde",
            "periodo_hasta",
            "monto_o_porcentaje",
            "resolucion",
            "origen",
            "id_externo",
            "estado",
            "estado_display",
            "causal",
            "seguimientos",
        ]
        read_only_fields = ["estado", "causal"]


class CambiarEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=BecaBeneficiario.Estado.choices)
    causal = serializers.CharField(required=False, allow_blank=True, default="")


class RegistrarSeguimientoSerializer(serializers.Serializer):
    periodo = serializers.IntegerField()
    tipo = serializers.ChoiceField(choices=SeguimientoBeca.Tipo.choices)
    detalle = serializers.CharField()
