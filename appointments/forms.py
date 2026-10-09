from django import forms
from django.core.exceptions import ValidationError
from datetime import date, datetime

from .models import (
    Appointment, Equipment, Technician, Customer, CustomerContact,
    EquipmentCategory, Skill, TechnicianWorkDay, TechnicianLeave,
    TechnicianOvertimeDay,
)


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            'equipment', 'technician', 'service_type',
            'scheduled_date', 'start_time', 'end_time', 'duration_minutes',
            'status', 'notes', 'coordinator_name',
        ]
        widgets = {
            'equipment': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_equipment'}),
            'technician': forms.Select(attrs={
                'class': 'form-select', 'id': 'id_technician'}),
            'service_type': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_date': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-control', 'type': 'text', 'id': 'id_scheduled_date',
                'autocomplete': 'off'}),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control', 'type': 'time', 'id': 'id_start_time'}),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control', 'type': 'time', 'id': 'id_end_time'}),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'id': 'id_duration_minutes'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'coordinator_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        scheduled_date = cleaned.get('scheduled_date')
        if scheduled_date and scheduled_date < date.today():
            self.add_error('scheduled_date', 'วันที่นัดต้องเป็นวันนี้หรือวันถัดไป ไม่สามารถเลือกวันที่ย้อนหลังได้')
        equipment = cleaned.get('equipment')
        technician = cleaned.get('technician')
        service_type = cleaned.get('service_type')
        if equipment and technician:
            required_skill_ids = equipment.required_skill_ids_for_service(service_type)
            technician_skill_ids = set(technician.skills.values_list('pk', flat=True))
            missing_skill_ids = required_skill_ids - technician_skill_ids
            if missing_skill_ids:
                self.add_error(
                    'technician',
                    'ช่างที่เลือกไม่มีทักษะที่จำเป็นสำหรับประเภทงานนี้ครบถ้วน',
                )
        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        if start and end and end <= start:
            raise ValidationError('เวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น')
        return cleaned


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            'equipment_code', 'name', 'name_th', 'manufacturer', 'model',
            'serial_number', 'asset_number',
            'customer', 'owner_unit_name', 'user_unit_name', 'department',
            'category',
            'maintenance_duration_minutes', 'maintenance_interval_months',
            'last_maintenance_date', 'next_maintenance_date',
            'maintenance_required_skills',
            'requires_calibration',
            'calibration_duration_minutes', 'calibration_interval_months',
            'last_calibration_date', 'next_calibration_date',
            'calibration_required_skills',
            'is_active',
        ]
        widgets = {
            'equipment_code': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'asset_number': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'name_th': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'owner_unit_name': forms.TextInput(attrs={'class': 'form-control'}),
            'user_unit_name': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'maintenance_duration_minutes': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}),
            'maintenance_interval_months': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}),
            'last_maintenance_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'next_maintenance_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'maintenance_required_skills': forms.CheckboxSelectMultiple(),
            'requires_calibration': forms.CheckboxInput(
                attrs={'class': 'form-check-input', 'id': 'id_requires_calibration',
                       'onchange': 'toggleCalibration(this)'}),
            'calibration_duration_minutes': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}),
            'calibration_interval_months': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 1}),
            'last_calibration_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'next_calibration_date': forms.DateInput(
                format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'calibration_required_skills': forms.CheckboxSelectMultiple(),
            'repair_required_skills': forms.CheckboxSelectMultiple(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('requires_calibration'):
            cleaned['calibration_required_skills'] = []
        return cleaned

    def save(self, commit=True):
        equipment = super().save(commit=commit)
        if commit:
            pm_skills = self.cleaned_data.get('maintenance_required_skills') or []
            cal_skills = self.cleaned_data.get('calibration_required_skills') or []
            repair_skills = self.cleaned_data.get('repair_required_skills') or []

            pm_ids = set(pm_skills.values_list('pk', flat=True)) if hasattr(pm_skills, 'values_list') else set()
            cal_ids = set(cal_skills.values_list('pk', flat=True)) if hasattr(cal_skills, 'values_list') else set()
            repair_ids = set(repair_skills.values_list('pk', flat=True)) if hasattr(repair_skills, 'values_list') else set()
            equipment.required_skills.set(pm_ids | cal_ids | repair_ids)
        return equipment


class TechnicianForm(forms.ModelForm):
    work_days = forms.MultipleChoiceField(
        choices=TechnicianWorkDay.WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='วันทำงานปกติ',
    )
    from .models import Skill
    pm_skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.filter(skill_type='pm'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='ทักษะ PM',
    )
    cal_skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.filter(skill_type='cal'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='ทักษะ Calibration',
    )
    repair_skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.filter(skill_type='repair'),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='ทักษะซ่อม',
    )

    class Meta:
        model = Technician
        fields = ['employee_id', 'first_name', 'last_name', 'phone',
                  'email', 'skills', 'color', 'is_active']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'skills': forms.CheckboxSelectMultiple(),
            'color': forms.TextInput(attrs={'class': 'form-control form-control-color',
                                            'type': 'color'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['work_days'].initial = list(
                self.instance.work_days.values_list('day_of_week', flat=True))
            # Initialize skill groups from existing technician.skills
            owned_ids = set(self.instance.skills.values_list('pk', flat=True))
            self.fields['pm_skills'].initial = [s.pk for s in self.fields['pm_skills'].queryset if s.pk in owned_ids]
            self.fields['cal_skills'].initial = [s.pk for s in self.fields['cal_skills'].queryset if s.pk in owned_ids]
            self.fields['repair_skills'].initial = [s.pk for s in self.fields['repair_skills'].queryset if s.pk in owned_ids]

    def save(self, commit=True):
        technician = super().save(commit=commit)
        if commit:
            work_days = [int(d) for d in self.cleaned_data.get('work_days', [])]
            technician.work_days.all().delete()
            for day in work_days:
                TechnicianWorkDay.objects.create(technician=technician, day_of_week=day)
            # Save skill groups: union all selected skills into technician.skills
            pm = set(self.cleaned_data.get('pm_skills') or [])
            cal = set(self.cleaned_data.get('cal_skills') or [])
            repair = set(self.cleaned_data.get('repair_skills') or [])
            all_skills = {s.pk for s in (pm | cal | repair)}
            technician.skills.set(all_skills)
        return technician


class TechnicianLeaveForm(forms.ModelForm):
    class Meta:
        model = TechnicianLeave
        fields = ['technician', 'leave_date', 'leave_type', 'reason']
        widgets = {
            'technician': forms.Select(attrs={'class': 'form-select'}),
            'leave_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['code', 'name', 'parent', 'email', 'address', 'phone', 'contact_person']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Customer.objects.all().order_by('code')
        if self.instance and self.instance.pk:
            # Exclude self and all descendants to prevent cycles
            excluded = {self.instance.pk}
            stack = list(self.instance.children.values_list('pk', flat=True))
            while stack:
                pk = stack.pop()
                excluded.add(pk)
                stack.extend(
                    Customer.objects.filter(parent_id=pk).values_list('pk', flat=True)
                )
            qs = qs.exclude(pk__in=excluded)
        self.fields['parent'].queryset = qs
        self.fields['parent'].empty_label = '— (องค์กรหลัก / ไม่มี parent)'


class CustomerContactForm(forms.ModelForm):
    class Meta:
        model = CustomerContact
        fields = ['name', 'role', 'phone', 'email']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ชื่อ-นามสกุล'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ตำแหน่ง / แผนก'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0x-xxxx-xxxx'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
        }


class TechnicianOvertimeDayForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
        label='วันที่นอกเวลา',
    )

    def clean_date(self):
        d = self.cleaned_data['date']
        from datetime import date as dt
        if d < dt.today():
            raise ValidationError('ไม่สามารถเพิ่มวันที่ผ่านมาแล้ว')
        return d
