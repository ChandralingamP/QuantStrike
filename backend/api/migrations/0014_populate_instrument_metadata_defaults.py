from django.db import migrations


def apply_defaults(apps, schema_editor):
    Instrument = apps.get_model("api", "Instrument")

    metadata = {
        "NIFTY": {"exchange": "NFO", "lot_size": 50},
        "BANKNIFTY": {"exchange": "NFO", "lot_size": 15},
        "SENSEX": {"exchange": "BFO", "lot_size": 10},
    }

    for code, fields in metadata.items():
        Instrument.objects.filter(instrument=code, lot_size__in=(0, None)).update(
            exchange=fields["exchange"],
            lot_size=fields["lot_size"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_instrument_live_fields"),
    ]

    operations = [
        migrations.RunPython(apply_defaults, migrations.RunPython.noop),
    ]
