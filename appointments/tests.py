import io
from datetime import date, time, timedelta
from unittest import mock

import openpyxl
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .forms import AppointmentForm, EquipmentForm
from .models import (
    Appointment, Customer, Equipment, Skill, Technician, TechnicianLeave,
    TechnicianOvertimeDay, TechnicianWorkDay,
)
from .views import _IMPORT_COLUMNS, _skill_by_name


def next_weekday(weekday, min_days_ahead=7):
    """First date at least `min_days_ahead` days from today that falls on `weekday` (Mon=0)."""
    d = date.today() + timedelta(days=min_days_ahead)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(code='C1', name='Hospital')
        cls.tech = Technician.objects.create(
            employee_id='T1', first_name='Som', last_name='Chai', phone='0')
        cls.other_tech = Technician.objects.create(
            employee_id='T2', first_name='Mali', last_name='Dee', phone='0')
        for t in (cls.tech, cls.other_tech):
            for dow in range(5):
                TechnicianWorkDay.objects.create(technician=t, day_of_week=dow)
        cls.equipment = Equipment.objects.create(
            serial_number='SN1', name='Monitor', model='M1', customer=cls.customer,
            maintenance_duration_minutes=60)
        cls.monday = next_weekday(0)
        cls.saturday = next_weekday(5)

    def make_appointment(self, start='09:00', end='11:00', day=None, tech=None, **kwargs):
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        return Appointment.objects.create(
            equipment=self.equipment, technician=tech or self.tech, service_type='PM',
            scheduled_date=day or self.monday, start_time=time(sh, sm), end_time=time(eh, em),
            duration_minutes=(eh * 60 + em) - (sh * 60 + sm), coordinator_name='x', **kwargs)

    def form(self, start='09:00', end='10:00', day=None, tech=None, instance=None, **overrides):
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        data = {
            'equipment': self.equipment.pk, 'technician': (tech or self.tech).pk,
            'service_type': 'PM', 'scheduled_date': (day or self.monday).isoformat(),
            'start_time': start, 'end_time': end,
            'duration_minutes': (eh * 60 + em) - (sh * 60 + sm),
            'status': 'scheduled', 'coordinator_name': 'x',
        }
        data.update(overrides)
        return AppointmentForm(data, instance=instance)

    def assertRejected(self, form, fragment):
        self.assertFalse(form.is_valid(), 'form should have been rejected')
        self.assertTrue(
            any(fragment in msg for msg in form.non_field_errors()),
            f'expected "{fragment}" in {list(form.non_field_errors())}')


class OverlapTests(BaseCase):
    def setUp(self):
        self.existing = self.make_appointment('09:00', '11:00')

    def test_overlapping_ranges_are_rejected(self):
        for start, end in [('09:00', '11:00'), ('10:00', '12:00'), ('08:30', '09:30'),
                           ('09:30', '10:00'), ('08:30', '12:00')]:
            with self.subTest(start=start, end=end):
                self.assertRejected(self.form(start, end), self.existing.appointment_no)

    def test_adjacent_ranges_are_allowed(self):
        self.assertTrue(self.form('11:00', '12:00').is_valid())
        self.assertTrue(self.form('08:30', '09:00').is_valid())

    def test_other_technician_is_allowed(self):
        self.assertTrue(self.form('09:00', '11:00', tech=self.other_tech).is_valid())

    def test_cancelled_appointment_does_not_block(self):
        self.existing.status = 'cancelled'
        self.existing.save()
        self.assertTrue(self.form('09:00', '11:00').is_valid())

    def test_completed_appointment_still_blocks(self):
        self.existing.status = 'completed'
        self.existing.save()
        self.assertRejected(self.form('09:00', '11:00'), self.existing.appointment_no)

    def test_editing_an_appointment_does_not_conflict_with_itself(self):
        self.assertTrue(self.form('09:00', '11:00', instance=self.existing).is_valid())


class ScheduleRuleTests(BaseCase):
    def test_valid_office_booking(self):
        self.assertTrue(self.form('09:00', '10:00').is_valid())

    def test_duration_must_match_time_range(self):
        self.assertRejected(self.form('09:00', '10:00', duration_minutes=600), 'ไม่ตรงกับ')

    def test_inactive_technician_or_equipment_rejected_for_new_booking(self):
        self.tech.is_active = False
        self.tech.save()
        self.assertRejected(self.form(), 'ปิดการใช้งาน')
        self.tech.is_active = True
        self.tech.save()
        self.equipment.is_active = False
        self.equipment.save()
        self.assertRejected(self.form(), 'ปิดการใช้งาน')

    def test_technician_on_leave_rejected(self):
        TechnicianLeave.objects.create(technician=self.tech, leave_date=self.monday)
        self.assertRejected(self.form(), 'ลา')

    def test_non_work_day_requires_overtime_registration(self):
        self.assertRejected(self.form('09:00', '10:00', day=self.saturday), 'ลงทะเบียน')
        TechnicianOvertimeDay.objects.create(technician=self.tech, date=self.saturday)
        self.assertTrue(self.form('09:00', '10:00', day=self.saturday).is_valid())

    def test_weekend_must_stay_inside_session_window(self):
        TechnicianOvertimeDay.objects.create(technician=self.tech, date=self.saturday)
        self.assertRejected(self.form('08:00', '09:00', day=self.saturday), 'นอกช่วง')
        self.assertRejected(self.form('16:00', '17:00', day=self.saturday), 'นอกช่วง')
        self.assertTrue(self.form('08:30', '16:30', day=self.saturday).is_valid())

    def test_weekday_after_hours_requires_registration_and_window(self):
        self.assertRejected(self.form('16:30', '17:30'), 'ลงทะเบียน')
        TechnicianOvertimeDay.objects.create(technician=self.tech, date=self.monday)
        self.assertTrue(self.form('16:30', '17:30').is_valid())
        self.assertRejected(self.form('20:00', '21:00'), 'นอกช่วง')

    def test_office_booking_cannot_run_past_office_hours_or_start_early(self):
        self.assertRejected(self.form('16:00', '17:00'), 'นอกช่วง')
        self.assertRejected(self.form('07:00', '08:00'), 'นอกช่วง')

    def test_cancelled_status_skips_scheduling_rules(self):
        TechnicianLeave.objects.create(technician=self.tech, leave_date=self.monday)
        self.assertTrue(self.form(status='cancelled').is_valid())

    def test_editing_notes_of_old_appointment_is_not_blocked(self):
        apt = self.make_appointment('09:00', '11:00')
        TechnicianLeave.objects.create(technician=self.tech, leave_date=self.monday)
        self.tech.is_active = False
        self.tech.save()
        apt.refresh_from_db()
        apt.notes = 'only a note changed'
        apt.full_clean()  # must not raise


class WorkflowTests(BaseCase):
    def post(self, name, apt, **data):
        return self.client.post(reverse(f'appointments:{name}', args=[apt.pk]), data, follow=True)

    def test_receive_and_assign_are_rejected_for_closed_appointments(self):
        for status in ('completed', 'cancelled'):
            with self.subTest(status=status):
                apt = self.make_appointment('09:00', '10:00', day=self.monday + timedelta(days=7 * len(status)),
                                            status=status)
                self.post('appointment_receive', apt)
                self.post('appointment_assign', apt, assigned_to=self.tech.pk)
                apt.refresh_from_db()
                self.assertEqual(apt.status, status)
                self.assertFalse(apt.equipment_received)
                self.assertIsNone(apt.assigned_to)

    def test_assign_validates_technician(self):
        apt = self.make_appointment()
        for bad in ('abc', '99999', ''):
            with self.subTest(value=bad):
                response = self.post('appointment_assign', apt, assigned_to=bad)
                self.assertEqual(response.status_code, 200)
        self.other_tech.is_active = False
        self.other_tech.save()
        self.post('appointment_assign', apt, assigned_to=self.other_tech.pk)
        apt.refresh_from_db()
        self.assertIsNone(apt.assigned_to)
        self.assertEqual(apt.status, 'scheduled')

    def test_refusal_messages_use_bootstrap_danger_style(self):
        apt = self.make_appointment(status='completed')
        response = self.post('appointment_receive', apt)
        self.assertContains(response, 'alert-danger')
        self.assertNotContains(response, 'alert-error')

    def test_assign_moves_open_appointment_to_in_progress(self):
        apt = self.make_appointment()
        self.post('appointment_assign', apt, assigned_to=self.other_tech.pk)
        apt.refresh_from_db()
        self.assertEqual(apt.assigned_to, self.other_tech)
        self.assertEqual(apt.status, 'in_progress')

    def test_complete_updates_equipment_registry(self):
        apt = self.make_appointment()
        done = date.today()
        self.post('appointment_complete_action', apt, actual_completion_date=done.isoformat())
        apt.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(apt.status, 'completed')
        self.assertEqual(self.equipment.last_maintenance_date, done)
        self.assertIsNotNone(self.equipment.next_maintenance_date)

    def test_cannot_complete_cancelled_or_already_completed(self):
        cancelled = self.make_appointment(status='cancelled')
        self.post('appointment_complete_action', cancelled, actual_completion_date=date.today().isoformat())
        cancelled.refresh_from_db()
        self.equipment.refresh_from_db()
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertIsNone(self.equipment.last_maintenance_date)

        apt = self.make_appointment('13:00', '14:00')
        apt.mark_completed(date.today() - timedelta(days=3))
        with self.assertRaises(ValidationError):
            apt.mark_completed(date.today())
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.last_maintenance_date, date.today() - timedelta(days=3))


class RegressionTests(BaseCase):
    def test_equipment_form_renders_dates_in_html_date_format(self):
        self.equipment.last_maintenance_date = date(2025, 9, 2)
        self.equipment.save()
        html = str(EquipmentForm(instance=self.equipment)['last_maintenance_date'])
        self.assertIn('value="2025-09-02"', html)

    def test_skill_lookup_tolerates_duplicate_names(self):
        first = Skill.objects.create(name='Ventilator', skill_type='pm')
        second = Skill.objects.create(name='Ventilator', skill_type='cal')
        self.assertEqual(_skill_by_name('Ventilator'), first)
        self.assertEqual(_skill_by_name('Ventilator', prefer=[second]), second)
        self.assertIsNone(_skill_by_name('missing'))

    def test_skill_search_with_query(self):
        Skill.objects.create(name='Ventilator')
        response = self.client.get(reverse('appointments:api_skill_search'), {'q': 'Vent'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['name'] for r in response.json()['results']], ['Ventilator'])

    def test_pages_render_styles_and_scripts_without_static_file_serving(self):
        expected = {
            'dashboard': ['.sidebar-backdrop'],
            'schedule': ['#calendar-loading', 'FullCalendar.Calendar'],
            'dispatch_board': ['.dispatch-scroll'],
            'appointment_create': ['.tech-suggest-card', 'escapeHtml'],
        }
        for name, fragments in expected.items():
            with self.subTest(page=name):
                html = self.client.get(reverse(f'appointments:{name}')).content.decode()
                self.assertNotIn('/static/appointments/', html)
                self.assertIn('.sidebar-backdrop', html)
                for fragment in fragments:
                    self.assertIn(fragment, html)

    def test_inlined_assets_cannot_close_their_element(self):
        import os
        import tempfile
        from .templatetags.appointments_extras import _read_asset
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as handle:
            handle.write("var a = '</script><b>';\nvar b = '</STYLE'.length;")
            path = handle.name
        try:
            content = _read_asset(path, os.path.getmtime(path))
        finally:
            os.unlink(path)
        self.assertNotIn('</script', content)
        self.assertIn('<\\/script', content)

    def test_malformed_parameters_do_not_cause_server_errors(self):
        api = reverse('appointments:api_appointments')
        self.assertEqual(self.client.get(api, {'start': 'zzz'}).status_code, 400)
        self.assertEqual(self.client.get(api, {'technician': 'abc'}).status_code, 400)
        listing = reverse('appointments:appointment_list')
        for params in ({'customer': 'abc', 'technician': 'abc'}, {'date_from': 'bad', 'date_to': 'bad'}):
            self.assertEqual(self.client.get(listing, params).status_code, 200)

    def test_calendar_api_excludes_overtime_when_requested(self):
        TechnicianOvertimeDay.objects.create(technician=self.tech, date=self.saturday)
        self.make_appointment('09:00', '10:00')
        self.make_appointment('09:00', '10:00', day=self.saturday)
        api = reverse('appointments:api_appointments')
        everything = self.client.get(api, {'technician': 'all'}).json()
        office_only = self.client.get(api, {'technician': 'all', 'include_overtime': '0'}).json()
        self.assertEqual(len(everything), 2)
        self.assertEqual(len(office_only), 1)
        self.assertEqual(sorted(e['extendedProps']['is_overtime'] for e in everything), [False, True])


class ImportTests(BaseCase):
    LABELS = {field: label for field, label in _IMPORT_COLUMNS}

    def upload(self, rows, name='equipment.xlsx'):
        """rows: list of dicts keyed by import field name."""
        wb = openpyxl.Workbook()
        ws = wb.active
        fields = [field for field, _ in _IMPORT_COLUMNS]
        ws.append([self.LABELS[f] for f in fields])
        for row in rows:
            ws.append([row.get(f) for f in fields])
        buffer = io.BytesIO()
        wb.save(buffer)
        upload = SimpleUploadedFile(name, buffer.getvalue())
        return self.client.post(reverse('appointments:equipment_import'), {'excel_file': upload})

    def row(self, serial, **kwargs):
        return {'serial_number': serial, 'name': f'Name {serial}', 'customer_code': 'C1', **kwargs}

    def test_creates_new_equipment_with_model_defaults(self):
        response = self.upload([self.row('NEW1')])
        self.assertEqual((response.context['created'], response.context['skipped']), (1, 0))
        equipment = Equipment.objects.get(serial_number='NEW1')
        self.assertEqual(equipment.maintenance_duration_minutes, 120)
        self.assertTrue(equipment.is_active)

    def test_update_never_overwrites_existing_data_with_blank_cells(self):
        self.equipment.manufacturer = 'Zoll'
        self.equipment.last_maintenance_date = date(2025, 9, 2)
        self.equipment.requires_calibration = True
        self.equipment.save()
        response = self.upload([self.row('SN1', name='Renamed')])
        self.assertEqual(response.context['updated'], 1)
        self.equipment.refresh_from_db()
        self.assertEqual(self.equipment.name, 'Renamed')
        self.assertEqual(self.equipment.manufacturer, 'Zoll')
        self.assertEqual(self.equipment.last_maintenance_date, date(2025, 9, 2))
        self.assertTrue(self.equipment.requires_calibration)

    def test_non_positive_or_non_integer_numbers_are_rejected_per_row(self):
        rows = [
            self.row('BAD0', maintenance_duration_minutes=0),
            self.row('BAD1', maintenance_interval_months=-5),
            self.row('BAD2', calibration_duration_minutes='abc'),
            self.row('BAD3', maintenance_duration_minutes=12.5),
            self.row('GOOD', maintenance_duration_minutes=45),
        ]
        response = self.upload(rows)
        self.assertEqual((response.context['created'], response.context['skipped']), (1, 4))
        self.assertEqual(Equipment.objects.filter(serial_number__startswith='BAD').count(), 0)
        self.assertEqual(Equipment.objects.get(serial_number='GOOD').maintenance_duration_minutes, 45)

    def test_unknown_customer_row_is_skipped_and_reported(self):
        response = self.upload([self.row('X1', customer_code='NOPE'), self.row('X2')])
        self.assertEqual((response.context['created'], response.context['skipped']), (1, 1))
        self.assertIn('NOPE', str(response.context['row_errors']))

    def test_unexpected_failure_rolls_back_the_whole_import(self):
        original = Equipment.objects.create
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs['serial_number'])
            if len(calls) == 2:
                raise RuntimeError('boom')
            return original(**kwargs)

        with mock.patch.object(Equipment.objects, 'create', side_effect=flaky):
            response = self.upload([self.row('R1'), self.row('R2'), self.row('R3')])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Equipment.objects.filter(serial_number__in=['R1', 'R2', 'R3']).exists())

    def test_rejects_wrong_extension_and_oversized_files(self):
        before = Equipment.objects.count()
        self.upload([self.row('A1')], name='data.csv')
        with mock.patch('appointments.views.IMPORT_MAX_BYTES', 10):
            self.upload([self.row('A2')])
        with mock.patch('appointments.views.IMPORT_MAX_ROWS', 1):
            self.upload([self.row('A3'), self.row('A4')])
        self.assertEqual(Equipment.objects.count(), before)


class QueryScalingTests(BaseCase):
    """The number of queries must not grow with the number of technicians (N+1 regression)."""

    def add_technicians(self, count, prefix):
        skills = [Skill.objects.create(name=f'{prefix}{i}') for i in range(2)]
        for i in range(count):
            tech = Technician.objects.create(
                employee_id=f'{prefix}{i}', first_name='A', last_name='B', phone='0')
            tech.skills.set(skills)
            for dow in range(5):
                TechnicianWorkDay.objects.create(technician=tech, day_of_week=dow)
            TechnicianLeave.objects.create(technician=tech, leave_date=self.monday)
            TechnicianOvertimeDay.objects.create(technician=tech, date=self.monday)
            self.make_appointment('09:00', '10:00', day=self.monday, tech=tech)

    def urls(self):
        day = self.monday.isoformat()
        return [
            reverse('appointments:dashboard'),
            reverse('appointments:dispatch_board') + f'?date={day}',
            reverse('appointments:technician_list'),
            reverse('appointments:technician_skill'),
            reverse('appointments:api_technician_suggestions')
            + f'?equipment_id={self.equipment.pk}&date={day}&service_type=PM',
            reverse('appointments:api_calendar_availability')
            + f'?year={self.monday.year}&month={self.monday.month}&equipment_id={self.equipment.pk}',
        ]

    def counts(self):
        result = {}
        for url in self.urls():
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            result[url.split('?')[0]] = len(queries)
        return result

    def test_query_count_is_independent_of_technician_count(self):
        self.add_technicians(2, 'a')
        small = self.counts()
        self.add_technicians(10, 'b')
        large = self.counts()
        self.assertEqual(large, small)

    def test_availability_helpers_work_with_and_without_prefetch(self):
        tech = self.tech
        TechnicianLeave.objects.create(technician=tech, leave_date=self.monday)
        plain = Technician.objects.get(pk=tech.pk)
        from django.db.models import Prefetch
        prefetched = Technician.objects.prefetch_related(
            'work_days',
            Prefetch('leaves', queryset=TechnicianLeave.objects.filter(leave_date=self.monday)),
        ).get(pk=tech.pk)
        tuesday = self.monday + timedelta(days=1)
        for technician in (plain, prefetched):
            self.assertFalse(technician.is_available_on(self.monday))  # on leave
            self.assertTrue(technician.is_available_on(tuesday))
            self.assertFalse(technician.is_available_on(self.saturday))  # not a work day
