"""
El modo cliente: la portable abriendo el SIBU de la Unidad en vez de su propia
base.

Es el modo que la Unidad necesita de verdad. Repartir una copia de
`sibu.sqlite3` a cada profesional rompe el sello de Psicología de forma
irreparable: quien tenga el archivo lo abre con cualquier visor de SQLite y lee
el contenido clínico sin pasar por el RBAC. Una instancia central con las
portables como clientes lo mantiene.

Dos cosas que se vieron al ejercitarlo:

1. **La dirección se escribe como la escribe una persona.** `sibu.unl.edu.ec`,
   sin esquema. `webbrowser.open` con eso no abre el sistema: abre una búsqueda
   o un archivo local, y el profesional ve cualquier cosa menos SIBU.

2. **Cuando la red privada está caída, el navegador dice «no se puede
   conectar».** Eso no distingue entre la red, el servidor apagado y una
   dirección mal escrita. Y en modo cliente los datos no están en la carpeta,
   así que lo primero que hay que decirle a quien lo ve es que no ha perdido
   nada.
"""

import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "portable"))

import arrancar  # noqa: E402


@pytest.fixture
def archivo_servidor(tmp_path, monkeypatch):
    """Sustituye el `portable/servidor.txt` real por uno de prueba."""
    archivo = tmp_path / "servidor.txt"
    monkeypatch.setattr(arrancar, "ARCHIVO_SERVIDOR", archivo)
    return archivo


# ------------------------------------------------------- leer la dirección


def test_sin_archivo_la_portable_es_una_carpeta_sola(archivo_servidor):
    assert arrancar.servidor_central() is None


def test_una_direccion_sin_esquema_se_completa(archivo_servidor):
    """Lo que de verdad va a escribir alguien en ese archivo."""
    archivo_servidor.write_text("sibu.unl.edu.ec\n", encoding="utf-8")

    assert arrancar.servidor_central() == "http://sibu.unl.edu.ec"


def test_una_ip_con_puerto_tambien(archivo_servidor):
    """El caso de la red privada: no hay nombre, hay dirección."""
    archivo_servidor.write_text("10.0.0.5:8000", encoding="utf-8")

    assert arrancar.servidor_central() == "http://10.0.0.5:8000"


def test_el_esquema_escrito_se_respeta(archivo_servidor):
    archivo_servidor.write_text("https://sibu.unl.edu.ec/", encoding="utf-8")

    assert arrancar.servidor_central() == "https://sibu.unl.edu.ec"


def test_una_direccion_comentada_deja_la_portable_sola(archivo_servidor):
    """
    Para poder volver al modo de carpeta sola sin perder la dirección: si
    `#` no se respetara, la almohadilla viajaría dentro del nombre del equipo.
    """
    archivo_servidor.write_text("# https://sibu.unl.edu.ec\n", encoding="utf-8")

    assert arrancar.servidor_central() is None


def test_un_archivo_vacio_no_es_una_direccion(archivo_servidor):
    archivo_servidor.write_text("\n   \n", encoding="utf-8")

    assert arrancar.servidor_central() is None


# ------------------------------------------------- ¿contesta ese servidor?


def test_un_servidor_que_escucha_contesta():
    """Con un puerto real abierto, para no comprobar solo el camino del fallo."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        puerto = s.getsockname()[1]

        assert arrancar.responde(f"http://127.0.0.1:{puerto}") is True


def test_un_servidor_apagado_no_contesta():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]  # reservado y SIN escuchar

    assert arrancar.responde(f"http://127.0.0.1:{puerto}", segundos=1) is False


def test_una_direccion_sin_equipo_no_revienta():
    """Un archivo con basura dentro no puede tumbar el arranque."""
    assert arrancar.responde("http://", segundos=1) is False


def test_el_puerto_se_deduce_del_esquema():
    """`https://algo` son 443 y `http://algo` 80: sin eso no hay a dónde llamar."""
    from urllib.parse import urlsplit

    assert (urlsplit("https://sibu.unl.edu.ec").port or 443) == 443
    assert (urlsplit("http://sibu.unl.edu.ec").port or 80) == 80


# ----------------------------------------------------- lo que ve la persona


def test_con_el_servidor_caido_se_avisa_y_se_nombra_la_red(archivo_servidor, capsys, monkeypatch):
    """
    Lo que convierte un «no funciona» en algo que se puede arreglar: decir que
    puede ser la red privada, que puede estar apagado, y que no ha perdido nada.
    """
    archivo_servidor.write_text("10.0.0.5:8000", encoding="utf-8")
    monkeypatch.setattr(arrancar, "responde", lambda *a, **k: False)
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--sin-navegador"])

    codigo = arrancar.main()
    salida = capsys.readouterr().out

    assert codigo == 1, "si el servidor no contesta, el arranque no fue bien"
    assert "no contesta" in salida
    assert "NetBird" in salida, "hay que nombrar la red que hay que conectar"
    assert "no hay nada que" in salida and "perder" in salida
    assert "10.0.0.5:8000" in salida, "hay que enseñar la dirección que se usó"


def test_con_el_servidor_en_pie_no_se_asusta_a_nadie(archivo_servidor, capsys, monkeypatch):
    archivo_servidor.write_text("10.0.0.5:8000", encoding="utf-8")
    monkeypatch.setattr(arrancar, "responde", lambda *a, **k: True)
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--sin-navegador"])

    codigo = arrancar.main()
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "AVISO" not in salida
    assert "los datos están en el servidor, no aquí" in salida


def test_el_modo_cliente_no_toca_la_base_local(archivo_servidor, monkeypatch):
    """
    Un cliente no migra ni prepara nada: si lo hiciera, cada portable dejaría
    una base vacía al lado de la que de verdad usa.
    """
    archivo_servidor.write_text("10.0.0.5:8000", encoding="utf-8")
    monkeypatch.setattr(arrancar, "responde", lambda *a, **k: True)
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--sin-navegador"])

    def no_deberia(*args, **kwargs):
        raise AssertionError("el modo cliente preparó una base local")

    monkeypatch.setattr(arrancar, "preparar_carpeta", no_deberia)
    monkeypatch.setattr(arrancar, "preparar_django", no_deberia)

    assert arrancar.main() == 0
