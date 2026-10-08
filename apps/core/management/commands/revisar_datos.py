"""
Revisa la coherencia de los datos y dice qué encontró.

Las restricciones de base de datos impiden que se escriba un disparate NUEVO,
pero no dicen nada de lo que ya está escrito: una fila anterior a la
restricción sobrevive a la migración si nadie la toca. Y hay invariantes que
ninguna restricción puede expresar —el saldo de un lote contra la suma de sus
movimientos cruza dos tablas— y que solo se comprueban mirando.

    python manage.py revisar_datos            # resumen
    python manage.py revisar_datos --detalle  # con las filas implicadas

Devuelve código de salida 1 si encuentra algo, para poder encadenarlo en un
despliegue: estas migraciones fallan si los datos que ya están en el servidor
violan alguna regla, así que conviene mirarlo ANTES de aplicarlas.

No corrige nada, y es a propósito. Un saldo que no cuadra puede ser un
movimiento perdido o un ajuste sin registrar, y cada caso se arregla distinto:
decidirlo por su cuenta convertiría un descuadre visible en uno silencioso.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum

# Los movimientos que suman al saldo y los que restan. `TRANSFERENCIA` queda
# fuera a propósito: mueve existencias entre lotes y su signo depende del
# extremo, así que contarla aquí daría un descuadre falso.
SUMAN = {"ingreso", "ajuste_mas"}
RESTAN = {"egreso", "ajuste_menos", "baja"}


class Hallazgo:
    """Un problema encontrado, con las filas que lo provocan."""

    def __init__(self, titulo, explicacion, filas):
        self.titulo = titulo
        self.explicacion = explicacion
        self.filas = list(filas)

    def __bool__(self):
        return bool(self.filas)


class Command(BaseCommand):
    help = "Busca incoherencias en los datos ya guardados. No corrige nada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--detalle",
            action="store_true",
            help="Listar las filas implicadas, no solo cuántas son.",
        )

    def handle(self, *args, **opciones):
        hallazgos = [
            comprobar()
            for comprobar in (
                self._cedulas_invalidas,
                self._atenciones_de_servicio_ajeno,
                self._saldos_que_no_cuadran,
                self._fichas_vigentes_duplicadas,
                self._derivaciones_atendidas_sin_atencion,
                self._citas_con_profesional_de_otro_servicio,
                self._expedientes_duplicados_por_persona,
                self._alertas_sin_expediente_con_persona,
                self._bitacora_sin_servicio,
                self._montos_de_ficha_ilegibles,
            )
        ]
        con_problema = [h for h in hallazgos if h]

        for hallazgo in hallazgos:
            marca = self.style.ERROR("✗") if hallazgo else self.style.SUCCESS("✓")
            cuenta = f"{len(hallazgo.filas)}" if hallazgo else "—"
            self.stdout.write(f" {marca} {hallazgo.titulo:<52} {cuenta:>5}")
            if hallazgo and opciones["detalle"]:
                self.stdout.write(f"    {hallazgo.explicacion}")
                for fila in hallazgo.filas[:20]:
                    self.stdout.write(f"      · {fila}")
                if len(hallazgo.filas) > 20:
                    self.stdout.write(f"      … y {len(hallazgo.filas) - 20} más")

        if not con_problema:
            self.stdout.write(self.style.SUCCESS("\nSin incoherencias."))
            return

        self.stdout.write(
            self.style.ERROR(f"\n{len(con_problema)} comprobación(es) con hallazgos.")
        )
        if not opciones["detalle"]:
            self.stdout.write("Repita con --detalle para ver las filas.")
        # Código de salida != 0 para poder encadenarlo en un despliegue.
        raise SystemExit(1)

    # ------------------------------------------------------------ personas

    def _cedulas_invalidas(self):
        """
        `Persona.save()` valida el módulo 10 desde el Sprint 10, pero una fila
        escrita antes —o por una carga masiva anterior— sigue ahí.
        """
        from apps.academico.validators import validar_cedula_ecuatoriana
        from apps.expediente.models import Persona

        malas = [
            f"{p.cedula} — {p.nombre_completo}"
            for p in Persona.objects.filter(tipo_documento="cedula").only(
                "cedula", "nombres", "apellidos"
            )
            if not validar_cedula_ecuatoriana(p.cedula)
        ]
        return Hallazgo(
            "Cédulas que no pasan el módulo 10",
            "Se validan al guardar desde el Sprint 10; estas son anteriores.",
            malas,
        )

    def _expedientes_duplicados_por_persona(self):
        from apps.expediente.models import Expediente

        duplicados = (
            Expediente.objects.values("persona__cedula").annotate(n=Count("id")).filter(n__gt=1)
        )
        return Hallazgo(
            "Personas con más de un expediente",
            "El expediente es único por persona: dos parten su historia en dos.",
            [f"{d['persona__cedula']} — {d['n']} expedientes" for d in duplicados],
        )

    # ---------------------------------------------------------- atenciones

    def _atenciones_de_servicio_ajeno(self):
        """
        `verificar_profesional_del_servicio` lo impide desde que se añadió,
        pero antes cualquier perfil podía quedar de tratante en cualquier
        servicio. En Psicología eso daba acceso al contenido sellado: quien
        conste de tratante lo ve.
        """
        from apps.expediente.models import Atencion

        sueltas = []
        consulta = Atencion.objects.select_related("servicio", "profesional__usuario").exclude(
            profesional__isnull=True
        )
        for atencion in consulta.iterator():
            if not atencion.profesional.servicios.filter(pk=atencion.servicio_id).exists():
                sueltas.append(
                    f"Atención {atencion.pk} en {atencion.servicio.nombre}, "
                    f"tratante {atencion.profesional.usuario.username}"
                )
        return Hallazgo(
            "Atenciones con un tratante de otro servicio",
            "Quien consta de tratante puede verla, sello incluido.",
            sueltas,
        )

    def _citas_con_profesional_de_otro_servicio(self):
        from apps.citas.models import Cita

        malas = []
        for cita in Cita.objects.select_related("servicio", "profesional__usuario").iterator():
            if not cita.profesional.servicios.filter(pk=cita.servicio_id).exists():
                malas.append(
                    f"Cita {cita.pk}: {cita.profesional.usuario.username} "
                    f"en {cita.servicio.nombre}"
                )
        return Hallazgo(
            "Citas con un profesional de otro servicio",
            "El paciente llega y quien lo espera no atiende ese servicio.",
            malas,
        )

    # ------------------------------------------------------------ farmacia

    def _saldos_que_no_cuadran(self):
        """
        La comprobación que ninguna restricción puede hacer: cruza dos tablas.

        Es la que delata la lectura-modificación-escritura perdida que se
        corrigió con `select_for_update` —entraban 200 unidades y quedaban
        100, con dos movimientos que ya no cuadraban con el saldo—.
        """
        from apps.farmacia.models import Lote

        descuadres = []
        lotes = Lote.objects.select_related("medicamento").annotate(
            entradas=Sum("movimientos__cantidad", filter=Q(movimientos__tipo__in=SUMAN)),
            salidas=Sum("movimientos__cantidad", filter=Q(movimientos__tipo__in=RESTAN)),
        )
        for lote in lotes:
            esperado = (lote.entradas or 0) - (lote.salidas or 0)
            if esperado != lote.cantidad_actual:
                descuadres.append(f"{lote} — saldo {lote.cantidad_actual}, movimientos {esperado}")
        return Hallazgo(
            "Lotes cuyo saldo no cuadra con sus movimientos",
            "Un descuadre es un movimiento perdido o un ajuste sin registrar.",
            descuadres,
        )

    # ------------------------------------------------------- trabajo social

    def _fichas_vigentes_duplicadas(self):
        from apps.trabajo_social.models import FichaSocioeconomica

        duplicadas = (
            FichaSocioeconomica.objects.filter(vigente=True)
            .values("expediente__persona__cedula")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        return Hallazgo(
            "Expedientes con dos fichas socioeconómicas vigentes",
            "De la vigente salen el puntaje y el estrato de una beca.",
            [f"{d['expediente__persona__cedula']} — {d['n']} vigentes" for d in duplicadas],
        )

    # --------------------------------------------------------- derivaciones

    def _derivaciones_atendidas_sin_atencion(self):
        from apps.derivaciones.models import Derivacion

        sueltas = Derivacion.objects.filter(
            estado=Derivacion.Estado.ATENDIDA, atencion_destino__isnull=True
        ).select_related("servicio_destino")
        return Hallazgo(
            "Derivaciones atendidas sin atención de destino",
            "Consta como atendida y no hay registro de qué se hizo.",
            [f"Derivación {d.pk} hacia {d.servicio_destino.nombre}" for d in sueltas],
        )

    # ---------------------------------------------------------- expediente

    def _bitacora_sin_servicio(self):
        """
        La pantalla de la bitácora vela una entrada por su campo `servicio`.
        Una que apunte a una atención y no lo declare se pinta como abierta, y
        entonces enseña al paciente de una firma de Psicología. Estas son
        anteriores a que el campo existiera.
        """
        from apps.auditoria.models import LogAuditoria

        ENTIDADES_CLINICAS = ("Atencion", "SolicitudFirma", "FichaPsicologica")
        sueltas = LogAuditoria.objects.filter(
            servicio="", entidad__in=ENTIDADES_CLINICAS, expediente_id__isnull=False
        )
        return Hallazgo(
            "Entradas de bitácora clínicas sin servicio declarado",
            "La pantalla no puede velarlas y mostraría al paciente.",
            [f"Registro {r.pk}: {r.accion} sobre {r.entidad} {r.entidad_id}" for r in sueltas],
        )

    def _montos_de_ficha_ilegibles(self):
        """
        Fichas cuyos ingresos o egresos guardados no se pueden leer como número.

        Existe porque el arreglo de la lectura no arregla lo ya cargado. Hasta
        hoy el motor de carga borraba la coma antes de leer —«450,50» entraba
        como 45050— y la suma de Trabajo Social descartaba lo que no supiera
        leer. Las fichas que entraron así siguen en la base con lo que se
        escribió entonces, y ninguna restricción las va a delatar.

        Se listan para que Trabajo Social las vuelva a verificar; no se
        corrigen: un monto ilegible puede ser un error de digitación o texto
        descriptivo legítimo, y decidirlo por su cuenta convertiría un dato
        dudoso visible en uno inventado silencioso.
        """
        from apps.core import numeros
        from apps.trabajo_social.models import FichaSocioeconomica

        filas = []
        for ficha in FichaSocioeconomica.objects.filter(vigente=True).select_related(
            "expediente__persona"
        ):
            dudosos = []
            for grupo in (ficha.ingresos or {}, ficha.egresos or {}):
                for clave, valor in grupo.items():
                    if valor in (None, "", 0):
                        continue
                    if numeros.es_ambiguo(valor):
                        dudosos.append(f"{clave}=«{valor}» (dos lecturas)")
                        continue
                    if numeros.a_decimal_o(valor, None) is None:
                        dudosos.append(f"{clave}=«{valor}»")
            if dudosos:
                filas.append(f"Ficha {ficha.pk} de {ficha.expediente}: {', '.join(dudosos)}")
        return Hallazgo(
            "Fichas con montos que no se pueden leer",
            "Se suman como cero y mueven el estrato. Vuelva a verificarlas.",
            filas,
        )

    def _alertas_sin_expediente_con_persona(self):
        from apps.expediente.models import AlertaClinica

        huerfanas = AlertaClinica.objects.filter(expediente__persona__isnull=True)
        return Hallazgo(
            "Alertas clínicas sin persona detrás",
            "Una alerta que no apunta a nadie no avisa a nadie.",
            [f"Alerta {a.pk} ({a.tipo})" for a in huerfanas],
        )
