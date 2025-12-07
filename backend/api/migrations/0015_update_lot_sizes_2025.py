from django.db import migrations


def update_lot_sizes(apps, schema_editor):
    Instrument = apps.get_model("api", "Instrument")
    updates = {
        "NIFTY": 75,
        "BANKNIFTY": 35,
        "SENSEX": 20,
    }
    for code, lot_size in updates.items():
        Instrument.objects.filter(instrument=code).update(lot_size=lot_size)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0014_populate_instrument_metadata_defaults"),
    ]

    operations = [
        migrations.RunPython(update_lot_sizes, migrations.RunPython.noop),
    ]
