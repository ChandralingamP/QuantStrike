from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0018_instrument_daily_selection"),
    ]

    operations = [
        migrations.AddField(
            model_name="instrument",
            name="daily_ce_prev_high",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_ce_prev_low",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_pe_prev_high",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_pe_prev_low",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="instrument",
            name="daily_levels_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
