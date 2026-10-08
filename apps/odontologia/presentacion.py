"""
Cómo se pinta cada estado del odontograma.

Vive aquí y no en la plantilla porque la leyenda y las piezas tienen que salir
de la MISMA fuente. La leyenda estaba escrita a mano y enseñaba seis de los
diez estados: faltaban «Extraído por otra causa», «Prótesis», «Implante» y
«Ausente», que el sistema sí registra y el profesional no sabía que existían.

Dos decisiones sobre el color:

**No se usan los colores semánticos de Bootstrap.** El odontograma pintaba el
diente sano con `btn-success` y el obturado con `btn-primary`, y la línea
gráfica institucional tiñe `primary` con el verde de la UNL: los dos salían
verdes, con 1,14:1 de contraste entre sí —el mismo color a efectos prácticos—.
Un obturado leído como sano cambia el plan de tratamiento y el índice CPO-D que
se reporta. Un mapa clínico no puede heredar la paleta de una botonera.

**El color no decide solo.** Cada pieza lleva la inicial de su estado, como el
odontograma en papel. Alrededor del 8 % de los hombres no distingue el rojo del
verde, que son justamente los dos estados más frecuentes; y una impresión en
blanco y negro deja el color en nada.
"""

from __future__ import annotations

from .models import EstadoPieza

# estado -> (clase de color, inicial que se imprime en la pieza)
# Las clases se definen en `static/css/sibu.css`, sección «Odontograma».
ESTILOS = {
    EstadoPieza.SANO: ("odo-sano", ""),
    EstadoPieza.CARIADO: ("odo-cariado", "C"),
    EstadoPieza.OBTURADO: ("odo-obturado", "O"),
    EstadoPieza.PERDIDO: ("odo-perdido", "P"),
    EstadoPieza.EXTRAIDO_OTRO: ("odo-extraido", "E"),
    EstadoPieza.CORONA: ("odo-corona", "K"),
    EstadoPieza.SELLANTE: ("odo-sellante", "S"),
    EstadoPieza.PROTESIS: ("odo-protesis", "R"),
    EstadoPieza.IMPLANTE: ("odo-implante", "I"),
    EstadoPieza.AUSENTE: ("odo-ausente", "A"),
}

# La pieza sana no lleva inicial a propósito: es el estado por defecto y
# marcarlo todo recarga el mapa justo donde no hay nada que mirar.
SIN_REGISTRAR = ("odo-vacio", "")


def estilo(estado: str) -> tuple[str, str]:
    """(clase, inicial) de un estado; el de «sin registrar» si no se reconoce."""
    return ESTILOS.get(estado, SIN_REGISTRAR)


def leyenda() -> list[dict]:
    """
    Los diez estados con su color y su inicial, para pintar la leyenda.

    Se deriva de `EstadoPieza`, así que un estado nuevo aparece solo y no puede
    quedarse fuera como pasó con cuatro de los diez.
    """
    return [
        {
            "codigo": codigo,
            "etiqueta": etiqueta,
            "clase": ESTILOS[codigo][0],
            "inicial": ESTILOS[codigo][1],
        }
        for codigo, etiqueta in EstadoPieza.choices
    ]
