from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0008_appointment_workflow_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='time_type',
            field=models.CharField(
                max_length=15,
                choices=[
                    ('office',        'ในเวลาราชการ (08:30–16:30)'),
                    ('overtime_wday', 'นอกเวลา จ.-ศ. (16:30–20:30)'),
                    ('overtime_wknd', 'เสาร์/อาทิตย์ (08:30–16:30)'),
                    ('overtime',      'นอกเวลา (เดิม)'),
                ],
                default='office',
                verbose_name='ช่วงเวลา',
            ),
        ),
        migrations.CreateModel(
            name='TechnicianOvertimeDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='วันที่')),
                ('technician', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='overtime_days',
                    to='appointments.technician',
                    verbose_name='ช่าง',
                )),
            ],
            options={
                'verbose_name': 'วันทำงานนอกเวลา',
                'verbose_name_plural': 'วันทำงานนอกเวลา',
                'ordering': ['date'],
                'unique_together': {('technician', 'date')},
            },
        ),
    ]
