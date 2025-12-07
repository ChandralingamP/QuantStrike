from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_rename_api_email__0a02fd_idx_api_emailot_email_c73515_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="emailotp",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("signup", "Signup"),
                    ("password_reset", "Password Reset"),
                ],
                default="signup",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="emailotp",
            index=models.Index(
                fields=["email", "purpose", "is_used"],
                name="api_emailot_email_purpose_is_used_idx",
            ),
        ),
    ]
