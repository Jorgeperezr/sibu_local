"""
Libros de Excel con la línea gráfica de la Universidad Nacional de Loja.

Vive en `core` y no en `reportes` porque la exportación está en todos los
servicios: una sola implementación evita que cada uno acabe con su propio verde
y su propio encabezado, que es como una identidad visual deja de serlo.

Los colores salen del manual y son los mismos que usa la interfaz
(`static/css/sibu.css`): el verde conduce y el rojo queda para la marca.
"""

from __future__ import annotations

from datetime import date

# Los mismos de `sibu.css`, sin el «#»: openpyxl los quiere en ARGB o RGB.
VERDE_UNL = "4F8E3A"
VERDE_OSCURO = "3C6D2C"
ROJO_UNL = "BF0811"
GRIS_SUAVE = "F2F4F1"
NEGRO_UNL = "211915"

UNIVERSIDAD = "Universidad Nacional de Loja"
UNIDAD = "Unidad de Bienestar Universitario"


def libro_institucional(
    *,
    titulo: str,
    encabezados: list[str],
    filas: list[list],
    subtitulo: str = "",
    nota_pie: str = "",
    nombre_hoja: str = "Datos",
):
    """
    Un `Workbook` con encabezado institucional, cabecera verde y datos.

    Devuelve el libro sin guardar: quien llama decide si va a una respuesta
    HTTP o a disco.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    hoja.title = nombre_hoja[:31]  # Excel corta los nombres de hoja en 31

    ancho = max(len(encabezados), 1)
    ultima_columna = get_column_letter(ancho)

    # --- Encabezado institucional -----------------------------------------
    def _titular(fila, texto, tamano, color, negrita=True):
        hoja.merge_cells(f"A{fila}:{ultima_columna}{fila}")
        celda = hoja.cell(row=fila, column=1, value=texto)
        celda.font = Font(name="Calibri", size=tamano, bold=negrita, color=color)
        celda.alignment = Alignment(horizontal="left", vertical="center")
        return celda

    _titular(1, UNIVERSIDAD, 14, VERDE_OSCURO)
    _titular(2, UNIDAD, 11, NEGRO_UNL, negrita=False)
    _titular(3, titulo, 12, ROJO_UNL)
    if subtitulo:
        _titular(4, subtitulo, 9, "6C757D", negrita=False)
    hoja.row_dimensions[1].height = 20
    hoja.row_dimensions[3].height = 18

    fila_cabecera = 6 if subtitulo else 5

    # --- Cabecera de la tabla ---------------------------------------------
    relleno = PatternFill("solid", start_color=VERDE_UNL, end_color=VERDE_UNL)
    borde = Border(bottom=Side(style="thin", color=VERDE_OSCURO))
    for columna, nombre in enumerate(encabezados, start=1):
        celda = hoja.cell(row=fila_cabecera, column=columna, value=nombre)
        celda.fill = relleno
        celda.font = Font(bold=True, color="FFFFFF")
        celda.alignment = Alignment(horizontal="left", vertical="center")
        celda.border = borde
    hoja.row_dimensions[fila_cabecera].height = 18

    # --- Datos -------------------------------------------------------------
    franja = PatternFill("solid", start_color=GRIS_SUAVE, end_color=GRIS_SUAVE)
    for indice, valores in enumerate(filas):
        fila = fila_cabecera + 1 + indice
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=columna, value=valor)
            # Franjas alternas: sobre cien filas, seguir una a lo ancho sin
            # ellas es donde se cometen los errores de lectura.
            if indice % 2:
                celda.fill = franja

    # --- Acabado -----------------------------------------------------------
    # Congelar bajo la cabecera y filtrar: con cien atenciones, una tabla sin
    # esto obliga a bajar y perder de vista de qué columna es cada dato.
    hoja.freeze_panes = hoja.cell(row=fila_cabecera + 1, column=1)
    if filas:
        hoja.auto_filter.ref = f"A{fila_cabecera}:{ultima_columna}{fila_cabecera + len(filas)}"
    _ajustar_anchos(hoja, encabezados, filas)

    if nota_pie:
        fila_nota = fila_cabecera + len(filas) + 2
        hoja.merge_cells(f"A{fila_nota}:{ultima_columna}{fila_nota}")
        celda = hoja.cell(row=fila_nota, column=1, value=nota_pie)
        celda.font = Font(size=8, italic=True, color="6C757D")
        celda.alignment = Alignment(wrap_text=True, vertical="top")

    return libro


def _ajustar_anchos(hoja, encabezados, filas) -> None:
    """
    Ancho por el contenido más largo de cada columna, con tope.

    Sin tope, un nombre largo estira la columna hasta que la tabla ya no cabe
    en una pantalla; sin ajuste, las fechas salen como «####».
    """
    from openpyxl.utils import get_column_letter

    for columna, nombre in enumerate(encabezados, start=1):
        largo = len(str(nombre))
        for valores in filas:
            if columna <= len(valores) and valores[columna - 1] is not None:
                largo = max(largo, len(str(valores[columna - 1])))
        hoja.column_dimensions[get_column_letter(columna)].width = min(largo + 3, 42)


def nombre_de_archivo(base: str, *, servicio: str = "") -> str:
    """`historial-atenciones-medicina-2026-09-06.xlsx`, sin espacios ni tildes."""
    partes = [base]
    if servicio:
        partes.append(servicio)
    partes.append(date.today().isoformat())
    return "-".join(partes) + ".xlsx"
