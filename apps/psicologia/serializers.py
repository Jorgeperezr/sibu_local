"""
Serializers de Psicología.

CONFIDENCIALIDAD: estos serializers exponen el contenido más sensible del
sistema. Solo se usan desde endpoints sellados por RBAC (ver api.py).
"""

from rest_framework import serializers

from .models import AplicacionEscala, EscalaPsicometrica, FichaPsicologica, SesionPsicologica


class EscalaPsicometricaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EscalaPsicometrica
        fields = ["id", "codigo", "nombre", "descripcion", "puntaje_min", "puntaje_max", "tramos"]


class SesionPsicologicaSerializer(serializers.ModelSerializer):
    profesional_nombre = serializers.CharField(
        source="profesional.usuario.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = SesionPsicologica
        fields = [
            "id",
            "numero",
            "fecha",
            "profesional",
            "profesional_nombre",
            "temas",
            "tecnicas",
            "evolucion",
            "tareas",
            "proxima_sesion",
        ]
        read_only_fields = ["numero", "profesional"]


class AplicacionEscalaSerializer(serializers.ModelSerializer):
    class Meta:
        model = AplicacionEscala
        fields = ["id", "escala", "puntaje", "interpretacion", "alerta", "fecha"]
        read_only_fields = ["escala", "interpretacion", "alerta", "fecha"]


class FichaPsicologicaSerializer(serializers.ModelSerializer):
    sesiones = SesionPsicologicaSerializer(many=True, read_only=True)
    escalas = AplicacionEscalaSerializer(many=True, read_only=True)
    paciente = serializers.CharField(
        source="atencion.expediente.persona.nombre_completo", read_only=True, default=""
    )
    inmutable = serializers.BooleanField(source="atencion.inmutable", read_only=True)

    class Meta:
        model = FichaPsicologica
        fields = [
            "atencion",
            "paciente",
            "motivo",
            "historia_problema",
            "estado_mental",
            "impresion_diagnostica",
            "plan_terapeutico",
            "riesgo_nivel",
            "nota_riesgo",
            "modalidad",
            "estado_proceso",
            "inmutable",
            "sesiones",
            "escalas",
        ]
        read_only_fields = ["atencion", "riesgo_nivel", "estado_proceso"]


class CrearFichaPsicologicaSerializer(serializers.Serializer):
    expediente = serializers.IntegerField()
    motivo = serializers.CharField()
    modalidad = serializers.ChoiceField(
        choices=FichaPsicologica.Modalidad.choices,
        default=FichaPsicologica.Modalidad.PRESENCIAL,
    )


class RegistrarSesionSerializer(serializers.Serializer):
    evolucion = serializers.CharField()
    temas = serializers.CharField(required=False, allow_blank=True, default="")
    tecnicas = serializers.CharField(required=False, allow_blank=True, default="")
    tareas = serializers.CharField(required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False, allow_null=True)
    proxima_sesion = serializers.DateField(required=False, allow_null=True)


class AplicarEscalaSerializer(serializers.Serializer):
    escala = serializers.CharField(help_text="Código de la escala, ej. PHQ-9")
    puntaje = serializers.IntegerField()


class MarcarRiesgoSerializer(serializers.Serializer):
    nivel = serializers.ChoiceField(choices=FichaPsicologica.Riesgo.choices)
    nota = serializers.CharField()


class CerrarProcesoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(
        choices=[
            (FichaPsicologica.Estado.ALTA, "Alta"),
            (FichaPsicologica.Estado.ABANDONO, "Abandono"),
            (FichaPsicologica.Estado.DERIVADO, "Derivado a externo"),
        ]
    )
