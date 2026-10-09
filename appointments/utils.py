import calendar
from datetime import date


def add_months(source_date, months):
    """Add a given number of months to a date, handling month-end edge cases."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


OFFICE_HOURS_START  = (8, 30)    # 08:30
OFFICE_HOURS_END    = (16, 30)   # 16:30
OFFICE_WEEKDAYS     = [0, 1, 2, 3, 4]   # Mon-Fri
OT_WEEKDAY_START    = (16, 30)   # นอกเวลา จ.-ศ. เริ่ม
OT_WEEKDAY_END      = (20, 30)   # นอกเวลา จ.-ศ. สิ้นสุด
OT_WEEKDAY_MINUTES  = 240        # 4 ชั่วโมง
OT_WEEKEND_MINUTES  = 480        # 8 ชั่วโมง (เสาร์-อาทิตย์ 08:30-16:30)


def detect_time_type(check_date, check_time):
    """Return 'office', 'overtime_wday', or 'overtime_wknd'."""
    dow = check_date.weekday()
    t   = (check_time.hour, check_time.minute)
    if dow >= 5:                  # เสาร์/อาทิตย์
        return 'overtime_wknd'
    if t >= OT_WEEKDAY_START:    # จ.-ศ. หลัง 16:30
        return 'overtime_wday'
    return 'office'


def is_office_hours(check_date, check_time):
    """Return True if within regular office hours (backward-compat)."""
    return detect_time_type(check_date, check_time) == 'office'


STATUS_COLORS = {
    'scheduled': 'primary',
    'confirmed': 'info',
    'in_progress': 'warning',
    'completed': 'success',
    'cancelled': 'secondary',
    'rescheduled': 'danger',
}

SERVICE_TYPE_COLORS = {
    'PM': 'success',
    'CAL': 'info',
    'PM_CAL': 'primary',
    'CM': 'warning',
}
