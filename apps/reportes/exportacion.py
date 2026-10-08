"""
Volcado del historial de atenciones a una hoja de cálculo compartida.

Se pega el enlace de una hoja de Google compartida con permiso de editor y el
sistema escribe ahí las atenciones.

Tres decisiones que conviene entender antes de tocar esto:

**1. Psicología no sale nunca, ni para Psicología.** El sello dice que su
contenido no es accesible FUERA del servicio, y una hoja compartida es fuera:
quien tenga el enlace la lee sin pasar por SIBU, no queda registrado quién la
abrió y no se puede revocar. Es el mismo razonamiento que impide a un servicio
confidencial emitir referencias externas —«el resumen saldría de la Unidad»—.
Y como una exportación parcial que calla que es parcial hace contar mal a quien
la recibe, `resumen_de_exportacion` dice cuántas filas se retuvieron.

**2. No se exporta texto clínico.** Fecha, servicio, profesional y a quién se
atendió: eso es gestión y es lo que sirve para un informe. El motivo de
consulta, los diagnósticos y las notas son el contenido del expediente, y en
una hoja que el destinatario puede editar dejan de tener dueño.

**3. Cada quien exporta lo que ve.** La exportación no es una puerta trasera al
RBAC: pasa por `rbac.atenciones_visibles`, igual que la pantalla.

El proveedor es intercambiable, como en académico, firma y evidencias: sin
credenciales de Google el sistema dice que no está disponible en vez de
reventar, y el CSV que ya existía sigue funcionando.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.usuarios import rbac

# Columnas del volcado. Gestión, no contenido: ver la decisión 2 de arriba.
ENCABEZADOS = [
    "Fecha",
    "Hora",
    "Servicio",
    "Profesional",
    "Cédula",
    "Paciente",
    "Vínculo",
    "Facultad",
    "Carrera",
    "Expediente",
]

# `docs.google.com/spreadsheets/d/<id>/…`, o el id pelado. Se acepta la barra de
# direcciones tal cual se copia: exigir que el usuario extraiga el id a mano es
# pedirle que haga de intérprete.
_PATRON_URL = re.compile(r"spreadsheets/d/([a-zA-Z0-9_-]{10,})")
_PATRON_ID = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


def id_de_hoja(enlace: str) -> str:
    """El identificador de la hoja a partir de lo que se pegó."""
    texto = (enlace or "").strip()
    coincidencia = _PATRON_URL.search(texto)
    if coincidencia:
        return coincidencia.group(1)
    if _PATRON_ID.match(texto):
        return texto
    raise ValidationError(
        "Eso no parece una hoja de cálculo de Google. Pegue el enlace de la "
        "barra de direcciones, que empieza por "
        "https://docs.google.com/spreadsheets/d/…"
    )


# ------------------------------------------------------------ qué se exporta


def verificar_exportable(codigo_servicio: str) -> None:
    """
    Lanza si el servicio no puede exportar su historial.

    Se comprueba aparte de filtrar porque hay que poder DECIRLO: un servicio
    confidencial que pulsara el botón obtendría un archivo vacío sin entender
    por qué, y un vacío inexplicado se lee como un fallo del sistema.
    """
    if codigo_servicio in rbac.SERVICIOS_CONFIDENCIALES:
        raise ValidationError(
            "Este servicio no exporta su historial: su contenido es confidencial "
            "y un archivo descargado sale de la Unidad igual que una hoja "
            "compartida. Los conteos agregados sí están en el informe estadístico."
        )


def _atenciones_exportables(usuario, servicio: str = ""):
    """
    Lo que este usuario puede ver, menos los servicios confidenciales.

    El `exclude` va DESPUÉS del filtro del RBAC y no en su lugar: si mañana
    `atenciones_visibles` se afloja, esto sigue sin dejar salir lo sellado.

    `servicio` acota a uno solo, para el botón que vive en cada bandeja: quien
    atiende en dos no quiere el revuelto de los dos. No amplía nada —el filtro
    del RBAC ya corrió—, así que pedir un servicio ajeno por la URL devuelve
    vacío en vez de datos.
    """
    from apps.expediente.models import Atencion

    visibles = rbac.atenciones_visibles(usuario, Atencion.objects.all())
    consulta = visibles.exclude(servicio__codigo__in=rbac.SERVICIOS_CONFIDENCIALES)
    if servicio:
        consulta = consulta.filter(servicio__codigo=servicio)
    return consulta


def _retenidas(usuario, servicio: str = "") -> int:
    from apps.expediente.models import Atencion

    return (
        rbac.atenciones_visibles(usuario, Atencion.objects.all())
        .filter(servicio__codigo__in=rbac.SERVICIOS_CONFIDENCIALES)
        .count()
    )


def historial(usuario, desde=None, hasta=None, servicio: str = "") -> list[dict]:
    """Las filas que se volcarían, en el orden en que van a la hoja."""
    consulta = (
        _atenciones_exportables(usuario, servicio)
        .select_related("expediente__persona", "servicio", "profesional__usuario")
        .order_by("-fecha_hora")
    )
    if desde:
        consulta = consulta.filter(fecha_hora__date__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha_hora__date__lte=hasta)

    academicos = _academicos_de(consulta)
    filas = []
    for atencion in consulta:
        persona = atencion.expediente.persona
        academico = academicos.get(persona.pk)
        profesional = getattr(atencion.profesional, "usuario", None)
        filas.append(
            {
                "Fecha": atencion.fecha_hora.date().isoformat(),
                "Hora": atencion.fecha_hora.strftime("%H:%M"),
                "Servicio": atencion.servicio.nombre,
                "Profesional": (
                    profesional.get_full_name() or profesional.username if profesional else ""
                ),
                "Cédula": persona.cedula,
                "Paciente": persona.nombre_completo,
                "Vínculo": persona.get_tipo_vinculo_display(),
                "Facultad": academico.facultad if academico else "",
                "Carrera": academico.carrera if academico else "",
                "Expediente": atencion.expediente.numero_expediente,
            }
        )
    return filas


def _academicos_de(consulta) -> dict:
    """El dato académico más reciente de cada persona, en UNA consulta."""
    from apps.academico.models import DatoAcademico

    personas = {a.expediente.persona_id for a in consulta}
    if not personas:
        return {}
    academicos = {}
    for dato in DatoAcademico.objects.filter(persona_id__in=personas).order_by(
        "persona_id", "-periodo__codigo"
    ):
        academicos.setdefault(dato.persona_id, dato)
    return academicos


def resumen_de_exportacion(usuario, desde=None, hasta=None, servicio: str = "") -> dict:
    """
    Qué saldría y qué se queda. Se muestra ANTES de volcar.

    Una exportación parcial que calla que es parcial hace contar mal a quien la
    recibe: por eso las retenidas se cuentan y se dicen.
    """
    return {
        "exportables": len(historial(usuario, desde, hasta, servicio)),
        "retenidas_por_confidencialidad": _retenidas(usuario, servicio),
    }


# --------------------------------------------------------------- proveedores


class HojaCalculoProvider(ABC):
    codigo: str = ""
    nombre: str = ""

    @abstractmethod
    def disponible(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def motivo_no_disponible(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def volcar(self, hoja_id: str, encabezados: list[str], filas: list[list]) -> str:
        """Escribe y devuelve la URL de la hoja."""
        raise NotImplementedError


class GoogleSheetsProvider(HojaCalculoProvider):
    """
    Escribe en una hoja de Google mediante una cuenta de servicio.

    La hoja debe estar compartida con el correo de esa cuenta CON PERMISO DE
    EDITOR: es lo único que hace falta configurar del lado del usuario, y por
    eso el sistema lo dice en la pantalla.
    """

    codigo = "gsheets"
    nombre = "Google Sheets"

    def _credenciales_json(self) -> str:
        return getattr(settings, "SIBU", {}).get("GOOGLE_CREDENCIALES_JSON", "")

    def disponible(self) -> bool:
        return bool(self._credenciales_json())

    def motivo_no_disponible(self) -> str:
        return (
            "No hay credenciales de Google configuradas (SIBU.GOOGLE_CREDENCIALES_JSON). "
            "Mientras tanto puede descargar el historial en CSV y subirlo a la hoja."
        )

    def volcar(self, hoja_id: str, encabezados: list[str], filas: list[list]) -> str:
        if not self.disponible():
            raise ValidationError(self.motivo_no_disponible())

        import json

        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        credenciales = Credentials.from_service_account_info(
            json.loads(self._credenciales_json()),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        servicio = build("sheets", "v4", credentials=credenciales, cache_discovery=False)
        hojas = servicio.spreadsheets()
        # Se limpia antes de escribir: sin esto, un volcado más corto que el
        # anterior dejaría filas viejas debajo y la hoja mezclaría dos cortes
        # distintos sin que se note.
        hojas.values().clear(spreadsheetId=hoja_id, range="A:Z").execute()
        hojas.values().update(
            spreadsheetId=hoja_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": [encabezados, *filas]},
        ).execute()
        return f"https://docs.google.com/spreadsheets/d/{hoja_id}/edit"


def get_proveedor() -> HojaCalculoProvider:
    """Punto único de obtención. Hoy solo hay uno; el patrón deja añadir otro."""
    return GoogleSheetsProvider()
