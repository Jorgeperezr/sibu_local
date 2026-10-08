"""
Sprint 6: catálogo de procedimientos, odontograma con estados tipificados y
registro de procedimientos ejecutados.

OdontogramaDetalle se recrea porque incorpora `registrado_en` (auto_now_add) y
`estado_codigo` pasa a ser un campo con choices. No hay datos de producción en
esta fase, por lo que la recreación es segura.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("odontologia", "0001_initial"),
        ("expediente", "0001_initial"),
        ("usuarios", "0001_initial"),
    ]

    operations = [
        # 1. Catálogo editable de procedimientos
        migrations.CreateModel(
            name="CatalogoProcedimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=20, unique=True)),
                ("nombre", models.CharField(max_length=150)),
                ("requiere_pieza", models.BooleanField(
                    default=True,
                    help_text="Si es falso, aplica a boca completa (ej. profilaxis).")),
                ("estado_resultante", models.CharField(
                    blank=True,
                    choices=[("sano", "Sano"), ("cariado", "Cariado"),
                             ("obturado", "Obturado"), ("perdido", "Perdido por caries"),
                             ("extraido_otro", "Extraído por otra causa"),
                             ("corona", "Corona"), ("sellante", "Sellante"),
                             ("protesis", "Prótesis"), ("implante", "Implante"),
                             ("ausente", "Ausente (no erupcionado)")],
                    help_text="Estado en que queda la pieza tras el procedimiento (ej. obturado).",
                    max_length=20)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "procedimiento del catálogo",
                "verbose_name_plural": "catálogo de procedimientos",
                "ordering": ["nombre"],
            },
        ),
        # 2. Campos nuevos de la atención odontológica
        migrations.AddField(
            model_name="atencionodontologia",
            name="indicaciones",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="atencionodontologia",
            name="proxima_cita_sugerida",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="atencionodontologia",
            name="indices",
            field=models.JSONField(
                blank=True, default=dict,
                help_text="Calculados por services.calcular_indices: cpod, componentes, placa"),
        ),
        migrations.AlterField(
            model_name="atencionodontologia",
            name="examen_estomatognatico",
            field=models.JSONField(
                blank=True, default=dict,
                help_text="{region: hallazgos} — labios, lengua, paladar…"),
        ),
        # 3. Recrear OdontogramaDetalle (nuevo registrado_en + choices en estado)
        migrations.DeleteModel(name="OdontogramaDetalle"),
        migrations.CreateModel(
            name="OdontogramaDetalle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("pieza_fdi", models.CharField(help_text="Notación FDI de dos dígitos",
                                               max_length=2)),
                ("superficie", models.CharField(
                    blank=True, help_text="V, L, M, D, O (vacío = pieza completa)",
                    max_length=2)),
                ("estado_codigo", models.CharField(
                    choices=[("sano", "Sano"), ("cariado", "Cariado"),
                             ("obturado", "Obturado"), ("perdido", "Perdido por caries"),
                             ("extraido_otro", "Extraído por otra causa"),
                             ("corona", "Corona"), ("sellante", "Sellante"),
                             ("protesis", "Prótesis"), ("implante", "Implante"),
                             ("ausente", "Ausente (no erupcionado)")],
                    max_length=20)),
                ("tipo", models.CharField(
                    choices=[("inicial", "Inicial"), ("evolucion", "Evolución")],
                    default="inicial", max_length=10)),
                ("observacion", models.CharField(blank=True, max_length=255)),
                ("registrado_en", models.DateTimeField(auto_now_add=True)),
                ("atencion", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="odontograma", to="expediente.atencion")),
            ],
            options={
                "verbose_name": "detalle de odontograma",
                "verbose_name_plural": "detalles de odontograma",
                "ordering": ["pieza_fdi", "superficie"],
            },
        ),
        migrations.AddIndex(
            model_name="odontogramadetalle",
            index=models.Index(fields=["atencion", "pieza_fdi"],
                               name="odontologia_atenc_pieza_idx"),
        ),
        # 4. Procedimientos ejecutados
        migrations.CreateModel(
            name="Procedimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("eliminado_en", models.DateTimeField(blank=True, null=True)),
                ("pieza_fdi", models.CharField(blank=True, max_length=2)),
                ("superficie", models.CharField(blank=True, max_length=2)),
                ("observacion", models.CharField(blank=True, max_length=255)),
                ("atencion", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="procedimientos_odonto", to="expediente.atencion")),
                ("catalogo", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="ejecuciones", to="odontologia.catalogoprocedimiento")),
                ("ejecutado_por", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="procedimientos_odonto", to="usuarios.perfilprofesional")),
            ],
            options={
                "verbose_name": "procedimiento odontológico",
                "verbose_name_plural": "procedimientos odontológicos",
                "ordering": ["-creado_en"],
            },
        ),
    ]
