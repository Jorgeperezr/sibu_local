"""Serializers del módulo de Farmacia."""

from rest_framework import serializers

from .models import Dispensacion, Lote, Medicamento, MovimientoInventario, Receta, RecetaDetalle


class MedicamentoSerializer(serializers.ModelSerializer):
    stock_disponible = serializers.SerializerMethodField()

    class Meta:
        model = Medicamento
        fields = [
            "id",
            "codigo",
            "dci",
            "nombre_comercial",
            "concentracion",
            "forma_farmaceutica",
            "unidad_medida",
            "stock_minimo",
            "requiere_receta",
            "activo",
            "stock_disponible",
        ]

    def get_stock_disponible(self, obj):
        from .services import stock_disponible

        return stock_disponible(obj)


class LoteSerializer(serializers.ModelSerializer):
    medicamento_nombre = serializers.CharField(source="medicamento.__str__", read_only=True)

    class Meta:
        model = Lote
        fields = [
            "id",
            "medicamento",
            "medicamento_nombre",
            "numero_lote",
            "fecha_caducidad",
            "cantidad_actual",
            "costo_unitario",
            "proveedor",
        ]


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    lote_numero = serializers.CharField(source="lote.numero_lote", read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = [
            "id",
            "lote",
            "lote_numero",
            "tipo",
            "tipo_display",
            "cantidad",
            "saldo_resultante",
            "referencia_doc",
            "fecha_hora",
        ]


class DispensacionSerializer(serializers.ModelSerializer):
    lote_numero = serializers.CharField(source="lote.numero_lote", read_only=True)
    caducidad = serializers.DateField(source="lote.fecha_caducidad", read_only=True)

    class Meta:
        model = Dispensacion
        fields = ["id", "lote", "lote_numero", "caducidad", "cantidad_despachada", "fecha_hora"]


class RecetaDetalleSerializer(serializers.ModelSerializer):
    medicamento_nombre = serializers.CharField(source="medicamento.__str__", read_only=True)
    dispensaciones = DispensacionSerializer(many=True, read_only=True)
    pendiente = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()

    class Meta:
        model = RecetaDetalle
        fields = [
            "id",
            "medicamento",
            "medicamento_nombre",
            "cantidad_prescrita",
            "dosis",
            "via",
            "frecuencia",
            "duracion",
            "indicaciones",
            "pendiente",
            "stock_disponible",
            "dispensaciones",
        ]

    def get_pendiente(self, obj):
        from .services import pendiente_por_despachar

        return pendiente_por_despachar(obj)

    def get_stock_disponible(self, obj):
        from .services import stock_disponible

        return stock_disponible(obj.medicamento)


class RecetaSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True
    )
    cedula = serializers.CharField(source="atencion.expediente.persona.cedula", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    detalles = RecetaDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = Receta
        fields = [
            "id",
            "numero",
            "atencion",
            "paciente",
            "cedula",
            "valida_hasta",
            "estado",
            "estado_display",
            "detalles",
            "creado_en",
        ]


class IngresoLoteSerializer(serializers.Serializer):
    medicamento = serializers.IntegerField()
    numero_lote = serializers.CharField(max_length=60)
    cantidad = serializers.IntegerField(min_value=1)
    fecha_caducidad = serializers.DateField()
    costo_unitario = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=0
    )
    proveedor = serializers.CharField(max_length=150, required=False, allow_blank=True)
    referencia_doc = serializers.CharField(max_length=60, required=False, allow_blank=True)


class DespacharItemSerializer(serializers.Serializer):
    detalle = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)


class AnularRecetaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255, min_length=5)
