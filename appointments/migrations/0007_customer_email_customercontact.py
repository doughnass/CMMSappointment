import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0006_remove_skill_parent_customer_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='อีเมล'),
        ),
        migrations.CreateModel(
            name='CustomerContact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='ชื่อผู้ติดต่อ')),
                ('role', models.CharField(blank=True, max_length=100, verbose_name='ตำแหน่ง')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='โทรศัพท์')),
                ('email', models.EmailField(blank=True, verbose_name='อีเมล')),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contacts',
                    to='appointments.customer',
                    verbose_name='ลูกค้า',
                )),
            ],
            options={
                'verbose_name': 'ผู้ติดต่อ',
                'verbose_name_plural': 'ผู้ติดต่อลูกค้า',
                'ordering': ['name'],
            },
        ),
    ]
