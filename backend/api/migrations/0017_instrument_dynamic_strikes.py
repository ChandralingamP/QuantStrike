from django.db import migrations, models


def initialise_strike_selection(apps, schema_editor):
    Instrument = apps.get_model("api", "Instrument")
    defaults = {
        "NIFTY": ("atm", 50),
        "BANKNIFTY": ("atm", 100),
        "SENSEX": ("atm", 100),
    }
    for instrument_code, (mode, step) in defaults.items():
        Instrument.objects.filter(instrument=instrument_code).update(
            strike_selection=mode,
            strike_step=step,
            ce_strike_offset=0,
            pe_strike_offset=0,
        )


def reset_strike_selection(apps, schema_editor):
    Instrument = apps.get_model("api", "Instrument")
    Instrument.objects.update(
        strike_selection="static",
        strike_step=50,
        ce_strike_offset=0,
        pe_strike_offset=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0016_instrument_alternate_symbol_token_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="instrument",
            name="strike_selection",
            field=models.CharField(
                choices=[("static", "Static"), ("atm", "ATM (dynamic)")],
                default="static",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="instrument",
            name="strike_step",
            field=models.PositiveIntegerField(default=50),
        ),
        migrations.AddField(
            model_name="instrument",
            name="ce_strike_offset",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="instrument",
            name="pe_strike_offset",
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(initialise_strike_selection, reset_strike_selection),
    ]
