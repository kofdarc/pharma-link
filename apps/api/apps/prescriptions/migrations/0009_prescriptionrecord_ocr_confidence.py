from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prescriptions", "0008_alter_prescriptionrecord_ocr_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="prescriptionrecord",
            name="ocr_confidence",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="0-1 reliability of the structured read: mostly the share of medication rows that "
                "linked to a real catalog SKU. Null when no extraction ran. Below "
                "OCR_LOW_CONFIDENCE_THRESHOLD the patient sees a 'a pharmacist will check your photo' "
                "notice instead of the parsed medication list, and scalar fields are not auto-filled from it.",
            ),
        ),
    ]
