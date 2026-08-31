from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eprescriptions', '0004_prescription_fax_sent_at_prescription_patient_fax'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='sms_sent_at',
            field=models.DateTimeField(blank=True, help_text="Set when the prescription was texted to the patient's phone at issue time.", null=True),
        ),
    ]
