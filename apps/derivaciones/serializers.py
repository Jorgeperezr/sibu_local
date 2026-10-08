"""
Serializers de Derivaciones.

CONFIDENCIALIDAD: `atencion_destino` se expone SOLO como identificador y
nombre de servicio, NUNCA anidado con su contenido. Anidarlo filtraría el
detalle clínico de Psicología a quien derivó, que es precisamente lo que el
sello impide. El `retorno_texto` ya viene saneado desde services.retornar().
"""

from rest_framework import serializers

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES

from .models import Contrarreferencia, Derivacion, ReferenciaExterna


class DerivacionSerializer(serializers.ModelSerializer):
    paciente = serializers.CharField(
        source="atencion_origen.expediente.persona.nombre_completo",
        read_only=True,
        default="",
    )
    servicio_origen = serializers.CharField(
        source="atencion_origen.servicio.nombre", read_only=True
    )
    servicio_destino_nombre = serializers.CharField(
        source="servicio_destino.nombre", read_only=True
    )
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    destino_confidencial = serializers.SerializerMethodField()

    class Meta:
        model = Derivacion
        fields = [
            "id",
            "paciente",
            "atencion_origen",
            "servicio_origen",
            "servicio_destino",
            "servicio_destino_nombre",
            "destino_confidencial",
            "motivo",
            "resumen",
            "prioridad",
            "estado",
            "estado_display",
            # atencion_destino: solo el id, jamás anidado con su contenido.
            "atencion_destino",
            "retorno_texto",
            "creado_en",
        ]
        read_only_fields = ["estado", "atencion_destino", "retorno_texto", "creado_en"]

    def get_destino_confidencial(self, obj) -> bool:
        return obj.servicio_destino.codigo in SERVICIOS_CONFIDENCIALES


class CrearDerivacionSerializer(serializers.Serializer):
    atencion_origen = serializers.IntegerField()
    servicio_destino = serializers.IntegerField()
    motivo = serializers.CharField()
    resumen = serializers.CharField(required=False, allow_blank=True, default="")
    prioridad = serializers.ChoiceField(
        choices=[("normal", "Normal"), ("urgente", "Urgente")], default="normal"
    )


class RechazarSerializer(serializers.Serializer):
    motivo = serializers.CharField()


class AtenderSerializer(serializers.Serializer):
    atencion_destino = serializers.IntegerField()


class RetornarSerializer(serializers.Serializer):
    texto = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text=(
            "Se ignora si el servicio destino es confidencial: en ese caso se "
            "sustituye por un acuse sin contenido clínico."
        ),
    )


class ContrarreferenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contrarreferencia
        fields = ["id", "fecha_recepcion", "hallazgos", "tratamiento_instaurado"]


class ReferenciaExternaSerializer(serializers.ModelSerializer):
    contrarreferencia = ContrarreferenciaSerializer(read_only=True)

    class Meta:
        model = ReferenciaExterna
        fields = [
            "id",
            "atencion",
            "institucion_destino",
            "especialidad",
            "motivo",
            "resumen_clinico",
            "contrarreferencia",
            "creado_en",
        ]
        read_only_fields = ["creado_en"]


class CrearReferenciaSerializer(serializers.Serializer):
    atencion = serializers.IntegerField()
    institucion = serializers.CharField()
    motivo = serializers.CharField()
    especialidad = serializers.CharField(required=False, allow_blank=True, default="")
    resumen_clinico = serializers.CharField(required=False, allow_blank=True, default="")


class RegistrarContrarreferenciaSerializer(serializers.Serializer):
    hallazgos = serializers.CharField(required=False, allow_blank=True, default="")
    tratamiento = serializers.CharField(required=False, allow_blank=True, default="")
    fecha_recepcion = serializers.DateField(required=False, allow_null=True)
