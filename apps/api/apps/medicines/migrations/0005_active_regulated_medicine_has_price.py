from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("medicines", "0004_medicine_drug_schedule"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="medicine",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | models.Q(price_regime="FREE")
                    | models.Q(regulated_price__isnull=False)
                ),
                name="active_regulated_medicine_has_price",
            ),
        ),
    ]
