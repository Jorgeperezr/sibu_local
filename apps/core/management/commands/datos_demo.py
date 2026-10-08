"""
Siembra un escenario completo para poder PROBAR el sistema.

`seed_inicial` deja secciones, servicios y roles: la estructura, pero ni un
solo paciente. Con la base así, todas las pantallas salen vacías y no hay con
qué entrar. Este comando llena ese hueco: crea un usuario por servicio, varios
pacientes con su expediente, y actividad real en cada módulo —citas, historias
clínicas, triaje, odontograma, recetas con stock, órdenes de laboratorio,
talleres y becas— para que el sistema se pueda recorrer de punta a punta.

    python manage.py datos_demo            # siembra (idempotente)
    python manage.py datos_demo --limpiar  # borra lo sembrado y vuelve a empezar

Al terminar imprime las credenciales de acceso.

ADVERTENCIA: son datos ficticios y contraseñas conocidas. Solo corre con
DEBUG=True, igual que `perfil_dev`: en el servidor real esto sería una puerta
abierta con pacientes inventados dentro del expediente único.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

CLAVE = "sibu-demo-2026"

# Cuenta de administración solicitada para probar el sistema completo.
#
# El usuario es la cédula, que es como el modelo `Usuario` dice que se
# identifica una cuenta ("username = cédula o usuario institucional").
#
# La contraseña no pasa la política del proyecto —AUTH_PASSWORD_VALIDATORS pide
# 12 caracteres, prohíbe que se parezca al usuario y rechaza las puramente
# numéricas; esta incumple las tres—, y no hace falta que la pase: los
# validadores solo actúan sobre formularios (el admin, `createsuperuser`, el
# cambio de contraseña), no sobre `set_password()`. Así esta cuenta existe sin
# rebajar la política que protege al resto, que sigue intacta.
#
# ADVERTENCIA: una contraseña igual al usuario, y además la cédula de una
# persona real, no puede salir de aquí. Este comando se niega a correr con
# DEBUG=False, que es lo que impide que llegue al servidor de la Unidad.
# Sin correo, y a propósito: `jorge.perez@unl.edu.ec` es el buzón de la cuenta
# de Psicología, y una dirección institucional identifica a UNA cuenta. Con la
# misma en dos, cualquier flujo que parta del correo —recuperar la contraseña,
# avisar de algo— quedaría sin saber a cuál de las dos se refiere. Esta cuenta
# se identifica por la cédula, que es lo que se teclea para entrar.
ADMIN = {
    "username": "1104346091",
    "cedula": "1104346091",
    "email": "",
    "first_name": "Jorge",
    "last_name": "Pérez",
    "clave": "1104346091",
}

# Cédulas ficticias que pasan el módulo 10 ecuatoriano: `Persona.save()` las
# valida, así que un número inventado a ojo no entraría.
PACIENTES = [
    # (cédula, nombres, apellidos, sexo, vínculo con la UNL)
    ("1101001004", "María Fernanda", "Jaramillo Ochoa", "F", "estudiante"),
    ("1102002001", "Luis Alberto", "Cueva Riofrío", "M", "estudiante"),
    ("1103003008", "Ana Belén", "Sarango Guamán", "F", "estudiante"),
    ("1104004005", "Diego Armando", "Tandazo Loaiza", "M", "estudiante"),
    ("1105005001", "Carmen Rocío", "Chamba Vivanco", "F", "estudiante"),
    ("1106006008", "Jorge Andrés", "Espinosa Torres", "M", "estudiante"),
    ("1109009009", "Silvia Patricia", "Ruiz Montoya", "F", "estudiante"),
    ("1110001003", "Kevin Joel", "Padilla Ortega", "M", "estudiante"),
    ("1111002000", "Doris Elizabeth", "Camacho León", "F", "docente"),
    ("1112003007", "Fabián Eduardo", "Correa Salinas", "M", "docente"),
    ("1703003002", "Nancy Alexandra", "Bustamante Rojas", "F", "administrativo"),
    ("1704004009", "Byron Patricio", "Aguilar Zúñiga", "M", "trabajador"),
]

# (username, nombre, apellido, código de servicio, rol)
# Profesionales de la Unidad.
#
# Los cinco primeros son las personas reales de cada servicio: el usuario es lo
# que va antes de la @ de su correo institucional, y la contraseña es lo mismo.
# Esa contraseña es tan débil como parece —es el usuario— y por eso este comando
# se niega a correr con DEBUG=False: cuando el sistema entre en servicio, cada
# uno debe fijar la suya con `manage.py changepassword <usuario>`.
#
# Los cuatro restantes siguen siendo cuentas de prueba con nombres inventados,
# porque de esos servicios no se ha indicado quién los atiende. Usan la clave
# común `CLAVE`.
PROFESIONALES = [
    {
        "usuario": "jhoely.lalangui",
        "nombres": "Jhoely Michelle",
        "apellidos": "Lalangui Iñiguez",
        "correo": "jhoely.lalangui@unl.edu.ec",
        "servicio": "medicina",
        "rol": "profesional",
    },
    {
        "usuario": "andrea.ambuludi",
        "nombres": "Andrea Paulina",
        "apellidos": "Ambuludi Chamba",
        "correo": "andrea.ambuludi@unl.edu.ec",
        "servicio": "enfermeria",
        "rol": "profesional",
    },
    {
        "usuario": "daniel.cabrera",
        "nombres": "Daniel Francisco",
        "apellidos": "Cabrera Vaca",
        "correo": "daniel.cabrera@unl.edu.ec",
        "servicio": "odontologia",
        "rol": "profesional",
    },
    {
        "usuario": "jorge.perez",
        "nombres": "Jorge Eduardo",
        "apellidos": "Pérez Rodríguez",
        "correo": "jorge.perez@unl.edu.ec",
        "servicio": "psicologia",
        "rol": "profesional",
    },
    {
        "usuario": "victor.samaniego",
        "nombres": "Víctor Manuel",
        "apellidos": "Samaniego Aguirre",
        "correo": "victor.samaniego@unl.edu.ec",
        "servicio": "psicopedagogia",
        "rol": "profesional",
    },
    # Sin persona asignada todavía: nombres de prueba y clave común.
    {
        "usuario": "laboratorista",
        "nombres": "Paola",
        "apellidos": "Bermeo",
        "correo": "",
        "servicio": "laboratorio-clinico",
        "rol": "laboratorio",
        "clave": CLAVE,
    },
    {
        "usuario": "farmaceutico",
        "nombres": "Iván",
        "apellidos": "Costa",
        "correo": "",
        "servicio": "farmacia",
        "rol": "farmacia",
        "clave": CLAVE,
    },
    {
        "usuario": "trabajadora",
        "nombres": "Rosa",
        "apellidos": "Célleri",
        "correo": "",
        "servicio": "trabajo-social",
        "rol": "profesional",
        "clave": CLAVE,
    },
    {
        "usuario": "becas",
        "nombres": "Pablo",
        "apellidos": "Quezada",
        "correo": "",
        "servicio": "becas-y-ayudas-economicas",
        "rol": "profesional",
        "clave": CLAVE,
    },
]

# Las tres cuentas que no atienden un servicio. Se listan aquí, y no sueltas
# dentro de cada método, porque `_limpiar` se olvidaba de `administrador` y la
# dejaba viva —con su contraseña conocida— después de un borrado que decía
# haberlo limpiado todo.
OTRAS_CUENTAS = ["administrador", "director", "estudiante"]


def clave_de(profesional: dict) -> str:
    """
    La contraseña del profesional: la que traiga, o su propio usuario.

    Que sea igual al usuario es lo pedido, y lo que obliga a que esto no salga
    de un entorno de prueba.
    """
    return profesional.get("clave") or profesional["usuario"]


class Command(BaseCommand):
    help = "Crea usuarios, pacientes y actividad de ejemplo para probar el sistema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Borra los datos de demostración antes de sembrarlos de nuevo.",
        )

    def handle(self, *args, **opciones):
        # Estos datos son ficticios y las contraseñas, públicas. En producción
        # esto no es una comodidad: es un expediente único contaminado.
        if not settings.DEBUG:
            raise CommandError(
                "datos_demo solo corre con DEBUG=True. Son pacientes inventados y "
                "contraseñas conocidas; en el servidor real no tienen cabida."
            )

        if opciones["limpiar"]:
            self._limpiar()

        with transaction.atomic():
            self._sembrar()

        self._credenciales()

    # ------------------------------------------------------------------ borrar

    def _limpiar(self):
        from apps.expediente.models import Persona
        from apps.farmacia.models import Lote
        from apps.usuarios.models import Usuario

        cedulas = [c for c, *_ in PACIENTES]
        usuarios = [p["usuario"] for p in PROFESIONALES] + OTRAS_CUENTAS + [ADMIN["username"]]
        self._borrar_protegido(Persona.objects.filter(cedula__in=cedulas))
        # Las cuentas también están protegidas: su perfil, los movimientos de
        # inventario que registraron y los talleres que facilitan. Todo eso es
        # dato de demostración y se va con ellas.
        self._borrar_protegido(Usuario.objects.filter(username__in=usuarios))
        # Y los lotes DETRÁS de los movimientos, no antes: al borrarse las
        # cuentas se llevan por delante la bitácora del inventario, y un lote
        # con saldo y sin un solo movimiento que lo explique es exactamente la
        # incoherencia que la pantalla de inventario existe para impedir. Lo
        # detectó `revisar_datos` la primera vez que se ejecutó.
        self._borrar_protegido(Lote.objects.all())
        self.stdout.write("Datos de demostración eliminados.")

    def _borrar_protegido(self, consulta, profundidad=0):
        """
        Borra apartando primero lo que lo protege.

        El comentario anterior decía que bastaba con borrar «desde la persona
        hacia abajo con el borrado en cascada de Django», y no era cierto:
        `Expediente.persona` es PROTECT, así que `--limpiar` reventaba con
        ProtectedError y no borraba nada. Debajo hay cuatro niveles más
        —atención, orden de laboratorio, receta, derivación—, y cablear ese
        orden a mano lo dejaría roto la próxima vez que se añada un modelo.

        En lugar de eso se le pregunta a Django: cuando se planta, la excepción
        trae exactamente qué filas estorban. Se borran esas y se reintenta.
        """
        if profundidad > 10:
            raise CommandError(
                "No se pudo borrar: hay una cadena de claves protegidas más larga de lo "
                "esperado. Revise si un modelo nuevo usa on_delete=PROTECT en ciclo."
            )
        try:
            consulta.delete()
            return
        except ProtectedError as error:
            estorban: dict = {}
            for objeto in error.protected_objects:
                estorban.setdefault(type(objeto), []).append(objeto.pk)

        for modelo, pks in estorban.items():
            self._borrar_protegido(modelo.objects.filter(pk__in=pks), profundidad + 1)
        self._borrar_protegido(consulta, profundidad + 1)

    # ----------------------------------------------------------------- sembrar

    def _sembrar(self):
        from apps.core.models import PeriodoAcademico, Servicio
        from apps.expediente.models import Expediente, Persona
        from apps.usuarios.models import PerfilProfesional, Rol, Usuario

        if not Servicio.objects.exists():
            raise CommandError("No hay servicios. Ejecute antes: python manage.py seed_inicial")

        # --- Usuarios ------------------------------------------------------
        self.perfiles = {}
        for datos in PROFESIONALES:
            codigo = datos["servicio"]
            servicio = Servicio.objects.filter(codigo=codigo).first()
            if servicio is None:
                continue
            u, _ = Usuario.objects.get_or_create(username=datos["usuario"])
            # Fuera de `defaults`, para que resembrar corrija también las
            # cuentas que ya existían con otro nombre o sin correo.
            u.first_name = datos["nombres"]
            u.last_name = datos["apellidos"]
            u.email = datos["correo"]
            u.rol_principal = datos["rol"]
            u.set_password(clave_de(datos))
            u.save()
            perfil, _ = PerfilProfesional.objects.get_or_create(
                usuario=u, defaults={"seccion": servicio.seccion}
            )
            perfil.servicios.add(servicio)
            self.perfiles[codigo] = perfil

        # Dirección: ve el tablero, no el contenido clínico.
        director, _ = Usuario.objects.get_or_create(
            username="director",
            defaults={
                "first_name": "Gabriela",
                "last_name": "Aguirre",
                "rol_principal": Rol.DIRECTOR,
            },
        )
        director.set_password(CLAVE)
        director.save()

        self._administrador()

        # --- Personas y expedientes ----------------------------------------
        self.expedientes = []
        for i, (cedula, nombres, apellidos, sexo, vinculo) in enumerate(PACIENTES):
            persona, _ = Persona.objects.get_or_create(
                cedula=cedula,
                defaults={
                    "nombres": nombres,
                    "apellidos": apellidos,
                    "sexo": sexo,
                    "fecha_nacimiento": date(2003, 1, 1) + timedelta(days=i * 200),
                    "tipo_vinculo": vinculo,
                    "correo_institucional": f"{cedula}@unl.edu.ec",
                    "celular": f"09{cedula[:8]}",
                },
            )
            exp, _ = Expediente.objects.get_or_create(
                persona=persona, defaults={"numero_expediente": f"EXP-{cedula}"}
            )
            self.expedientes.append(exp)

        # El estudiante del portal se vincula al primer expediente.
        estudiante, _ = Usuario.objects.get_or_create(
            username="estudiante",
            defaults={
                "first_name": PACIENTES[0][1],
                "last_name": PACIENTES[0][2],
                "rol_principal": Rol.USUARIO_FINAL,
            },
        )
        estudiante.set_password(CLAVE)
        estudiante.save()
        self._vincular_portal(estudiante, self.expedientes[0])

        self.periodo, _ = PeriodoAcademico.objects.get_or_create(
            codigo="2026-1",
            defaults={
                "nombre": "Abril–Agosto 2026",
                "fecha_inicio": date(2026, 4, 1),
                "fecha_fin": date(2026, 8, 31),
                "vigente": True,
            },
        )

        self._agenda_y_citas()
        self._medicina_y_enfermeria()
        self._odontologia()
        self._farmacia()
        self._laboratorio()
        self._psicologia()
        self._talleres_y_becas()

    def _administrador(self):
        """
        Cuenta con acceso a todo, para recorrer el sistema sin cambiar de sesión.

        ADVERTENCIA: su perfil incluye los NUEVE servicios, Psicología entre
        ellos. Eso rompe el sello de confidencialidad a propósito —igual que
        `perfil_dev`— para poder navegar en desarrollo. En producción cada
        profesional lleva únicamente su servicio, y esta cuenta no debe existir:
        por eso el comando entero se niega a correr con DEBUG=False.
        """
        from django.contrib.auth.models import Permission

        from apps.core.models import Servicio
        from apps.usuarios.models import PerfilProfesional, Rol, Usuario

        admin, _ = Usuario.objects.get_or_create(
            username=ADMIN["username"],
            defaults={"email": ADMIN["email"]},
        )
        admin.email = ADMIN["email"]
        admin.first_name = ADMIN["first_name"]
        admin.last_name = ADMIN["last_name"]
        # `Usuario.cedula` es única: se libera de cualquier otra cuenta antes de
        # asignarla, o el guardado fallaría con IntegrityError sobre una siembra
        # anterior en la que la llevara otro usuario.
        Usuario.objects.filter(cedula=ADMIN["cedula"]).exclude(pk=admin.pk).update(cedula=None)
        admin.cedula = ADMIN["cedula"]

        # El rol es PROFESIONAL, no ADMIN_GENERAL, y esto no es un descuido:
        # `rbac.atenciones_visibles` le niega el contenido clínico a quien sea
        # administrador —`es_admin()` cubre ADMIN_GENERAL y is_superuser— por
        # separación de funciones. Con rol de administrador, esta cuenta abriría
        # cada expediente y vería "0 atenciones visibles", que es justo lo
        # contrario de poder probar el sistema.
        admin.rol_principal = Rol.PROFESIONAL

        # Para el admin de Django se usan permisos explícitos en lugar de
        # is_superuser: el atajo habría vuelto a activar `es_admin()` y a
        # ocultarle el contenido clínico.
        admin.is_staff = True
        admin.is_superuser = False
        admin.set_password(ADMIN["clave"])
        admin.save()
        admin.user_permissions.set(Permission.objects.all())

        seccion = Servicio.objects.filter(codigo="medicina").first()
        perfil, _ = PerfilProfesional.objects.get_or_create(
            usuario=admin,
            defaults={"seccion": seccion.seccion if seccion else None},
        )
        perfil.servicios.set(Servicio.objects.all())
        self.admin = admin

        # Cuenta de Administrador General, aparte y a propósito.
        #
        # La de arriba tiene rol PROFESIONAL para poder ver contenido clínico;
        # con eso, ningún usuario sembrado llegaba a lo que sí es propio de
        # quien administra —cargar la base institucional, ver el padrón—, porque
        # esas pantallas piden ADMIN_GENERAL. Y no se podía dar ese rol a la
        # cuenta de arriba sin dejarla ciega ante las atenciones.
        #
        # Que sean dos cuentas no es un rodeo del entorno de prueba: es la
        # separación de funciones real. Quien administra el sistema no lee
        # historias clínicas, y esta cuenta lo demuestra en vez de contarlo.
        administrador, _ = Usuario.objects.get_or_create(
            username="administrador",
            defaults={"email": "administracion@unl.edu.ec"},
        )
        administrador.first_name = "Ana"
        administrador.last_name = "Ordóñez"
        administrador.rol_principal = Rol.ADMIN_GENERAL
        administrador.is_staff = True
        administrador.is_superuser = False
        administrador.set_password(CLAVE)
        administrador.save()
        administrador.user_permissions.set(Permission.objects.all())

    # ------------------------------------------------------------- por módulo

    def _vincular_portal(self, usuario, expediente):
        from apps.portal.models import VinculacionPortal

        VinculacionPortal.objects.get_or_create(
            usuario=usuario,
            defaults={
                "expediente": expediente,
                "verificado": True,
                "correo_destino": expediente.persona.correo_institucional,
                "token_hash": "demo",
                "token_expira_en": timezone.now() + timedelta(days=365),
            },
        )

    def _agenda_y_citas(self):
        from apps.citas import services
        from apps.citas.models import Agenda
        from apps.core.models import Servicio

        medicina = Servicio.objects.get(codigo="medicina")
        perfil = self.perfiles.get("medicina")
        if perfil is None:
            return

        # Agenda de lunes a viernes, para que haya turnos que reservar.
        for dia in range(5):
            Agenda.objects.get_or_create(
                profesional=perfil,
                servicio=medicina,
                dia_semana=dia,
                hora_inicio="08:00",
                defaults={"hora_fin": "12:00", "duracion_turno_min": 20},
            )

        # Una cita en el próximo día hábil, a las 09:00 hora de Loja.
        proximo = timezone.localtime() + timedelta(days=1)
        while proximo.weekday() > 4:
            proximo += timedelta(days=1)
        inicio = proximo.replace(hour=9, minute=0, second=0, microsecond=0)
        for exp in self.expedientes[:3]:
            try:
                services.reservar_cita(
                    expediente=exp,
                    servicio=medicina,
                    profesional=perfil,
                    fecha_hora=inicio,
                    duracion_min=20,
                )
            except Exception:  # noqa: BLE001 - turno ocupado o fuera de agenda
                pass
            inicio += timedelta(minutes=20)

    def _medicina_y_enfermeria(self):
        from apps.enfermeria.models import SignosVitales
        from apps.medicina import services

        med, enf = self.perfiles.get("medicina"), self.perfiles.get("enfermeria")
        if med is None:
            return

        for exp in self.expedientes[:3]:
            if enf is not None and not SignosVitales.objects.filter(expediente=exp).exists():
                SignosVitales.objects.create(
                    expediente=exp,
                    temperatura="36.8",
                    fc=72,
                    fr=16,
                    pa_sistolica=118,
                    pa_diastolica=76,
                    sat_o2=97,
                    peso="62.5",
                    talla="1.65",
                    responsable=enf,
                )
            if not exp.atenciones.filter(servicio__codigo="medicina").exists():
                services.crear_atencion_medicina(
                    expediente=exp, profesional=med, motivo="Cefalea de 3 días de evolución"
                )

    def _odontologia(self):
        from apps.odontologia import services

        perfil = self.perfiles.get("odontologia")
        if perfil is None:
            return
        for exp in self.expedientes[3:5]:
            if exp.atenciones.filter(servicio__codigo="odontologia").exists():
                continue
            hc = services.crear_atencion_odontologia(
                expediente=exp, profesional=perfil, motivo="Control y profilaxis"
            )
            services.registrar_estado_pieza(hc.atencion, "16", "cariado")
            services.registrar_estado_pieza(hc.atencion, "26", "obturado")
            services.registrar_estado_pieza(hc.atencion, "36", "sano")

    def _farmacia(self):
        from apps.farmacia import services
        from apps.farmacia.models import Lote, Medicamento

        perfil = self.perfiles.get("farmacia")
        if perfil is None:
            return

        catalogo = [
            ("MED-001", "Paracetamol", "500 mg", "tableta", 50),
            ("MED-002", "Ibuprofeno", "400 mg", "tableta", 40),
            ("MED-003", "Amoxicilina", "500 mg", "cápsula", 30),
            ("MED-004", "Loratadina", "10 mg", "tableta", 20),
        ]
        medicamentos = []
        for codigo, dci, conc, forma, minimo in catalogo:
            med, _ = Medicamento.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "dci": dci,
                    "concentracion": conc,
                    "forma_farmaceutica": forma,
                    "unidad_medida": forma,
                    "stock_minimo": minimo,
                },
            )
            medicamentos.append(med)

        hoy = timezone.localdate()
        for i, med in enumerate(medicamentos):
            # Dos lotes con caducidades distintas: así el FEFO se ve funcionar.
            for sufijo, dias, cantidad in (("A", 120, 200), ("B", 400, 300)):
                numero = f"L-{med.codigo}-{sufijo}"
                # Se pregunta si el lote ya está, en vez de ingresarlo y
                # atrapar el fallo: `ingresar_lote` NO falla cuando el lote
                # existe, SUMA. Con el `except Exception: pass` que había aquí
                # —comentado «ya ingresado»— cada siembra añadía otras 200
                # unidades, y tres siembras dejaban 600 donde se declaran 200.
                # El comando se documenta como idempotente y el inventario no
                # lo era.
                if Lote.objects.filter(medicamento=med, numero_lote=numero).exists():
                    continue
                services.ingresar_lote(
                    med,
                    numero,
                    cantidad,
                    hoy + timedelta(days=dias + i),
                    usuario=perfil,
                )

        # Una receta pendiente en el mostrador, emitida desde una consulta.
        atencion = self._primera_atencion("medicina")
        if atencion is not None and not atencion.recetas.exists():
            services.emitir_receta(
                atencion,
                [
                    {
                        "medicamento_id": medicamentos[0].id,
                        "cantidad_prescrita": 12,
                        "dosis": "1 tableta",
                        "frecuencia": "cada 8 horas",
                        "duracion": "4 días",
                    },
                    {
                        "medicamento_id": medicamentos[1].id,
                        "cantidad_prescrita": 6,
                        "dosis": "1 tableta",
                        "frecuencia": "cada 12 horas",
                        "duracion": "3 días",
                    },
                ],
            )

    def _laboratorio(self):
        from apps.laboratorio import services
        from apps.laboratorio.models import Examen, ParametroExamen

        perfil = self.perfiles.get("laboratorio-clinico")
        if perfil is None:
            return

        examen, creado = Examen.objects.get_or_create(
            codigo="BH", defaults={"nombre": "Biometría hemática"}
        )
        if creado:
            ParametroExamen.objects.create(
                examen=examen, nombre="Hemoglobina", unidad="g/dL", ref_min=12, ref_max=16
            )
            ParametroExamen.objects.create(
                examen=examen, nombre="Leucocitos", unidad="10³/µL", ref_min=4, ref_max=11
            )

        atencion = self._primera_atencion("medicina")
        if atencion is not None and not atencion.ordenes_lab.exists():
            services.crear_orden(atencion, [examen.id], diagnostico_presuntivo="Descartar anemia")

    def _psicologia(self):
        """
        Un proceso psicológico, para que el servicio no aparezca vacío.

        No se toca el sello: estos datos solo los verá quien pertenezca a
        Psicología, igual que en producción.
        """
        from apps.psicologia import services

        perfil = self.perfiles.get("psicologia")
        if perfil is None:
            return
        exp = self.expedientes[5]
        if exp.atenciones.filter(servicio__codigo="psicologia").exists():
            return
        services.crear_ficha(
            expediente=exp,
            profesional=perfil,
            motivo="Ansiedad ante evaluaciones",
            usuario=perfil.usuario,
        )

    def _talleres_y_becas(self):
        from apps.becas import services as becas_services
        from apps.becas.models import TipoBeca
        from apps.core.models import Servicio
        from apps.talleres import services as talleres_services

        # Taller: registrar a alguien en un taller NO le abre expediente.
        perfil_psico = self.perfiles.get("psicologia")
        if perfil_psico is not None:
            psico = Servicio.objects.get(codigo="psicologia")
            from apps.talleres.models import Taller

            if not Taller.objects.exists():
                taller = talleres_services.crear_taller(
                    servicio=psico,
                    responsable=perfil_psico,
                    tema="Manejo del estrés en época de exámenes",
                    fecha=timezone.localdate(),
                    usuario=perfil_psico.usuario,
                )
                for cedula, *_ in PACIENTES[:4]:
                    try:
                        talleres_services.registrar_participante(taller, cedula=cedula)
                    except Exception:  # noqa: BLE001
                        pass

        # Beca sobre un expediente distinto del que ya tiene actividad clínica.
        perfil_becas = self.perfiles.get("becas-y-ayudas-economicas")
        if perfil_becas is not None:
            tipo, _ = TipoBeca.objects.get_or_create(
                codigo="socioeconomica",
                defaults={"nombre": "Beca socioeconómica"},
            )
            try:
                becas_services.registrar_beneficiario(
                    expediente=self.expedientes[1],
                    tipo_beca=tipo,
                    periodo_desde=self.periodo,
                    profesional=perfil_becas,
                    monto_o_porcentaje="50 %",
                    resolucion="RES-UNL-2026-014",
                    usuario=perfil_becas.usuario,
                )
            except Exception:  # noqa: BLE001 - ya registrada
                pass

    # ----------------------------------------------------------------- apoyo

    def _primera_atencion(self, codigo_servicio):
        for exp in self.expedientes:
            atencion = exp.atenciones.filter(servicio__codigo=codigo_servicio).first()
            if atencion is not None:
                return atencion
        return None

    def _credenciales(self):
        ok = self.style.SUCCESS
        self.stdout.write("")
        self.stdout.write(ok("Datos de demostración listos."))
        self.stdout.write("")
        self.stdout.write(ok("  Cuenta con acceso a todo (los nueve servicios y /admin/):"))
        self.stdout.write(f"    usuario:    {ADMIN['username']}")
        self.stdout.write(f"    contraseña: {ADMIN['clave']}")
        self.stdout.write("")
        self.stdout.write(ok("  Profesionales de la Unidad (contraseña = usuario):"))
        self.stdout.write("")
        self.stdout.write(f"  {'usuario':<18} {'contraseña':<18} {'nombre':<32} atiende")
        self.stdout.write("  " + "-" * 88)
        for p in PROFESIONALES:
            if p["servicio"] not in self.perfiles or p.get("clave"):
                continue
            nombre = f"{p['nombres']} {p['apellidos']}"
            self.stdout.write(
                f"  {p['usuario']:<18} {clave_de(p):<18} {nombre:<32} {p['servicio']}"
            )
        self.stdout.write("")
        self.stdout.write(f"  Cuentas de prueba, contraseña: {CLAVE}")
        self.stdout.write("")
        for p in PROFESIONALES:
            if p["servicio"] in self.perfiles and p.get("clave"):
                self.stdout.write(f"  {p['usuario']:<18} su servicio ({p['servicio']})")
        self.stdout.write(
            f"  {'administrador':<18} base institucional y gestión, sin contenido clínico"
        )
        self.stdout.write(f"  {'director':<18} tablero de gestión, sin contenido clínico")
        self.stdout.write(f"  {'estudiante':<18} portal del paciente (/portal/)")
        self.stdout.write("")
        self.stdout.write(
            "  Cada profesional ve SOLO su servicio: es el comportamiento real.\n"
            "  Para recorrerlo todo con una cuenta, use 'python manage.py perfil_dev'."
        )
        self.stdout.write("")
