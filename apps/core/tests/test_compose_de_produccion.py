"""
El compose de producción y su plantilla de entorno tienen que decir lo mismo.

Dos trampas concretas, las dos silenciosas hasta el día del despliegue:

1. `env_file:` alimenta al CONTENEDOR, pero los `${...}` del propio fichero los
   resuelve el compose y para eso solo mira el shell y un `.env` del
   directorio. Sin `--env-file .env.prod`, la contraseña de la base está
   escrita y el arranque aborta igual diciendo que no está definida.
2. Una variable que el compose exige y la plantilla no nombra es una que el
   operador no sabe que tiene que rellenar.
"""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[3]
COMPOSE = RAIZ / "docker-compose.prod.yml"
PLANTILLA = RAIZ / ".env.prod.example"

# ${NOMBRE}, ${NOMBRE:-valor}, ${NOMBRE:?mensaje}
VARIABLE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(:[-?][^}]*)?\}")


def _exigidas():
    """Las que no traen valor por omisión: si faltan, no arranca."""
    return {
        nombre
        for nombre, defecto in VARIABLE.findall(COMPOSE.read_text())
        if not (defecto or "").startswith(":-")
    }


def test_toda_variable_exigida_por_el_compose_esta_en_la_plantilla():
    declaradas = {
        linea.split("=", 1)[0].strip()
        for linea in PLANTILLA.read_text().splitlines()
        if "=" in linea and not linea.lstrip().startswith("#")
    }

    ausentes = _exigidas() - declaradas
    assert not ausentes, (
        f"El compose exige {sorted(ausentes)} y .env.prod.example no las nombra: "
        "quien despliegue no sabrá que tiene que rellenarlas."
    )


def _ordenes_de_compose(texto):
    return [
        linea
        for linea in texto.splitlines()
        if "docker compose" in linea and "docker-compose.prod.yml" in linea
    ]


def test_toda_orden_documentada_pasa_el_env_file():
    """
    Sin `--env-file .env.prod` el compose no ve las variables aunque estén
    escritas. Es el fallo que hace perder la tarde con la contraseña delante.
    """
    fuentes = [
        COMPOSE,
        RAIZ / "docs" / "ORACLE_CLOUD.md",
        RAIZ / "docs" / "CONEXION_ENTRE_PORTABLES.md",
        PLANTILLA,
        RAIZ / "CLAUDE.md",
    ]
    sin_env_file = [
        (fuente.name, orden.strip())
        for fuente in fuentes
        if fuente.exists()
        for orden in _ordenes_de_compose(fuente.read_text())
        if "--env-file" not in orden
    ]

    assert not sin_env_file, f"Órdenes que abortarían al ejecutarse: {sin_env_file}"
