"""Utilidades para pruebas: generación de cédulas ecuatorianas válidas."""


def generar_cedula(provincia: int = 11, secuencia: int = 234567) -> str:
    """Construye una cédula de 10 dígitos con verificador correcto (módulo 10)."""
    base = f"{provincia:02d}{secuencia:07d}"[:9]
    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for coef, d in zip(coeficientes, base, strict=False):
        p = coef * int(d)
        total += p - 9 if p > 9 else p
    verificador = (10 - (total % 10)) % 10
    return base + str(verificador)
