from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0017_instrument_dynamic_strikes"),
    ]

    operations = [
        migrations.AddField(
            model_name="instrument",
            name="daily_ce_symbol",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_ce_token",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_pe_symbol",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_pe_token",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_selection_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_underlying_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
    ]
