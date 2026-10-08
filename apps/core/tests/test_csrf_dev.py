"""
Los orígenes que CSRF acepta en desarrollo.

El síntoma que motivó esto, tal cual salió en Codespaces:

    Forbidden (Origin checking failed - https://localhost:8000 does not match
    any trusted origins.): /cuentas/login/

La página cargaba, el formulario se veía, y al enviarlo respondía 403 «La
verificación CSRF ha fallado». Dos defectos encadenados: el reenvío de puertos
de Codespaces presenta `https://localhost:8000` como Origin aunque el navegador
muestre el dominio *.app.github.dev, y `dev.py` ignoraba la variable
`CSRF_TRUSTED_ORIGINS` que `scripts/dev.sh` calculaba —esa derivación era
código muerto—.

Se importa `origenes_dev`, no `dev`: importar el módulo de ajustes de
desarrollo altera los ajustes del resto de la suite (ver `test_arranque.py`).
"""

from config.settings.origenes_dev import origenes_confiables

CODESPACE = {
    "CODESPACE_NAME": "sturdy-palm-tree-v6vxr79q67q6cxg76",
    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
}


def test_acepta_el_origen_que_presenta_el_reenvio_de_puertos():
    """El caso exacto del error: Codespaces mandando Origin de localhost."""
    assert "https://localhost:8000" in origenes_confiables(CODESPACE)


def test_acepta_el_dominio_que_codespaces_asigna_al_puerto():
    assert "https://sturdy-palm-tree-v6vxr79q67q6cxg76-8000.app.github.dev" in origenes_confiables(
        CODESPACE
    )


def test_respeta_lo_declarado_en_el_entorno():
    """
    `scripts/dev.sh` calcula esta variable. Antes `dev.py` la ignoraba y fijaba
    la lista a mano, así que el trabajo del script no llegaba a ninguna parte.
    """
    origenes = origenes_confiables({"CSRF_TRUSTED_ORIGINS": "https://sibu.unl.edu.ec"})
    assert origenes[0] == "https://sibu.unl.edu.ec"


def test_lo_declarado_no_se_repite_aunque_coincida():
    origenes = origenes_confiables({"CSRF_TRUSTED_ORIGINS": "https://localhost:8000"})
    assert origenes.count("https://localhost:8000") == 1


def test_sin_codespaces_sigue_habiendo_con_que_trabajar_en_local():
    origenes = origenes_confiables({})
    assert "http://localhost:8000" in origenes
    assert "http://127.0.0.1:8000" in origenes


def test_en_otro_puerto_nombra_ese_puerto():
    """
    Django no admite comodín de puerto —el `*` solo vale en la etiqueta
    izquierda del host—, así que el puerto hay que nombrarlo.
    """
    origenes = origenes_confiables({}, puerto="8080")
    assert "https://localhost:8080" in origenes
    assert "https://localhost:8000" not in origenes
