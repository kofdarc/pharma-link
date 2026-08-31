from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('eprescriptions', '0005_prescription_sms_sent_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescription',
            name='whatsapp_sent_at',
            field=models.DateTimeField(blank=True, help_text="Set when the prescription was sent to the patient's phone over WhatsApp at issue time.", null=True),
        ),
    ]
