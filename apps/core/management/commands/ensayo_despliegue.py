"""
Ensaya el despliegue: no comprueba la configuración, la EJERCITA.

`check --deploy` mira los ajustes; esto usa el sistema. La diferencia importa
porque el fallo más caro del despliegue no se ve mirando:

    CSRF_TRUSTED_ORIGINS mal puesto → el sitio arranca, TODAS las páginas
    responden 200 y nadie puede iniciar sesión.

El 403 solo aparece al enviar el primer formulario, así que la única manera de
saberlo es enviar uno. Eso es lo que hace este comando: pide el formulario de
acceso, lo envía y comprueba que la sesión quedó abierta. Después recorre las
pantallas principales.

    python manage.py ensayo_despliegue
    python manage.py ensayo_despliegue --usuario admin --clave ****

Devuelve código de salida 1 si algo falla, para poder encadenarlo.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client
from django.urls import NoReverseMatch, reverse

# Lo que tiene que poder abrirse. Rutas y no nombres: es lo que teclea la gente.
PANTALLAS = [
    ("/", "portada"),
    ("/cuentas/login/", "acceso"),
]


class Command(BaseCommand):
    help = "Ejercita el sistema como lo haría un usuario: entra, navega y sale."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", default="", help="Cuenta con la que entrar.")
        parser.add_argument("--clave", default="", help="Su contraseña.")
        parser.add_argument(
            "--host",
            default="",
            help="Host con el que se piden las páginas (por omisión, el primero de ALLOWED_HOSTS).",
        )

    def handle(self, *args, **opciones):
        from django.conf import settings

        host = opciones["host"] or self._primer_host(settings.ALLOWED_HOSTS)
        # Se pide por HTTPS: en producción `SECURE_SSL_REDIRECT` manda todo lo
        # demás a un 301 y el ensayo mediría la redirección, no el sistema.
        cliente = Client(headers={"host": host}, secure=True)

        fallos = []
        self.stdout.write(self.style.MIGRATE_HEADING(f"Ensayo contra el host «{host}»"))

        for ruta, nombre in PANTALLAS:
            estado = self._abrir(cliente, ruta)
            self._linea(nombre, ruta, estado, estado and estado < 400)
            if not estado or estado >= 400:
                fallos.append(f"{ruta} ({nombre}) responde {estado}")

        fallos += self._probar_estaticos()
        self.acceso_ejercitado = False
        fallos += self._probar_acceso(cliente, host, opciones)
        if self.acceso_ejercitado and not fallos:
            fallos += self._probar_modulos(cliente, opciones["usuario"])

        self.stdout.write("")
        if fallos:
            self.stdout.write(self.style.ERROR(f"{len(fallos)} problema(s):"))
            for fallo in fallos:
                self.stdout.write(f"  · {fallo}")
            raise SystemExit(1)
        if self.acceso_ejercitado:
            self.stdout.write(self.style.SUCCESS("El sistema responde y se puede iniciar sesión."))
        else:
            # No decir «se puede iniciar sesión» sin haberlo intentado: esa
            # frase de más es justo la que haría inútil todo el ensayo.
            self.stdout.write(
                self.style.WARNING(
                    "El sistema responde. El acceso NO se ejercitó: repita con "
                    "--usuario y --clave antes de dar el despliegue por bueno."
                )
            )

    # ------------------------------------------------------------------ pasos

    def _primer_host(self, permitidos):
        """
        Un comodín de ALLOWED_HOSTS no sirve para pedir una página: `*` y
        `.unl.edu.ec` valen como permiso pero no son un nombre. Se toma el
        primero que sí lo sea.
        """
        for candidato in permitidos:
            if not candidato.startswith(("*", ".")):
                return candidato
        return "testserver"

    def _probar_estaticos(self):
        """
        En producción el manifiesto es la ley: `{% static %}` lanza si el
        fichero no se recogió. Es el fallo que dejó la imagen construyéndose
        «bien» y el sitio en blanco, así que se comprueba a propósito y no de
        rebote al pintar una plantilla.
        """
        from django.contrib.staticfiles.storage import staticfiles_storage

        fallos = []
        for ruta in ("css/sibu.css", "vendor/bootstrap/bootstrap.min.css"):
            try:
                staticfiles_storage.url(ruta)
            except Exception as exc:  # noqa: BLE001 - se reporta con su ruta
                self._linea("estático", ruta, type(exc).__name__, False)
                fallos.append(f"{ruta} no está en el manifiesto: ejecute collectstatic ({exc})")
            else:
                self._linea("estático", ruta, "ok", True)
        return fallos

    def _probar_acceso(self, cliente, host, opciones):
        """
        El paso que de verdad importa: enviar un formulario.

        Sin una cuenta con la que probar no se puede afirmar nada, así que se
        dice en vez de dar por bueno el silencio.
        """
        usuario, clave = opciones["usuario"], opciones["clave"]
        if not (usuario and clave):
            self.stdout.write(
                self.style.WARNING(
                    "  ! sin --usuario y --clave no se puede ejercitar el acceso, "
                    "que es donde aparece el fallo de CSRF_TRUSTED_ORIGINS"
                )
            )
            return []

        if not get_user_model().objects.filter(username=usuario).exists():
            return [f"la cuenta «{usuario}» no existe en esta base de datos"]

        url = reverse("login")
        pagina = cliente.get(url)
        token = pagina.cookies.get("csrftoken")
        respuesta = cliente.post(
            url,
            {"username": usuario, "password": clave},
            headers={"referer": f"https://{host}{url}"},
        )
        self.acceso_ejercitado = True
        entro = "_auth_user_id" in cliente.session
        self._linea("acceso con formulario", url, respuesta.status_code, entro)

        if entro:
            return []
        if respuesta.status_code == 403:
            return [
                "el formulario de acceso responde 403: revise CSRF_TRUSTED_ORIGINS. "
                f"Debe incluir «https://{host}» "
                "(con el puerto si no es el 443). Es el fallo que deja el sitio "
                "en pie y a todo el mundo fuera."
            ]
        if token is None:
            return ["no se recibió la cookie CSRF: revise el proxy y las cookies seguras"]
        return ["no se pudo iniciar sesión: compruebe la cuenta y la contraseña"]

    def _probar_modulos(self, cliente, usuario):
        """
        Abre lo que esta cuenta ve en el menú.

        La navegación sale del RBAC, así que esto recorre exactamente lo que
        esta persona va a pulsar el primer día. Un 403 aquí sería una
        contradicción entre el menú y la vista —el menú ofrece algo que la
        vista niega—, no un permiso mal puesto, y por eso cuenta como fallo.
        """
        from django.contrib.auth import get_user_model

        from apps.core.navegacion import modulos_visibles

        cuenta = get_user_model().objects.get(username=usuario)
        fallos = []
        for modulo in modulos_visibles(cuenta):
            try:
                ruta = reverse(modulo.url_name)
            except NoReverseMatch:
                continue
            estado = self._abrir(cliente, ruta)
            self._linea(modulo.etiqueta, ruta, estado, bool(estado) and estado < 400)
            if not estado or estado >= 400:
                fallos.append(
                    f"{modulo.etiqueta} ({ruta}) responde {estado} para «{usuario}», "
                    "y el menú se lo ofrece"
                )
        return fallos

    def _abrir(self, cliente, ruta):
        try:
            return cliente.get(ruta).status_code
        except Exception as exc:  # noqa: BLE001 - se reporta con su ruta
            self.stdout.write(self.style.ERROR(f"    {type(exc).__name__}: {exc}"))
            return None

    def _linea(self, nombre, ruta, estado, bien):
        marca = self.style.SUCCESS("✓") if bien else self.style.ERROR("✗")
        self.stdout.write(f"  {marca} {nombre:26} {ruta:24} {estado}")
