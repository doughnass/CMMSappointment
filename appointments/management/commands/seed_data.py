"""
Management command: python manage.py seed_data
Creates sample skills, technicians, customers, equipment categories, and equipment.
"""
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from appointments.models import (
    Skill, Technician, TechnicianWorkDay, Customer,
    EquipmentCategory, Equipment,
)
from appointments.utils import add_months


class Command(BaseCommand):
    help = 'Seed sample data for testing'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding sample data…')

        # ── Skills ──
        skills_data = [
            'PM เครื่อง X-ray',
            'PM เครื่องอัลตราซาวด์',
            'PM เครื่อง ECG / EKG',
            'PM เครื่องหายใจ (Ventilator)',
            'PM เครื่องวัดความดัน / Vital Signs',
            'สอบเทียบเครื่องมือความดัน',
            'สอบเทียบ Thermometer / Temperature',
            'สอบเทียบเครื่องชั่ง',
            'ซ่อมแซมอุปกรณ์ไฟฟ้า',
            'ซ่อมแซมเครื่องมือแพทย์ทั่วไป',
        ]
        skills = {}
        for sn in skills_data:
            s, _ = Skill.objects.get_or_create(name=sn)
            skills[sn] = s
        self.stdout.write(f'  ✔ Skills: {len(skills)}')

        # ── Technicians ──
        techs_data = [
            {
                'employee_id': 'T001',
                'first_name': 'สมชาย',
                'last_name': 'รักงาน',
                'phone': '081-234-5678',
                'color': '#e74c3c',
                'work_days': [0, 1, 2, 3, 4],  # Mon-Fri
                'skills': ['PM เครื่อง X-ray', 'PM เครื่องอัลตราซาวด์',
                           'สอบเทียบเครื่องมือความดัน'],
            },
            {
                'employee_id': 'T002',
                'first_name': 'วิชัย',
                'last_name': 'ช่างดี',
                'phone': '089-876-5432',
                'color': '#3498db',
                'work_days': [0, 1, 2, 3, 4],
                'skills': ['PM เครื่อง ECG / EKG', 'PM เครื่องหายใจ (Ventilator)',
                           'ซ่อมแซมอุปกรณ์ไฟฟ้า'],
            },
            {
                'employee_id': 'T003',
                'first_name': 'ประภา',
                'last_name': 'มือทอง',
                'phone': '092-555-1234',
                'color': '#27ae60',
                'work_days': [0, 1, 2, 3, 4, 5],  # Mon-Sat
                'skills': ['PM เครื่องวัดความดัน / Vital Signs',
                           'สอบเทียบ Thermometer / Temperature',
                           'สอบเทียบเครื่องชั่ง'],
            },
        ]
        techs = {}
        for td in techs_data:
            tech, created = Technician.objects.get_or_create(
                employee_id=td['employee_id'],
                defaults={
                    'first_name': td['first_name'],
                    'last_name': td['last_name'],
                    'phone': td['phone'],
                    'color': td['color'],
                }
            )
            if created:
                for day in td['work_days']:
                    TechnicianWorkDay.objects.get_or_create(
                        technician=tech, day_of_week=day)
                for sn in td['skills']:
                    if sn in skills:
                        tech.skills.add(skills[sn])
            techs[td['employee_id']] = tech
        self.stdout.write(f'  ✔ Technicians: {len(techs)}')

        # ── Customers ──
        customers_data = [
            {'code': 'RH001', 'name': 'โรงพยาบาลศิริราช', 'phone': '02-419-7000',
             'contact_person': 'คุณมาลี วงศ์ดี'},
            {'code': 'RH002', 'name': 'โรงพยาบาลรามาธิบดี', 'phone': '02-201-1000',
             'contact_person': 'คุณสมศักดิ์ ใจดี'},
            {'code': 'RH003', 'name': 'โรงพยาบาลพระมงกุฎเกล้า', 'phone': '02-354-7600',
             'contact_person': 'คุณอรุณ แสงทอง'},
            {'code': 'RH004', 'name': 'โรงพยาบาลกรุงเทพ', 'phone': '02-310-3000',
             'contact_person': 'คุณสุดา นิลสาร'},
        ]
        customers = {}
        for cd in customers_data:
            c, _ = Customer.objects.get_or_create(code=cd['code'], defaults=cd)
            customers[cd['code']] = c
        self.stdout.write(f'  ✔ Customers: {len(customers)}')

        # ── Equipment Categories ──
        cats_data = [
            ('เครื่อง X-ray / Imaging', ['PM เครื่อง X-ray']),
            ('เครื่องอัลตราซาวด์', ['PM เครื่องอัลตราซาวด์']),
            ('เครื่อง ECG / Monitor', ['PM เครื่อง ECG / EKG']),
            ('เครื่องหายใจ / Ventilator', ['PM เครื่องหายใจ (Ventilator)']),
            ('เครื่องวัดสัญญาณชีพ', ['PM เครื่องวัดความดัน / Vital Signs']),
        ]
        cats = {}
        for name, skill_names in cats_data:
            cat, _ = EquipmentCategory.objects.get_or_create(name=name)
            for sn in skill_names:
                if sn in skills:
                    cat.required_skills.add(skills[sn])
            cats[name] = cat
        self.stdout.write(f'  ✔ Equipment Categories: {len(cats)}')

        # ── Equipment ──
        today = date.today()
        equipment_data = [
            {
                'serial_number': 'XR-2024-001',
                'name': 'เครื่อง X-ray ดิจิทัล Siemens',
                'model': 'MULTIX Impact',
                'manufacturer': 'Siemens Healthineers',
                'category': 'เครื่อง X-ray / Imaging',
                'customer': 'RH001',
                'department': 'แผนกรังสีวิทยา',
                'maintenance_duration_minutes': 180,
                'maintenance_interval_months': 6,
                'last_maintenance_date': today - timedelta(days=190),
                'requires_calibration': True,
                'calibration_duration_minutes': 120,
                'calibration_interval_months': 12,
                'last_calibration_date': today - timedelta(days=370),
            },
            {
                'serial_number': 'US-2023-015',
                'name': 'เครื่องอัลตราซาวด์ Philips',
                'model': 'EPIQ 7',
                'manufacturer': 'Philips Healthcare',
                'category': 'เครื่องอัลตราซาวด์',
                'customer': 'RH001',
                'department': 'แผนกอายุรกรรม',
                'maintenance_duration_minutes': 120,
                'maintenance_interval_months': 12,
                'last_maintenance_date': today - timedelta(days=200),
                'requires_calibration': False,
            },
            {
                'serial_number': 'ECG-2022-008',
                'name': 'เครื่อง ECG 12-Lead GE',
                'model': 'MAC 5500 HD',
                'manufacturer': 'GE Healthcare',
                'category': 'เครื่อง ECG / Monitor',
                'customer': 'RH002',
                'department': 'แผนกหัวใจ',
                'maintenance_duration_minutes': 90,
                'maintenance_interval_months': 12,
                'last_maintenance_date': today - timedelta(days=380),
                'requires_calibration': True,
                'calibration_duration_minutes': 60,
                'calibration_interval_months': 12,
                'last_calibration_date': today - timedelta(days=395),
            },
            {
                'serial_number': 'VENT-2023-003',
                'name': 'เครื่องช่วยหายใจ Draeger',
                'model': 'Evita V500',
                'manufacturer': 'Draeger',
                'category': 'เครื่องหายใจ / Ventilator',
                'customer': 'RH002',
                'department': 'ICU',
                'maintenance_duration_minutes': 240,
                'maintenance_interval_months': 6,
                'last_maintenance_date': today - timedelta(days=185),
                'requires_calibration': True,
                'calibration_duration_minutes': 90,
                'calibration_interval_months': 6,
                'last_calibration_date': today - timedelta(days=190),
            },
            {
                'serial_number': 'VS-2024-021',
                'name': 'เครื่องวัดสัญญาณชีพ Nihon Kohden',
                'model': 'BSM-2354',
                'manufacturer': 'Nihon Kohden',
                'category': 'เครื่องวัดสัญญาณชีพ',
                'customer': 'RH003',
                'department': 'ห้องผ่าตัด',
                'maintenance_duration_minutes': 60,
                'maintenance_interval_months': 12,
                'last_maintenance_date': today - timedelta(days=25),
                'requires_calibration': True,
                'calibration_duration_minutes': 45,
                'calibration_interval_months': 12,
                'last_calibration_date': today - timedelta(days=30),
            },
            {
                'serial_number': 'VS-2024-022',
                'name': 'เครื่องวัดสัญญาณชีพ Mindray',
                'model': 'MEC-2000',
                'manufacturer': 'Mindray',
                'category': 'เครื่องวัดสัญญาณชีพ',
                'customer': 'RH004',
                'department': 'แผนกฉุกเฉิน',
                'maintenance_duration_minutes': 60,
                'maintenance_interval_months': 12,
                'last_maintenance_date': today - timedelta(days=340),
                'requires_calibration': False,
            },
        ]

        for ed in equipment_data:
            cat_name = ed.pop('category')
            cust_code = ed.pop('customer')
            cal_dur = ed.pop('calibration_duration_minutes', None)
            cal_int = ed.pop('calibration_interval_months', None)
            cal_last = ed.pop('last_calibration_date', None)
            requires_cal = ed.pop('requires_calibration', False)

            eq, created = Equipment.objects.get_or_create(
                serial_number=ed['serial_number'],
                defaults={
                    **ed,
                    'category': cats.get(cat_name),
                    'customer': customers[cust_code],
                    'requires_calibration': requires_cal,
                    'calibration_duration_minutes': cal_dur,
                    'calibration_interval_months': cal_int,
                    'last_calibration_date': cal_last,
                }
            )
            if created:
                # Trigger save to auto-calculate next dates
                eq.save()

        self.stdout.write(f'  ✔ Equipment: {len(equipment_data)}')

        # ── Admin user ──
        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin1234')
            self.stdout.write('  ✔ Superuser created: admin / admin1234')
        else:
            self.stdout.write('  ⚠ Superuser already exists')

        self.stdout.write(self.style.SUCCESS('\n✅ Sample data seeded successfully!'))
        self.stdout.write('   → Run: python manage.py runserver')
        self.stdout.write('   → Open: http://127.0.0.1:8000/')
        self.stdout.write('   → Admin: http://127.0.0.1:8000/admin/  (admin / admin1234)')
