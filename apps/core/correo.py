"""
¿Este sistema envía correo de verdad?

Importa porque la respuesta cambia lo que el sistema puede AFIRMAR, no solo lo
que hace. Con el backend de archivo —el de la portable— `send_mail` **no
falla**: escribe el mensaje en una carpeta y devuelve 1. El servicio de
laboratorio lo tomaba por entregado y registraba «Informe enviado a
fulano@unl.edu.ec», estado ENVIADA, cuando el paciente no había recibido nada
y nadie iba a enterarse.

La regla del proyecto es la de siempre: el sistema informa, no decide, y sobre
todo no afirma lo que no sabe. Si no hay SMTP, hay que decir que los
resultados se entregan en ventanilla, que es exactamente lo que ya se dice
cuando la persona no tiene correo registrado.
"""

from django.conf import settings

# Backends que NO entregan el mensaje a nadie. Se nombran por lo que hacen:
# escribir en una carpeta, imprimir en la consola o tirarlo.
#
# `locmem` NO está en la lista, y la primera versión de esto lo incluía. Es el
# backend de las pruebas: guarda el mensaje en `mail.outbox`, que es
# precisamente el buzón que la prueba abre para comprobar que el aviso salió.
# Tratarlo como «no envía» apagaba el envío JUSTO en el entorno donde se
# comprueba, y seis pruebas que verificaban el correo de laboratorio y el
# código del portal pasaron a comprobar el camino contrario sin que el nombre
# de ninguna cambiara.
BACKENDS_QUE_NO_ENVIAN = (
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
)


def hay_correo_real() -> bool:
    """
    ¿Lo que se envíe va a llegar a un buzón?

    Con SMTP configurado, sí. Con el backend de archivo de la portable, o el
    de consola del desarrollo, no: el mensaje se escribe en algún sitio y ahí
    se queda.

    Un SMTP declarado sin servidor tampoco cuenta. `EMAIL_HOST` vacío con
    backend SMTP ya lo reporta `check --deploy` como sibu.E041; aquí se trata
    como lo que es: no hay correo.
    """
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if backend in BACKENDS_QUE_NO_ENVIAN:
        return False
    if backend.endswith("smtp.EmailBackend"):
        return bool(getattr(settings, "EMAIL_HOST", ""))
    # Un backend propio o de un tercero: se le concede que envía. No se puede
    # saber desde aquí, y suponer que no envía apagaría un correo que sí sale.
    return True
