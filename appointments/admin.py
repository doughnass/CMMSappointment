from django.contrib import admin
from .models import (
    Skill, Technician, TechnicianWorkDay, TechnicianLeave,
    Customer, EquipmentCategory, Equipment, Appointment
)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'skill_type', 'description']
    list_filter = ['skill_type']
    search_fields = ['name']


class TechnicianWorkDayInline(admin.TabularInline):
    model = TechnicianWorkDay
    extra = 0


class TechnicianLeaveInline(admin.TabularInline):
    model = TechnicianLeave
    extra = 0
    fields = ['leave_date', 'leave_type', 'reason']


@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'full_name', 'phone', 'is_active']
    list_filter = ['is_active', 'skills']
    search_fields = ['employee_id', 'first_name', 'last_name', 'phone']
    filter_horizontal = ['skills']
    inlines = [TechnicianWorkDayInline, TechnicianLeaveInline]

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'ชื่อ-นามสกุล'


@admin.register(TechnicianLeave)
class TechnicianLeaveAdmin(admin.ModelAdmin):
    list_display = ['technician', 'leave_date', 'leave_type', 'reason']
    list_filter = ['leave_type', 'technician']
    date_hierarchy = 'leave_date'


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'phone', 'contact_person']
    search_fields = ['code', 'name']


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    filter_horizontal = ['required_skills']


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = [
        'equipment_code', 'serial_number', 'name', 'name_th', 'customer', 'department',
        'next_maintenance_date', 'requires_calibration', 'next_calibration_date',
        'is_active'
    ]
    list_filter = ['is_active', 'requires_calibration', 'customer', 'category']
    search_fields = ['equipment_code', 'serial_number', 'asset_number', 'name', 'name_th',
                     'owner_unit_name', 'user_unit_name', 'customer__name']
    filter_horizontal = ['maintenance_required_skills', 'calibration_required_skills']
    filter_horizontal += ('repair_required_skills',)
    fieldsets = (
        ('ข้อมูลทั่วไป', {
            'fields': ('equipment_code', 'name', 'name_th', 'manufacturer', 'model',
                       'serial_number', 'asset_number', 'customer',
                       'owner_unit_name', 'user_unit_name', 'department',
                       'category', 'is_active')
        }),
        ('การบำรุงรักษา (PM)', {
            'fields': ('maintenance_duration_minutes', 'maintenance_interval_months',
                       'last_maintenance_date', 'next_maintenance_date')
        }),
        ('การสอบเทียบ (Calibration)', {
            'fields': ('requires_calibration', 'calibration_duration_minutes',
                       'calibration_interval_months', 'last_calibration_date',
                       'next_calibration_date'),
            'classes': ('collapse',),
        }),
        ('ทักษะที่ต้องการ (อ้างอิงงาน PM/CAL)', {
            'fields': ('maintenance_required_skills', 'calibration_required_skills', 'repair_required_skills'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = [
        'appointment_no', 'scheduled_date', 'start_time', 'end_time',
        'technician', 'equipment', 'service_type', 'time_type', 'status'
    ]
    list_filter = ['status', 'service_type', 'time_type', 'technician', 'scheduled_date']
    search_fields = ['appointment_no', 'equipment__name', 'technician__first_name',
                     'equipment__customer__name']
    date_hierarchy = 'scheduled_date'
    readonly_fields = ['appointment_no', 'created_at', 'updated_at']
