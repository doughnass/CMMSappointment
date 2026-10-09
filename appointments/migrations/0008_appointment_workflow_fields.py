import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0007_customer_email_customercontact'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='equipment_received',
            field=models.BooleanField(default=False, verbose_name='รับเครื่องแล้ว'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='equipment_received_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='เวลารับเครื่อง'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='assigned_to',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_appointments',
                to='appointments.technician',
                verbose_name='ผู้รับงาน',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='actual_completion_date',
            field=models.DateField(blank=True, null=True, verbose_name='วันที่เสร็จจริง'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='completion_notes',
            field=models.TextField(blank=True, verbose_name='บันทึกผลงาน'),
        ),
    ]
