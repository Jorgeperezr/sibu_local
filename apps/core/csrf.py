"""
La pantalla que aparece cuando falla la comprobación CSRF, en desarrollo.

La de Django dice «Origin checking failed - https://localhost:8000 does not
match any trusted origins» y ahí termina: no dice qué orígenes SÍ acepta, ni
qué hacer. Ese mensaje costó dos rondas de ida y vuelta con un usuario que
tenía el arreglo delante pero corría otra rama.

Solo se instala con DEBUG=True. En producción sigue la pantalla de Django, que
no revela configuración a quien no debería verla.
"""

from django.http import HttpResponseForbidden
from django.template import engines


def vista_fallo_csrf(request, reason=""):
    """
    Explica el fallo con los datos concretos de esta petición.

    Recibe `reason` de Django. Se muestra el Origin que llegó y la lista que el
    servidor acepta, que es exactamente lo que hace falta para saber si sobra
    una entrada en la configuración o si se está sirviendo desde otro sitio.
    """
    from django.conf import settings

    origen = request.META.get("HTTP_ORIGIN", "")
    referer = request.META.get("HTTP_REFERER", "")
    confiables = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    falta_el_origen = bool(origen) and origen not in confiables

    # Se renderiza SIN pasar `request`, y no es un descuido: hacerlo dispara
    # los context processors, y `navegacion` lee `request.user`. En un fallo
    # CSRF la petición puede no haber pasado por AuthenticationMiddleware, así
    # que la pantalla que viene a explicar el error reventaba con
    # `'WSGIRequest' object has no attribute 'user'` y devolvía un 500 en su
    # lugar. Esta pantalla tiene que dibujarse justamente cuando el contexto
    # de sesión es parte del problema.
    plantilla = engines["django"].from_string(PLANTILLA)
    return HttpResponseForbidden(
        plantilla.render(
            {
                "motivo": reason,
                "origen": origen,
                "referer": referer,
                "confiables": confiables,
                "falta_el_origen": falta_el_origen,
                "ruta": request.path,
            }
        )
    )


# Plantilla en línea y sin extender `base.html` a propósito: esta pantalla debe
# poder dibujarse aunque el contexto de la sesión o la navegación sean parte
# del problema.
PLANTILLA = """
<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Verificación CSRF fallida · SIBU</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #f6f7f8; color: #1d1f21; }
  main { max-width: 46rem; margin: 3rem auto; background: #fff; border-radius: .5rem;
         padding: 2rem 2.25rem; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
  .sub { color: #6b7280; margin: 0 0 1.5rem; }
  code { background: #f1f3f5; padding: .1rem .35rem; border-radius: .2rem; font-size: .9em; }
  pre { background: #f1f3f5; padding: .75rem 1rem; border-radius: .3rem; overflow-x: auto; }
  .dato { display: grid; grid-template-columns: 9rem 1fr; gap: .4rem 1rem; margin-bottom: 1.5rem; }
  .dato dt { color: #6b7280; }
  /* `overflow-wrap` y no `word-break: break-all`: este último parte a mitad
     de palabra incluso cuando cabría entera, y el motivo es una frase que hay
     que poder leer. Se rompe solo lo que de verdad no cabe (una URL larga). */
  .dato dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
  ul { padding-left: 1.2rem; } li { margin-bottom: .4rem; }
  .aviso { background: #fff8e1; border-left: 3px solid #f0b429; padding: .75rem 1rem;
           margin-bottom: 1.5rem; }
</style></head><body><main>
  <h1>No se pudo enviar el formulario</h1>
  <p class="sub">La comprobación CSRF rechazó la petición a <code>{{ ruta }}</code>.</p>

  <dl class="dato">
    <dt>Origin recibido</dt><dd>{{ origen|default:"(ninguno)" }}</dd>
    <dt>Referer</dt><dd>{{ referer|default:"(ninguno)" }}</dd>
    <dt>Motivo</dt><dd>{{ motivo }}</dd>
  </dl>

  {% if falta_el_origen %}
  <div class="aviso">
    <strong>El origen <code>{{ origen }}</code> no está en la lista de confianza.</strong>
    Es el caso habitual en Codespaces: su reenvío de puertos presenta un Origin
    distinto del que muestra la barra del navegador.
  </div>
  {% endif %}

  <p><strong>Orígenes que este servidor acepta ahora mismo:</strong></p>
  <pre>{% for o in confiables %}{{ o }}
{% empty %}(la lista está vacía){% endfor %}</pre>

  <p><strong>Qué suele resolverlo, por orden:</strong></p>
  <ul>
    <li>Detener el servidor y arrancarlo con <code>make up</code>: deriva los
        orígenes de Codespaces solo. Arrancar con <code>make run</code> o con
        <code>runserver</code> a secas no lo hace.</li>
    <li>Comprobar que está en la rama que trae el arreglo:
        <code>git branch --show-current</code>. Un <code>git pull</code> en otra
        rama dice «Already up to date» y no trae nada.</li>
    <li>Si el Origin de arriba no aparece en la lista, añádalo:
        <code>export CSRF_TRUSTED_ORIGINS="…,{{ origen }}"</code> antes de
        <code>make up</code>.</li>
    <li>Recargar esta pantalla y volver a enviar: tras iniciar sesión en otra
        pestaña, el token rota y el de esta página queda viejo.</li>
  </ul>

  <p class="sub" style="margin-top:2rem">
    Esta pantalla solo aparece con <code>DEBUG=True</code>. En el servidor real
    se muestra el mensaje escueto de Django, que no revela la configuración.
  </p>
</main></body></html>
"""
