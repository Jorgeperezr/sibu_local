"""URLs raíz de SIBU."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.firma import api as firma_api

urlpatterns = [
    # FirmaEC exige que la acción se llame así (manual 11.4.2).
    path(
        "grabar_archivos_firmados",
        firma_api.grabar_archivos_firmados,
        name="firmaec-callback",
    ),
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="inicio.html"), name="inicio"),
    path("cuentas/", include("django.contrib.auth.urls")),  # login/logout/password
    # API v1
    path("auditoria/", include("apps.auditoria.urls")),
    path("notificaciones/", include("apps.notificaciones.urls")),
    path("api/v1/", include("api.v1.urls")),
    path("usuarios/", include("apps.usuarios.urls")),
    path("academico/", include("apps.academico.urls")),
    path("expediente/", include("apps.expediente.urls")),
    path("citas/", include("apps.citas.urls")),
    path("enfermeria/", include("apps.enfermeria.urls")),
    path("medicina/", include("apps.medicina.urls")),
    path("laboratorio/", include("apps.laboratorio.urls")),
    path("odontologia/", include("apps.odontologia.urls")),
    path("farmacia/", include("apps.farmacia.urls")),
    path("psicologia/", include("apps.psicologia.urls")),
    path("psicopedagogia/", include("apps.psicopedagogia.urls")),
    path("trabajo-social/", include("apps.trabajo_social.urls")),
    path("derivaciones/", include("apps.derivaciones.urls")),
    path("firma/", include("apps.firma.urls")),
    path("becas/", include("apps.becas.urls")),
    path("talleres/", include("apps.talleres.urls")),
    path("portal/", include("apps.portal.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
