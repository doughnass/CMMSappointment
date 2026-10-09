from django.db import migrations, models


def copy_legacy_required_skills(apps, schema_editor):
    Equipment = apps.get_model('appointments', 'Equipment')
    for equip in Equipment.objects.all().prefetch_related('required_skills'):
        legacy_ids = list(equip.required_skills.values_list('id', flat=True))
        if not legacy_ids:
            continue
        equip.maintenance_required_skills.add(*legacy_ids)
        if equip.requires_calibration:
            equip.calibration_required_skills.add(*legacy_ids)


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0002_equipment_master_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipment',
            name='calibration_required_skills',
            field=models.ManyToManyField(blank=True, related_name='equipment_cal_required', to='appointments.skill', verbose_name='ทักษะที่ต้องการสำหรับสอบเทียบ'),
        ),
        migrations.AddField(
            model_name='equipment',
            name='maintenance_required_skills',
            field=models.ManyToManyField(blank=True, related_name='equipment_pm_required', to='appointments.skill', verbose_name='ทักษะที่ต้องการสำหรับ PM'),
        ),
        migrations.RunPython(copy_legacy_required_skills, migrations.RunPython.noop),
    ]
