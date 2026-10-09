from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipment',
            name='equipment_code',
            field=models.CharField(blank=True, max_length=50, verbose_name='รหัสเครื่อง'),
        ),
        migrations.AddField(
            model_name='equipment',
            name='name_th',
            field=models.CharField(blank=True, max_length=200, verbose_name='ชื่อเครื่องภาษาไทย'),
        ),
        migrations.AddField(
            model_name='equipment',
            name='owner_unit_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='ชื่อหน่วยงานเจ้าของเครื่อง'),
        ),
        migrations.AddField(
            model_name='equipment',
            name='user_unit_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='ชื่อหน่วยงานที่ใช้เครื่อง'),
        ),
        migrations.AlterField(
            model_name='equipment',
            name='asset_number',
            field=models.CharField(blank=True, max_length=50, verbose_name='เลขครุภัณฑ์'),
        ),
        migrations.AlterField(
            model_name='equipment',
            name='department',
            field=models.CharField(blank=True, max_length=200, verbose_name='ภาควิชา/ฝ่าย/งาน'),
        ),
        migrations.AlterField(
            model_name='equipment',
            name='manufacturer',
            field=models.CharField(blank=True, max_length=100, verbose_name='ยี่ห้อ'),
        ),
        migrations.AlterField(
            model_name='equipment',
            name='name',
            field=models.CharField(max_length=200, verbose_name='ชื่อเครื่อง'),
        ),
        migrations.AlterField(
            model_name='equipment',
            name='serial_number',
            field=models.CharField(max_length=100, unique=True, verbose_name='SerialNo'),
        ),
    ]
