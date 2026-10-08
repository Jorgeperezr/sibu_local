"""
Sprint 5: catálogo de parámetros con valores de referencia y resultados
enlazados a ellos.

ResultadoParametro se recrea porque `parametro` deja de ser texto libre y pasa
a ser FK a ParametroExamen (permite validar rangos por sexo/edad). No hay datos
de producción en esta fase, por lo que la recreación es segura.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("laboratorio", "0002_initial"),
        ("usuarios", "0001_initial"),
    ]

    operations = [
        # 1. Nuevo catálogo de parámetros
        migrations.CreateModel(
            name="ParametroExamen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("unidad", models.CharField(blank=True, max_length=30)),
                ("tipo_valor", models.CharField(
                    choices=[("numerico", "Numérico"), ("cualitativo", "Cualitativo"),
                             ("texto", "Texto libre")],
                    default="numerico", max_length=12)),
                ("orden", models.PositiveSmallIntegerField(default=0)),
                ("sexo", models.CharField(
                    choices=[("ambos", "Ambos"), ("M", "Masculino"), ("F", "Femenino")],
                    default="ambos", max_length=6)),
                ("edad_min", models.PositiveSmallIntegerField(blank=True, help_text="Años",
                                                              null=True)),
                ("edad_max", models.PositiveSmallIntegerField(blank=True, help_text="Años",
                                                              null=True)),
                ("ref_min", models.DecimalField(blank=True, decimal_places=3,
                                                max_digits=10, null=True)),
                ("ref_max", models.DecimalField(blank=True, decimal_places=3,
                                                max_digits=10, null=True)),
                ("critico_min", models.DecimalField(blank=True, decimal_places=3,
                                                    max_digits=10, null=True)),
                ("critico_max", models.DecimalField(blank=True, decimal_places=3,
                                                    max_digits=10, null=True)),
                ("examen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name="parametros",
                                             to="laboratorio.examen")),
            ],
            options={
                "verbose_name": "parámetro de examen",
                "verbose_name_plural": "parámetros de exámenes",
                "ordering": ["examen", "orden", "nombre"],
            },
        ),
        # 2. Campos nuevos del catálogo de exámenes
        migrations.AddField(
            model_name="examen",
            name="indicaciones_preparacion",
            field=models.TextField(blank=True,
                                   help_text="Ayuno, suspensión de medicación, etc."),
        ),
        migrations.AlterModelOptions(
            name="examen",
            options={"ordering": ["perfil", "nombre"], "verbose_name": "examen",
                     "verbose_name_plural": "catálogo de exámenes"},
        ),
        # 3. Fase preanalítica y postanalítica en la orden
        migrations.AddField(
            model_name="ordenlaboratorio",
            name="tipo_muestra",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="ordenlaboratorio",
            name="codigo_barras",
            field=models.CharField(blank=True, db_index=True, max_length=40),
        ),
        migrations.AddField(
            model_name="ordenlaboratorio",
            name="validado_por",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="+", to="usuarios.perfilprofesional"),
        ),
        migrations.AddField(
            model_name="ordenlaboratorio",
            name="validado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ordenlaboratorio",
            name="publicado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="ordenlaboratorio",
            options={"ordering": ["-creado_en"], "verbose_name": "orden de laboratorio",
                     "verbose_name_plural": "órdenes de laboratorio"},
        ),
        migrations.AddIndex(
            model_name="ordenlaboratorio",
            index=models.Index(fields=["estado", "prioridad"],
                               name="laboratori_estado_a1b2c3_idx"),
        ),
        # 4. Restricción de unicidad en OrdenExamen
        migrations.AlterModelOptions(
            name="ordenexamen",
            options={"verbose_name": "examen de la orden",
                     "verbose_name_plural": "exámenes de la orden"},
        ),
        migrations.AddConstraint(
            model_name="ordenexamen",
            constraint=models.UniqueConstraint(fields=("orden", "examen"),
                                               name="uniq_orden_examen"),
        ),
        # 5. Recrear ResultadoParametro (parametro: CharField -> FK)
        migrations.DeleteModel(name="ResultadoParametro"),
        migrations.CreateModel(
            name="ResultadoParametro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("valor", models.CharField(max_length=60)),
                ("unidad", models.CharField(blank=True, max_length=30)),
                ("ref_min", models.CharField(blank=True, max_length=30)),
                ("ref_max", models.CharField(blank=True, max_length=30)),
                ("marcador", models.CharField(
                    choices=[("normal", "Normal"), ("alto", "Alto"), ("bajo", "Bajo"),
                             ("critico", "Crítico")],
                    default="normal", max_length=10)),
                ("observacion", models.CharField(blank=True, max_length=255)),
                ("registrado_en", models.DateTimeField(auto_now_add=True)),
                ("orden_examen", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="resultados", to="laboratorio.ordenexamen")),
                ("parametro", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="resultados", to="laboratorio.parametroexamen")),
                ("registrado_por", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="resultados_registrados",
                    to="usuarios.perfilprofesional")),
            ],
            options={
                "verbose_name": "resultado de parámetro",
                "verbose_name_plural": "resultados de parámetros",
                "ordering": ["parametro__orden"],
            },
        ),
        migrations.AddConstraint(
            model_name="resultadoparametro",
            constraint=models.UniqueConstraint(fields=("orden_examen", "parametro"),
                                               name="uniq_resultado_parametro"),
        ),
    ]
