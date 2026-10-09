from django.db import models
from datetime import date
from .utils import add_months, is_office_hours, detect_time_type


class Skill(models.Model):
    name = models.CharField(max_length=100, verbose_name='ชื่อทักษะ')
    description = models.TextField(blank=True, verbose_name='รายละเอียด')
    SKILL_TYPE_CHOICES = [
        ('pm', 'บำรุงรักษา (PM)'),
        ('cal', 'สอบเทียบ (Calibration)'),
        ('repair', 'ซ่อม/แก้ไข (Repair)'),
        ('general', 'ทั่วไป'),
    ]
    skill_type = models.CharField(max_length=10, choices=SKILL_TYPE_CHOICES, default='general', verbose_name='ประเภททักษะ')

    class Meta:
        verbose_name = 'ทักษะ'
        verbose_name_plural = 'ทักษะช่าง'
        ordering = ['name']

    def __str__(self):
        return self.name


class Technician(models.Model):
    employee_id = models.CharField(max_length=20, unique=True, verbose_name='รหัสพนักงาน')
    first_name = models.CharField(max_length=100, verbose_name='ชื่อ')
    last_name = models.CharField(max_length=100, verbose_name='นามสกุล')
    phone = models.CharField(max_length=20, verbose_name='โทรศัพท์')
    email = models.EmailField(blank=True, verbose_name='อีเมล')
    skills = models.ManyToManyField(Skill, blank=True, related_name='technicians', verbose_name='ทักษะ')
    color = models.CharField(max_length=7, default='#3498db', verbose_name='สีปฏิทิน',
                             help_text='รหัสสี Hex เช่น #3498db')
    is_active = models.BooleanField(default=True, verbose_name='ปฏิบัติงาน')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ช่างเทคนิค'
        verbose_name_plural = 'ช่างเทคนิค'
        ordering = ['employee_id']

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"{self.employee_id} - {self.full_name}"

    def is_available_on(self, check_date):
        """Return True if the technician is scheduled to work and has no leave on check_date."""
        if not self.is_active:
            return False
        if not self.work_days.filter(day_of_week=check_date.weekday()).exists():
            return False
        return not self.leaves.filter(leave_date=check_date).exists()


class TechnicianWorkDay(models.Model):
    WEEKDAY_CHOICES = [
        (0, 'จันทร์'),
        (1, 'อังคาร'),
        (2, 'พุธ'),
        (3, 'พฤหัสบดี'),
        (4, 'ศุกร์'),
        (5, 'เสาร์'),
        (6, 'อาทิตย์'),
    ]
    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name='work_days')
    day_of_week = models.IntegerField(choices=WEEKDAY_CHOICES, verbose_name='วัน')

    class Meta:
        unique_together = ('technician', 'day_of_week')
        verbose_name = 'วันทำงาน'
        verbose_name_plural = 'วันทำงาน'
        ordering = ['day_of_week']

    def __str__(self):
        return f"{self.technician.full_name} - {self.get_day_of_week_display()}"


class TechnicianLeave(models.Model):
    LEAVE_TYPE_CHOICES = [
        ('sick', 'ลาป่วย'),
        ('personal', 'ลากิจ'),
        ('vacation', 'ลาพักร้อน'),
        ('official', 'ไปราชการ/อบรม'),
        ('other', 'อื่นๆ'),
    ]
    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name='leaves')
    leave_date = models.DateField(verbose_name='วันที่')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES,
                                  default='personal', verbose_name='ประเภท')
    reason = models.CharField(max_length=200, blank=True, verbose_name='เหตุผล')

    class Meta:
        verbose_name = 'การลา/ไม่อยู่'
        verbose_name_plural = 'การลา/ไม่อยู่'
        ordering = ['-leave_date']

    def __str__(self):
        return f"{self.technician.full_name} - {self.leave_date} ({self.get_leave_type_display()})"


class TechnicianOvertimeDay(models.Model):
    """วันที่ช่างลงทะเบียนนอกเวลาล่วงหน้า:
    - จ.-ศ. หลัง 16:30 (นอกเวลา 16:30-20:30)
    - เสาร์/อาทิตย์ 08:30-16:30
    """
    technician = models.ForeignKey(
        Technician, on_delete=models.CASCADE,
        related_name='overtime_days', verbose_name='ช่าง')
    date = models.DateField(verbose_name='วันที่')

    class Meta:
        unique_together = ('technician', 'date')
        verbose_name = 'วันทำงานนอกเวลา'
        verbose_name_plural = 'วันทำงานนอกเวลา'
        ordering = ['date']

    @property
    def is_weekday(self):
        return self.date.weekday() <= 4

    @property
    def session_label(self):
        return 'นอกเวลา จ.-ศ. (16:30–20:30)' if self.is_weekday else 'เสาร์/อาทิตย์ (08:30–16:30)'

    @property
    def start_time_str(self):
        return '16:30' if self.is_weekday else '08:30'

    @property
    def end_time_str(self):
        return '20:30' if self.is_weekday else '16:30'

    @property
    def duration_minutes(self):
        return 240 if self.is_weekday else 480

    def __str__(self):
        return f"{self.technician.full_name} – {self.date} ({self.session_label})"


class Customer(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='รหัสลูกค้า')
    name = models.CharField(max_length=200, verbose_name='ชื่อโรงพยาบาล/หน่วยงาน')
    address = models.TextField(blank=True, verbose_name='ที่อยู่')
    phone = models.CharField(max_length=20, blank=True, verbose_name='โทรศัพท์')
    email = models.EmailField(blank=True, verbose_name='อีเมล')
    contact_person = models.CharField(max_length=100, blank=True, verbose_name='ผู้ติดต่อ')
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
        verbose_name='องค์กรต้นทาง',
    )

    class Meta:
        verbose_name = 'ลูกค้า'
        verbose_name_plural = 'ลูกค้า'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class CustomerContact(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE,
        related_name='contacts', verbose_name='ลูกค้า')
    name = models.CharField(max_length=100, verbose_name='ชื่อผู้ติดต่อ')
    role = models.CharField(max_length=100, blank=True, verbose_name='ตำแหน่ง')
    phone = models.CharField(max_length=20, blank=True, verbose_name='โทรศัพท์')
    email = models.EmailField(blank=True, verbose_name='อีเมล')

    class Meta:
        verbose_name = 'ผู้ติดต่อ'
        verbose_name_plural = 'ผู้ติดต่อลูกค้า'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.customer.code})"


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name='ประเภทเครื่องมือ')
    required_skills = models.ManyToManyField(Skill, blank=True, verbose_name='ทักษะที่ต้องการ')

    class Meta:
        verbose_name = 'ประเภทเครื่องมือ'
        verbose_name_plural = 'ประเภทเครื่องมือแพทย์'
        ordering = ['name']

    def __str__(self):
        return self.name


class Equipment(models.Model):
    equipment_code = models.CharField(max_length=50, blank=True, verbose_name='รหัสเครื่อง')
    serial_number = models.CharField(max_length=100, unique=True, verbose_name='SerialNo')
    asset_number = models.CharField(max_length=50, blank=True, verbose_name='เลขครุภัณฑ์')
    name = models.CharField(max_length=200, verbose_name='ชื่อเครื่อง')
    name_th = models.CharField(max_length=200, blank=True, verbose_name='ชื่อเครื่องภาษาไทย')
    model = models.CharField(max_length=100, verbose_name='รุ่น')
    manufacturer = models.CharField(max_length=100, blank=True, verbose_name='ยี่ห้อ')
    category = models.ForeignKey(EquipmentCategory, on_delete=models.SET_NULL,
                                  null=True, blank=True, verbose_name='ประเภท')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,
                                  related_name='equipment', verbose_name='ลูกค้า/โรงพยาบาล')
    owner_unit_name = models.CharField(max_length=255, blank=True, verbose_name='ชื่อหน่วยงานเจ้าของเครื่อง')
    user_unit_name = models.CharField(max_length=255, blank=True, verbose_name='ชื่อหน่วยงานที่ใช้เครื่อง')
    department = models.CharField(max_length=200, blank=True, verbose_name='ภาควิชา/ฝ่าย/งาน')

    # Maintenance (PM)
    maintenance_duration_minutes = models.PositiveIntegerField(
        default=120, verbose_name='เวลา PM (นาที)')
    maintenance_interval_months = models.PositiveIntegerField(
        default=12, verbose_name='รอบ PM (เดือน)')
    last_maintenance_date = models.DateField(null=True, blank=True, verbose_name='PM ล่าสุด')
    next_maintenance_date = models.DateField(null=True, blank=True, verbose_name='PM ครั้งถัดไป')

    # Calibration
    requires_calibration = models.BooleanField(default=False, verbose_name='ต้องสอบเทียบ')
    calibration_duration_minutes = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='เวลาสอบเทียบ (นาที)')
    calibration_interval_months = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='รอบสอบเทียบ (เดือน)')
    last_calibration_date = models.DateField(null=True, blank=True, verbose_name='สอบเทียบล่าสุด')
    next_calibration_date = models.DateField(null=True, blank=True,
                                              verbose_name='สอบเทียบครั้งถัดไป')

    maintenance_required_skills = models.ManyToManyField(
        Skill, blank=True, related_name='equipment_pm_required',
        verbose_name='ทักษะที่ต้องการสำหรับ PM'
    )
    calibration_required_skills = models.ManyToManyField(
        Skill, blank=True, related_name='equipment_cal_required',
        verbose_name='ทักษะที่ต้องการสำหรับสอบเทียบ'
    )

    repair_required_skills = models.ManyToManyField(
        Skill, blank=True, related_name='equipment_repair_required',
        verbose_name='ทักษะที่ต้องการสำหรับซ่อม'
    )

    required_skills = models.ManyToManyField(Skill, blank=True, related_name='equipment',
                                              verbose_name='ทักษะที่ต้องการ')
    is_active = models.BooleanField(default=True, verbose_name='ใช้งาน')

    class Meta:
        verbose_name = 'เครื่องมือแพทย์'
        verbose_name_plural = 'เครื่องมือแพทย์'
        ordering = ['customer', 'name']

    def __str__(self):
        return f"{self.serial_number} - {self.name}"

    def required_skill_ids_for_service(self, service_type):
        if service_type == 'PM':
            skills = self.maintenance_required_skills
        elif service_type == 'CAL':
            skills = self.calibration_required_skills
        elif service_type == 'CM':
            skills = self.repair_required_skills
        elif service_type == 'PM_CAL':
            skill_ids = set(self.maintenance_required_skills.values_list('pk', flat=True)) | set(
                self.calibration_required_skills.values_list('pk', flat=True))
            if skill_ids:
                return skill_ids
            skills = self.required_skills
        else:
            skills = self.required_skills
        skill_ids = set(skills.values_list('pk', flat=True))
        if skill_ids:
            return skill_ids
        if service_type in ('PM', 'PM_CAL') and self.category_id:
            return set(self.category.required_skills.values_list('pk', flat=True))
        return set()

    @property
    def total_service_duration_minutes(self):
        """Total time for PM + Calibration (if required)."""
        total = self.maintenance_duration_minutes
        if self.requires_calibration and self.calibration_duration_minutes:
            total += self.calibration_duration_minutes
        return total

    @property
    def maintenance_status(self):
        """'overdue', 'due_soon' (≤30 days), or 'ok'."""
        if not self.next_maintenance_date:
            return 'unknown'
        days = (self.next_maintenance_date - date.today()).days
        if days < 0:
            return 'overdue'
        if days <= 30:
            return 'due_soon'
        return 'ok'

    @property
    def calibration_status(self):
        if not self.requires_calibration or not self.next_calibration_date:
            return 'not_required'
        days = (self.next_calibration_date - date.today()).days
        if days < 0:
            return 'overdue'
        if days <= 30:
            return 'due_soon'
        return 'ok'

    @property
    def days_until_maintenance(self):
        if not self.next_maintenance_date:
            return None
        return (self.next_maintenance_date - date.today()).days

    @property
    def days_until_calibration(self):
        if not self.requires_calibration or not self.next_calibration_date:
            return None
        return (self.next_calibration_date - date.today()).days

    def save(self, *args, **kwargs):
        # Auto-calculate next dates from last service dates
        if self.last_maintenance_date and self.maintenance_interval_months:
            self.next_maintenance_date = add_months(
                self.last_maintenance_date, self.maintenance_interval_months)
        if (self.requires_calibration and self.last_calibration_date
                and self.calibration_interval_months):
            self.next_calibration_date = add_months(
                self.last_calibration_date, self.calibration_interval_months)
        super().save(*args, **kwargs)


class Appointment(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('PM', 'บำรุงรักษาเชิงป้องกัน (PM)'),
        ('CAL', 'สอบเทียบ (Calibration)'),
        ('PM_CAL', 'บำรุงรักษาเชิงป้องกัน (PM) และสอบเทียบ (Calibration)'),
        ('CM', 'ซ่อมแซม / แก้ไขปัญหา'),
    ]
    TIME_TYPE_CHOICES = [
        ('office',        'ในเวลาราชการ (08:30–16:30)'),
        ('overtime_wday', 'นอกเวลา จ.-ศ. (16:30–20:30)'),
        ('overtime_wknd', 'เสาร์/อาทิตย์ (08:30–16:30)'),
        ('overtime',      'นอกเวลา (เดิม)'),  # legacy
    ]
    STATUS_CHOICES = [
        ('scheduled', 'นัดหมาย'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('in_progress', 'กำลังดำเนินการ'),
        ('completed', 'เสร็จสิ้น'),
        ('cancelled', 'ยกเลิก'),
        ('rescheduled', 'เลื่อนนัด'),
    ]

    appointment_no = models.CharField(
        max_length=20, unique=True, verbose_name='เลขที่นัดหมาย', blank=True)
    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name='appointments',
        verbose_name='เครื่องมือแพทย์')
    technician = models.ForeignKey(
        Technician, on_delete=models.CASCADE, related_name='appointments',
        verbose_name='ช่างเทคนิค')
    service_type = models.CharField(
        max_length=10, choices=SERVICE_TYPE_CHOICES, verbose_name='ประเภทงาน')
    time_type = models.CharField(
        max_length=15, choices=TIME_TYPE_CHOICES, default='office',
        verbose_name='ช่วงเวลา')

    scheduled_date = models.DateField(verbose_name='วันที่นัด')
    start_time = models.TimeField(verbose_name='เวลาเริ่ม')
    end_time = models.TimeField(verbose_name='เวลาสิ้นสุด')
    duration_minutes = models.PositiveIntegerField(verbose_name='ระยะเวลา (นาที)')

    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='scheduled', verbose_name='สถานะ')
    notes = models.TextField(blank=True, verbose_name='หมายเหตุ')
    coordinator_name = models.CharField(max_length=100, verbose_name='ผู้ประสานงาน')

    # ── Workflow fields ──
    equipment_received = models.BooleanField(default=False, verbose_name='รับเครื่องแล้ว')
    equipment_received_at = models.DateTimeField(null=True, blank=True, verbose_name='เวลารับเครื่อง')
    assigned_to = models.ForeignKey(
        'Technician', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_appointments', verbose_name='ผู้รับงาน')
    actual_completion_date = models.DateField(null=True, blank=True, verbose_name='วันที่เสร็จจริง')
    completion_notes = models.TextField(blank=True, verbose_name='บันทึกผลงาน')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'การนัดหมาย'
        verbose_name_plural = 'การนัดหมาย'
        ordering = ['scheduled_date', 'start_time']

    def __str__(self):
        return f"{self.appointment_no} - {self.equipment.name} ({self.scheduled_date})"

    def save(self, *args, **kwargs):
        # Auto-generate appointment number
        if not self.appointment_no:
            today = date.today()
            prefix = f"APT{today.strftime('%Y%m%d')}"
            last = (Appointment.objects
                    .filter(appointment_no__startswith=prefix)
                    .order_by('-appointment_no')
                    .first())
            suffix = last.appointment_no[len(prefix):] if last else None
            seq = (int(suffix) + 1) if (suffix and suffix.isdigit()) else 1
            self.appointment_no = f"{prefix}{seq:03d}"

        # Auto-detect time type
        self.time_type = detect_time_type(self.scheduled_date, self.start_time)
        super().save(*args, **kwargs)

    def mark_completed(self, completion_date, notes=''):
        """Complete this appointment and update the equipment service registry."""
        self.status = 'completed'
        self.actual_completion_date = completion_date
        self.completion_notes = notes
        self.save()
        equip = self.equipment
        if self.service_type in ('PM', 'PM_CAL'):
            equip.last_maintenance_date = completion_date
        if self.service_type in ('CAL', 'PM_CAL'):
            equip.last_calibration_date = completion_date
        if self.service_type in ('PM', 'CAL', 'PM_CAL'):
            equip.save()  # triggers auto-calculation of next due dates
