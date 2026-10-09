from datetime import date, datetime, timedelta
import calendar
import io
import json
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AppointmentForm, CustomerForm, CustomerContactForm, EquipmentForm,
    TechnicianForm, TechnicianLeaveForm, TechnicianOvertimeDayForm,
)
from .models import (
    Appointment, Customer, CustomerContact, Equipment, EquipmentCategory,
    Skill, Technician, TechnicianLeave, TechnicianOvertimeDay,
)
from .utils import (
    STATUS_COLORS, SERVICE_TYPE_COLORS,
    OFFICE_HOURS_START, OFFICE_HOURS_END,
)


# ─────────────────────────── Dashboard ───────────────────────────

def dashboard(request):
    today = date.today()
    thirty_days_later = today + timedelta(days=30)

    total_equipment = Equipment.objects.filter(is_active=True).count()
    total_technicians = Technician.objects.filter(is_active=True).count()

    overdue_maintenance = Equipment.objects.filter(
        is_active=True, next_maintenance_date__lt=today).count()
    overdue_calibration = Equipment.objects.filter(
        is_active=True, requires_calibration=True,
        next_calibration_date__lt=today).count()
    due_soon = Equipment.objects.filter(
        is_active=True,
        next_maintenance_date__gte=today,
        next_maintenance_date__lte=thirty_days_later,
    ).count()

    today_appointments = (
        Appointment.objects
        .filter(scheduled_date=today)
        .select_related('equipment', 'technician', 'equipment__customer')
        .order_by('start_time')
    )

    week_end = today + timedelta(days=7)
    upcoming_appointments = (
        Appointment.objects
        .filter(scheduled_date__gte=today, scheduled_date__lte=week_end,
                status__in=['scheduled', 'confirmed'])
        .select_related('equipment', 'technician', 'equipment__customer')
        .order_by('scheduled_date', 'start_time')[:15]
    )

    overdue_equipment = (
        Equipment.objects
        .filter(is_active=True, next_maintenance_date__lt=today)
        .select_related('customer', 'category')
        .order_by('next_maintenance_date')[:10]
    )

    technician_stats = []
    for tech in Technician.objects.filter(is_active=True).prefetch_related('work_days'):
        week_count = Appointment.objects.filter(
            technician=tech,
            scheduled_date__gte=today,
            scheduled_date__lte=week_end,
            status__in=['scheduled', 'confirmed'],
        ).count()
        technician_stats.append({
            'technician': tech,
            'week_count': week_count,
            'available_today': tech.is_available_on(today),
        })

    context = {
        'total_equipment': total_equipment,
        'total_technicians': total_technicians,
        'overdue_maintenance': overdue_maintenance,
        'overdue_calibration': overdue_calibration,
        'due_soon': due_soon,
        'today_appointments': today_appointments,
        'upcoming_appointments': upcoming_appointments,
        'overdue_equipment': overdue_equipment,
        'technician_stats': technician_stats,
        'today': today,
        'status_colors': STATUS_COLORS,
    }
    return render(request, 'appointments/dashboard.html', context)


# ─────────────────────────── Schedule / Calendar ───────────────────────────

def schedule(request):
    technicians = Technician.objects.filter(is_active=True)
    context = {'technicians': technicians}
    return render(request, 'appointments/schedule.html', context)


def _build_upcoming_ot(from_date):
    """Return OT days grouped by date for the next 14 days."""
    until = from_date + timedelta(days=13)
    ot_list = (
        TechnicianOvertimeDay.objects
        .filter(date__gte=from_date, date__lte=until)
        .select_related('technician')
        .order_by('date', 'technician__first_name')
    )
    grouped = {}
    for ot in ot_list:
        grouped.setdefault(ot.date, []).append(ot)
    return [{'date': d, 'items': items} for d, items in sorted(grouped.items())]


def ot_schedule(request):
    """Monthly OT calendar showing all technicians' overtime days."""
    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError):
        year, month = today.year, today.month

    # Clamp to reasonable range
    year = max(2020, min(2035, year))

    # Navigation
    prev_month_date = date(year, month, 1) - timedelta(days=1)
    next_month_date = date(year, month, calendar.monthrange(year, month)[1]) + timedelta(days=1)

    # All OT days this month
    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])
    ot_qs = (
        TechnicianOvertimeDay.objects
        .filter(date__gte=first_day, date__lte=last_day)
        .select_related('technician')
        .order_by('date', 'technician__first_name')
    )
    ot_by_date = defaultdict(list)
    for ot in ot_qs:
        ot_by_date[ot.date].append(ot)

    # Build calendar grid (weeks × 7)
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    weeks = cal.monthdatescalendar(year, month)
    grid = []
    for week in weeks:
        row = []
        for d in week:
            row.append({
                'date':        d,
                'in_month':    d.month == month,
                'is_today':    d == today,
                'ot_items':    ot_by_date.get(d, []),
            })
        grid.append(row)

    # Technician legend (only those with OT this month)
    tech_ids = {ot.technician_id for ot in ot_qs}
    technicians = Technician.objects.filter(pk__in=tech_ids).order_by('first_name')

    return render(request, 'appointments/ot_schedule.html', {
        'year':             year,
        'month':            month,
        'month_name':       first_day.strftime('%B %Y'),
        'grid':             grid,
        'technicians':      technicians,
        'all_technicians':  Technician.objects.filter(is_active=True).order_by('first_name'),
        'prev_month':       prev_month_date,
        'next_month':       next_month_date,
        'today':            today,
        'weekday_labels':   ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'],
    })


def _build_ot_section(selected_date, day_apts, by_tech):
    """Build OT rows for the dispatch board."""
    is_weekday  = selected_date.weekday() <= 4
    OT_START    = 16 * 60 + 30 if is_weekday else 8 * 60 + 30
    OT_TOTAL    = 240 if is_weekday else 480

    ot_ids = set(
        TechnicianOvertimeDay.objects
        .filter(date=selected_date)
        .values_list('technician_id', flat=True)
    )
    if not ot_ids:
        return {
            'ot_rows': [], 'is_weekday': is_weekday,
            'ot_label': '',
            'ot_start_str': '16:30' if is_weekday else '08:30',
            'ot_end_str':   '20:30' if is_weekday else '16:30',
            'ot_ruler': [],
        }

    ot_rows = []
    for tech in (Technician.objects.filter(is_active=True, pk__in=ot_ids)
                 .prefetch_related('leaves')):
        on_leave = tech.leaves.filter(leave_date=selected_date).exists()
        raw = list(by_tech.get(tech.pk, []))
        apts = [a for a in raw
                if not is_weekday or (a.start_time.hour * 60 + a.start_time.minute) >= OT_START]
        busy      = sum(a.duration_minutes for a in apts)
        remaining = max(0, OT_TOTAL - busy)
        blocks = []
        for apt in apts:
            s     = apt.start_time.hour * 60 + apt.start_time.minute
            left  = max(0, (s - OT_START) / OT_TOTAL * 100)
            width = min(100 - left, apt.duration_minutes / OT_TOTAL * 100)
            blocks.append({'apt': apt, 'left': round(left, 2), 'width': round(max(width, 1.5), 2)})
        status = ('leave' if on_leave else
                  'full' if remaining == 0 else
                  'limited' if remaining <= 60 else 'available')
        ot_rows.append({
            'tech': tech, 'apts': apts, 'blocks': blocks,
            'busy_min': busy, 'remaining': remaining,
            'status': status, 'on_leave': on_leave,
        })
    ot_rows.sort(key=lambda r: {'available': 0, 'limited': 1, 'full': 2, 'leave': 3}.get(r['status'], 4))

    return {
        'ot_rows':      ot_rows,
        'is_weekday':   is_weekday,
        'ot_label':     'นอกเวลา จ.-ศ. (16:30–20:30)' if is_weekday else 'เสาร์/อาทิตย์ (08:30–16:30)',
        'ot_start_str': '16:30' if is_weekday else '08:30',
        'ot_end_str':   '20:30' if is_weekday else '16:30',
        'ot_ruler':     [('17:00', 12.5), ('18:00', 37.5), ('19:00', 62.5), ('20:00', 87.5)]
                        if is_weekday else
                        [('09:00', 6.25), ('10:00', 18.75), ('11:00', 31.25),
                         ('12:00', 43.75), ('13:00', 56.25), ('14:00', 68.75),
                         ('15:00', 81.25), ('16:00', 93.75)],
    }


def dispatch_board(request):
    """Daily dispatch board: see every technician's workload for a selected date."""
    date_str = request.GET.get('date', '')
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = date.today()

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)

    OFFICE_START = 8 * 60 + 30    # 510 min
    OFFICE_END   = 16 * 60 + 30   # 990 min
    OFFICE_TOTAL = OFFICE_END - OFFICE_START   # 480 min

    active_statuses = ['scheduled', 'confirmed', 'in_progress']
    day_apts = (
        Appointment.objects
        .filter(scheduled_date=selected_date, status__in=active_statuses)
        .select_related('equipment', 'equipment__customer', 'technician')
        .order_by('start_time')
    )
    by_tech = defaultdict(list)
    for apt in day_apts:
        by_tech[apt.technician_id].append(apt)

    rows = []
    for tech in (Technician.objects.filter(is_active=True)
                 .prefetch_related('work_days', 'leaves', 'skills')):
        is_work_day = tech.work_days.filter(day_of_week=selected_date.weekday()).exists()
        on_leave    = tech.leaves.filter(leave_date=selected_date).exists()
        available   = is_work_day and not on_leave

        apts     = by_tech.get(tech.pk, [])
        busy_min = sum(a.duration_minutes for a in apts)
        remaining = max(0, OFFICE_TOTAL - busy_min) if available else 0

        blocks = []
        for apt in apts:
            s_min = apt.start_time.hour * 60 + apt.start_time.minute
            left  = max(0, (s_min - OFFICE_START) / OFFICE_TOTAL * 100)
            width = min(100 - left, apt.duration_minutes / OFFICE_TOTAL * 100)
            blocks.append({
                'apt':   apt,
                'left':  round(left, 2),
                'width': round(max(width, 1.5), 2),
            })

        if not is_work_day:
            status = 'off'
        elif on_leave:
            status = 'leave'
        elif remaining == 0:
            status = 'full'
        elif remaining <= 90:
            status = 'limited'
        else:
            status = 'available'

        rows.append({
            'tech': tech,
            'available': available,
            'on_leave': on_leave,
            'is_work_day': is_work_day,
            'status': status,
            'apts': apts,
            'busy_min': busy_min,
            'remaining': remaining,
            'blocks': blocks,
        })

    rows.sort(key=lambda r: {'available': 0, 'limited': 1, 'full': 2, 'leave': 3, 'off': 4}.get(r['status'], 5))

    summary = {
        'available': sum(1 for r in rows if r['status'] in ('available', 'limited')),
        'full':      sum(1 for r in rows if r['status'] == 'full'),
        'off':       sum(1 for r in rows if r['status'] in ('leave', 'off')),
        'total_apts': sum(len(r['apts']) for r in rows),
    }

    return render(request, 'appointments/dispatch_board.html', {
        'selected_date': selected_date,
        'prev_date':     prev_date,
        'next_date':     next_date,
        'rows':          rows,
        'summary':       summary,
        'ruler': [
            ('09:00', 6.25), ('10:00', 18.75), ('11:00', 31.25),
            ('12:00', 43.75), ('13:00', 56.25), ('14:00', 68.75),
            ('15:00', 81.25), ('16:00', 93.75),
        ],
        # ── OT section ──
        **_build_ot_section(selected_date, day_apts, by_tech),
        # ── Upcoming OT schedule (14 days) ──
        'upcoming_ot_schedule': _build_upcoming_ot(selected_date),
    })


def api_appointments(request):
    """JSON endpoint consumed by FullCalendar."""
    start_str = request.GET.get('start', '')
    end_str = request.GET.get('end', '')
    technician_id = request.GET.get('technician', 'all')

    qs = Appointment.objects.filter(
        status__in=['scheduled', 'confirmed', 'in_progress', 'completed']
    ).select_related('equipment', 'technician', 'equipment__customer')

    if start_str:
        qs = qs.filter(scheduled_date__gte=start_str[:10])
    if end_str:
        qs = qs.filter(scheduled_date__lte=end_str[:10])
    if technician_id and technician_id != 'all':
        qs = qs.filter(technician_id=technician_id)

    events = []
    for apt in qs:
        color = apt.technician.color
        if apt.status == 'completed':
            color = '#27ae60'
        elif apt.status == 'cancelled':
            color = '#95a5a6'

        start_iso = datetime.combine(apt.scheduled_date, apt.start_time).isoformat()
        end_iso = datetime.combine(apt.scheduled_date, apt.end_time).isoformat()

        events.append({
            'id': apt.pk,
            'title': f"{apt.technician.first_name}\n{apt.equipment.name}",
            'start': start_iso,
            'end': end_iso,
            'color': color,
            'borderColor': '#333' if apt.time_type == 'overtime' else color,
            'extendedProps': {
                'appointment_no': apt.appointment_no,
                'technician': apt.technician.full_name,
                'equipment': apt.equipment.name,
                'serial_number': apt.equipment.serial_number,
                'customer': apt.equipment.customer.name,
                'department': apt.equipment.department,
                'service_type': apt.get_service_type_display(),
                'time_type': apt.get_time_type_display(),
                'status': apt.get_status_display(),
                'duration': apt.duration_minutes,
                'notes': apt.notes,
                'is_overtime': apt.time_type == 'overtime',
                'detail_url': f'/appointments/{apt.pk}/',
            },
        })
    return JsonResponse(events, safe=False)


def api_equipment_info(request, pk):
    """Return equipment service-time data for the appointment form."""
    equip = get_object_or_404(Equipment, pk=pk)
    return JsonResponse({
        'maintenance_duration': equip.maintenance_duration_minutes,
        'calibration_duration': equip.calibration_duration_minutes or 0,
        'total_duration': equip.total_service_duration_minutes,
        'requires_calibration': equip.requires_calibration,
        'default_service_type': 'PM_CAL' if equip.requires_calibration else 'PM',
        'customer': equip.customer.name,
        'department': equip.department,
    })


def api_equipment_search(request):
    """Autocomplete search for equipment by code/serial/name (used on the appointment form)."""
    q = request.GET.get('q', '').strip()
    qs = Equipment.objects.filter(is_active=True).select_related('customer')
    if q:
        qs = qs.filter(
            Q(equipment_code__icontains=q) |
            Q(serial_number__icontains=q) |
            Q(asset_number__icontains=q) |
            Q(name__icontains=q) |
            Q(name_th__icontains=q) |
            Q(customer__name__icontains=q)
        )
    qs = qs.order_by('equipment_code')[:20]
    results = [{
        'id': e.pk,
        'code': e.equipment_code or '-',
        'name': e.name,
        'name_th': e.name_th,
        'serial_number': e.serial_number,
        'customer': e.customer.name,
        'department': e.department,
        'requires_calibration': e.requires_calibration,
        'duration': e.total_service_duration_minutes,
    } for e in qs]
    return JsonResponse({'results': results})


def api_skill_search(request):
    """Autocomplete search for Skill by name."""
    q = request.GET.get('q', '').strip()
    qs = Skill.objects.all()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(name_th__icontains=q))
    qs = qs.order_by('name')[:20]
    results = [{'id': s.pk, 'name': s.name} for s in qs]
    return JsonResponse({'results': results})


def api_technician_suggestions(request):
    """Suggest available technicians for an equipment on a given date, with remaining capacity.

    Capacity is estimated as: remaining office minutes that day (office hours minus
    minutes already booked) divided by the equipment's average service duration.
    """
    equipment_id = request.GET.get('equipment_id')
    date_str = request.GET.get('date')
    service_type = request.GET.get('service_type', 'PM')
    if not equipment_id or not date_str:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    try:
        equipment = Equipment.objects.prefetch_related(
            'required_skills', 'maintenance_required_skills',
            'calibration_required_skills', 'repair_required_skills',
        ).get(pk=equipment_id)
        check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (Equipment.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    duration = equipment.total_service_duration_minutes or 1
    required_skill_ids = equipment.required_skill_ids_for_service(service_type)
    office_minutes = (
        (OFFICE_HOURS_END[0] * 60 + OFFICE_HOURS_END[1])
        - (OFFICE_HOURS_START[0] * 60 + OFFICE_HOURS_START[1])
    )

    active_statuses = ['scheduled', 'confirmed', 'in_progress']
    results = []
    technicians = (
        Technician.objects.filter(is_active=True)
        .prefetch_related('skills', 'work_days', 'leaves')
    )
    for tech in technicians:
        tech_skill_ids = set(tech.skills.values_list('pk', flat=True))
        skill_match = required_skill_ids.issubset(tech_skill_ids)
        is_work_day = tech.work_days.filter(day_of_week=check_date.weekday()).exists()
        on_leave = tech.leaves.filter(leave_date=check_date).exists()
        available = is_work_day and not on_leave

        day_appointments = Appointment.objects.filter(
            technician=tech, scheduled_date=check_date, status__in=active_statuses)
        busy_minutes = day_appointments.aggregate(total=Sum('duration_minutes'))['total'] or 0
        job_count = day_appointments.count()

        remaining_minutes = max(0, office_minutes - busy_minutes)
        capacity_remaining = remaining_minutes // duration
        score = (50 if skill_match else 0) + (40 if available else 0)
        score += min(capacity_remaining, 10)

        results.append({
            'id': tech.pk,
            'name': tech.full_name,
            'color': tech.color,
            'skill_match': skill_match,
            'is_work_day': is_work_day,
            'on_leave': on_leave,
            'available': available,
            'job_count_today': job_count,
            'busy_minutes': busy_minutes,
            'remaining_minutes': remaining_minutes,
            'capacity_remaining': capacity_remaining,
            'recommendation_score': score,
        })

    # Rank candidates transparently so the UI can explain the recommendation.
    results.sort(key=lambda r: (-r['recommendation_score'], r['busy_minutes'], r['name']))
    recommendation = None
    if results:
        recommended = next((r for r in results if r['available'] and r['skill_match']), None)
        if not recommended:
            return JsonResponse({
                'equipment_duration': duration,
                'office_minutes': office_minutes,
                'recommendation': None,
                'message': 'ไม่พบช่างที่มีทักษะตรงกับประเภทงานและว่างในวันที่เลือก',
                'technicians': results,
            })
        reasons = []
        if recommended['skill_match']:
            reasons.append('ทักษะตรงกับงาน')
        if recommended['available']:
            reasons.append('มีเวรและไม่ลาในวันที่เลือก')
        if recommended['capacity_remaining'] > 0:
            reasons.append(f"ยังรับงานได้อีก {recommended['capacity_remaining']} เครื่อง")
        recommendation = {
            'id': recommended['id'],
            'name': recommended['name'],
            'reasons': reasons,
        }

    return JsonResponse({
        'equipment_duration': duration,
        'office_minutes': office_minutes,
        'recommendation': recommendation,
        'technicians': results,
    })


def api_calendar_availability(request):
    """Per-day availability summary for a month, used to color the date-picker calendar.

    Status per day:
      'closed'    – no eligible technician is scheduled to work that day.
      'full'      – technicians are on duty but have no remaining capacity.
      'limited'   – some capacity left, but low (<=2 more jobs).
      'available' – plenty of capacity left.
    """
    try:
        year = int(request.GET.get('year'))
        month = int(request.GET.get('month'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    if not (1 <= month <= 12):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    equipment_id = request.GET.get('equipment_id')
    technician_id = request.GET.get('technician_id')

    duration = 120
    required_skill_ids = set()
    service_type = request.GET.get('service_type', 'PM')
    if equipment_id:
        try:
            equipment = Equipment.objects.prefetch_related(
                'required_skills', 'maintenance_required_skills',
                'calibration_required_skills', 'repair_required_skills',
            ).get(pk=equipment_id)
            duration = equipment.total_service_duration_minutes or 120
            required_skill_ids = equipment.required_skill_ids_for_service(service_type)
        except Equipment.DoesNotExist:
            pass

    technicians_qs = (
        Technician.objects.filter(is_active=True)
        .prefetch_related('skills', 'work_days', 'leaves')
    )
    if technician_id:
        technicians_qs = technicians_qs.filter(pk=technician_id)
    technicians = list(technicians_qs)
    if required_skill_ids and not technician_id:
        technicians = [
            t for t in technicians
            if required_skill_ids.issubset(set(t.skills.values_list('pk', flat=True)))
        ]

    # Build in-memory lookups (uses the prefetch cache, avoids per-day queries).
    tech_workdays = {t.pk: {wd.day_of_week for wd in t.work_days.all()} for t in technicians}
    tech_leavedates = {t.pk: {lv.leave_date for lv in t.leaves.all()} for t in technicians}

    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    office_minutes = (
        (OFFICE_HOURS_END[0] * 60 + OFFICE_HOURS_END[1])
        - (OFFICE_HOURS_START[0] * 60 + OFFICE_HOURS_START[1])
    )
    active_statuses = ['scheduled', 'confirmed', 'in_progress']

    busy_by_day = defaultdict(dict)
    tech_ids = list(tech_workdays.keys())
    if tech_ids:
        rows = (
            Appointment.objects
            .filter(technician_id__in=tech_ids, scheduled_date__gte=month_start,
                    scheduled_date__lte=month_end, status__in=active_statuses)
            .values('technician_id', 'scheduled_date')
            .annotate(total=Sum('duration_minutes'))
        )
        for row in rows:
            busy_by_day[row['scheduled_date']][row['technician_id']] = row['total'] or 0

    days = []
    for day_num in range(1, days_in_month + 1):
        current = date(year, month, day_num)
        working_tech_ids = [
            pk for pk in tech_ids
            if current.weekday() in tech_workdays[pk] and current not in tech_leavedates[pk]
        ]
        if not working_tech_ids:
            days.append({'date': current.isoformat(), 'status': 'closed',
                         'capacity': 0, 'tech_count': 0})
            continue

        total_capacity = 0
        for pk in working_tech_ids:
            busy = busy_by_day.get(current, {}).get(pk, 0)
            remaining = max(0, office_minutes - busy)
            total_capacity += remaining // duration

        if total_capacity <= 0:
            status = 'full'
        elif total_capacity <= 2:
            status = 'limited'
        else:
            status = 'available'

        days.append({
            'date': current.isoformat(),
            'status': status,
            'capacity': total_capacity,
            'tech_count': len(working_tech_ids),
        })

    return JsonResponse({'days': days, 'duration': duration})


def api_technician_availability(request):
    """Return technician availability info for a date."""
    tech_id = request.GET.get('technician_id')
    date_str = request.GET.get('date')
    if not tech_id or not date_str:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    try:
        tech = Technician.objects.get(pk=tech_id)
        check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (Technician.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)

    busy_slots = list(
        Appointment.objects.filter(
            technician=tech,
            scheduled_date=check_date,
            status__in=['scheduled', 'confirmed', 'in_progress'],
        ).values('start_time', 'end_time', 'duration_minutes', 'appointment_no')
    )
    # Convert time objects to string for JSON
    for s in busy_slots:
        s['start_time'] = s['start_time'].strftime('%H:%M')
        s['end_time'] = s['end_time'].strftime('%H:%M')

    return JsonResponse({
        'available': tech.is_available_on(check_date),
        'technician_name': tech.full_name,
        'busy_slots': busy_slots,
    })


# ─────────────────────────── Appointment CRUD ───────────────────────────

def appointment_list(request):
    qs = Appointment.objects.select_related(
        'equipment', 'technician', 'equipment__customer'
    ).order_by('-scheduled_date', 'start_time')

    technician_id  = request.GET.get('technician')
    customer_id    = request.GET.get('customer')
    status_filter  = request.GET.get('status')
    service_type   = request.GET.get('service_type')
    date_from      = request.GET.get('date_from')
    date_to        = request.GET.get('date_to')
    time_type      = request.GET.get('time_type')
    search         = request.GET.get('search', '')

    if technician_id:
        qs = qs.filter(technician_id=technician_id)
    if customer_id:
        qs = qs.filter(equipment__customer_id=customer_id)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if service_type:
        qs = qs.filter(service_type=service_type)
    if date_from:
        qs = qs.filter(scheduled_date__gte=date_from)
    if date_to:
        qs = qs.filter(scheduled_date__lte=date_to)
    if time_type:
        qs = qs.filter(time_type=time_type)
    if search:
        qs = qs.filter(
            Q(appointment_no__icontains=search) |
            Q(equipment__name__icontains=search) |
            Q(equipment__customer__name__icontains=search) |
            Q(technician__first_name__icontains=search) |
            Q(technician__last_name__icontains=search)
        )

    total_count = qs.count()
    paginator   = Paginator(qs, 50)
    page_obj    = paginator.get_page(request.GET.get('page', 1))

    context = {
        'appointments':         page_obj,
        'page_obj':             page_obj,
        'total_count':          total_count,
        'technicians':          Technician.objects.filter(is_active=True),
        'customers':            Customer.objects.all().order_by('name'),
        'status_choices':       Appointment.STATUS_CHOICES,
        'service_type_choices': Appointment.SERVICE_TYPE_CHOICES,
        'time_type_choices':    Appointment.TIME_TYPE_CHOICES,
        'status_colors':        STATUS_COLORS,
        'service_type_colors':  SERVICE_TYPE_COLORS,
    }
    return render(request, 'appointments/appointment_list.html', context)


def reports(request):
    today = date.today()
    date_from_str = request.GET.get('date_from', today.replace(day=1).strftime('%Y-%m-%d'))
    date_to_str   = request.GET.get('date_to',   today.strftime('%Y-%m-%d'))
    try:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        date_from = today.replace(day=1)
    try:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        date_to = today

    qs = Appointment.objects.filter(
        scheduled_date__gte=date_from,
        scheduled_date__lte=date_to,
    )

    total      = qs.count()
    completed  = qs.filter(status='completed').count()
    cancelled  = qs.filter(status='cancelled').count()
    pending    = qs.filter(status__in=['scheduled', 'confirmed']).count()
    total_mins = qs.filter(status='completed').aggregate(t=Sum('duration_minutes'))['t'] or 0

    tech_rows = list(
        qs.values('technician__id', 'technician__first_name',
                  'technician__last_name', 'technician__color')
        .annotate(
            cnt=Count('id'),
            done=Count('id', filter=Q(status='completed')),
            mins=Sum('duration_minutes', filter=Q(status='completed')),
        )
        .order_by('-done')
    )
    for r in tech_rows:
        r['name'] = f"{r['technician__first_name']} {r['technician__last_name']}"
        r['hours'] = round((r['mins'] or 0) / 60, 1)

    svc_rows = list(
        qs.values('service_type')
        .annotate(cnt=Count('id'), done=Count('id', filter=Q(status='completed')))
        .order_by('-cnt')
    )
    svc_labels = dict(Appointment.SERVICE_TYPE_CHOICES)
    for r in svc_rows:
        r['label'] = svc_labels.get(r['service_type'], r['service_type'])
    svc_max = max((r['cnt'] for r in svc_rows), default=1)

    cust_rows = list(
        qs.values('equipment__customer__name', 'equipment__customer__code')
        .annotate(cnt=Count('id'), done=Count('id', filter=Q(status='completed')))
        .order_by('-cnt')[:10]
    )
    cust_max = max((r['cnt'] for r in cust_rows), default=1)

    # Preset date ranges
    import calendar as _cal
    last_day = _cal.monthrange(today.year, today.month)[1]
    prev_month_end = today.replace(day=1) - timedelta(days=1)
    presets = {
        'this_month': (today.replace(day=1).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
        'last_month': (prev_month_end.replace(day=1).strftime('%Y-%m-%d'), prev_month_end.strftime('%Y-%m-%d')),
        'last_90':    ((today - timedelta(days=90)).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
        'this_year':  (today.replace(month=1, day=1).strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')),
    }

    return render(request, 'appointments/reports.html', {
        'date_from':   date_from,
        'date_to':     date_to,
        'total':       total,
        'completed':   completed,
        'cancelled':   cancelled,
        'pending':     pending,
        'total_hours': round(total_mins / 60, 1),
        'tech_rows':   tech_rows,
        'svc_rows':    svc_rows,
        'svc_max':     svc_max,
        'cust_rows':   cust_rows,
        'cust_max':    cust_max,
        'presets':     presets,
    })


def appointment_detail(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related(
            'equipment', 'technician', 'equipment__customer', 'equipment__category',
            'assigned_to',
        ), pk=pk
    )
    technicians = Technician.objects.filter(is_active=True).order_by('first_name')

    STEPS = [
        ('confirmed',    'รับเครื่อง',    'box-arrow-in-down'),
        ('in_progress',  'ดำเนินการ',     'tools'),
        ('completed',    'เสร็จสิ้น',     'patch-check'),
    ]
    STATUS_ORDER = ['scheduled', 'confirmed', 'in_progress', 'completed']
    current_idx = STATUS_ORDER.index(appointment.status) if appointment.status in STATUS_ORDER else 0
    completed_steps = set(STATUS_ORDER[:current_idx + 1])

    context = {
        'appointment': appointment,
        'technicians': technicians,
        'steps': STEPS,
        'completed_steps': completed_steps,
        'status_colors': STATUS_COLORS,
        'service_type_colors': SERVICE_TYPE_COLORS,
    }
    return render(request, 'appointments/appointment_detail.html', context)


@require_POST
def appointment_receive(request, pk):
    apt = get_object_or_404(Appointment, pk=pk)
    apt.equipment_received = not apt.equipment_received
    if apt.equipment_received:
        apt.equipment_received_at = timezone.now()
        if apt.status == 'scheduled':
            apt.status = 'confirmed'
    else:
        apt.equipment_received_at = None
    apt.save()
    messages.success(request, 'อัพเดทสถานะการรับเครื่องแล้ว')
    return redirect('appointments:appointment_detail', pk=pk)


@require_POST
def appointment_assign(request, pk):
    apt = get_object_or_404(Appointment, pk=pk)
    tech_id = request.POST.get('assigned_to')
    if tech_id:
        apt.assigned_to_id = int(tech_id)
        if apt.status in ('scheduled', 'confirmed'):
            apt.status = 'in_progress'
        apt.save()
        messages.success(request, 'มอบหมายงานเรียบร้อยแล้ว')
    return redirect('appointments:appointment_detail', pk=pk)


@require_POST
def appointment_complete_action(request, pk):
    apt = get_object_or_404(Appointment, pk=pk)
    date_str = request.POST.get('actual_completion_date', '').strip()
    notes = request.POST.get('completion_notes', '').strip()
    try:
        from datetime import datetime as _dt
        completion_date = _dt.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        completion_date = date.today()
    apt.mark_completed(completion_date, notes)
    equip = apt.equipment
    next_parts = []
    if equip.next_maintenance_date:
        next_parts.append(f'PM ถัดไป {equip.next_maintenance_date.strftime("%d/%m/%Y")}')
    if equip.next_calibration_date:
        next_parts.append(f'Cal ถัดไป {equip.next_calibration_date.strftime("%d/%m/%Y")}')
    suffix = ' | '.join(next_parts)
    messages.success(request, f'บันทึกผลงานเรียบร้อย! {suffix}' if suffix else 'บันทึกผลงานเรียบร้อย!')
    return redirect('appointments:appointment_detail', pk=pk)


def appointment_create(request):
    equipment_id  = request.GET.get('equipment_id')
    technician_id = request.GET.get('technician')
    date_str      = request.GET.get('date')
    initial = {}

    if equipment_id:
        try:
            equip = Equipment.objects.get(pk=equipment_id)
            initial['equipment'] = equip
            initial['service_type'] = 'PM_CAL' if equip.requires_calibration else 'PM'
            initial['duration_minutes'] = equip.total_service_duration_minutes
        except Equipment.DoesNotExist:
            pass

    if technician_id:
        try:
            initial['technician'] = Technician.objects.get(pk=technician_id)
        except Technician.DoesNotExist:
            pass

    if date_str:
        try:
            initial['scheduled_date'] = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            apt = form.save()
            messages.success(request, f'สร้างนัดหมาย {apt.appointment_no} เรียบร้อยแล้ว')
            return redirect('appointments:appointment_detail', pk=apt.pk)
    else:
        form = AppointmentForm(initial=initial)

    technicians = list(
        Technician.objects.filter(is_active=True).prefetch_related('work_days')
    )
    context = {
        'form': form,
        'technicians': technicians,
        'technicians_json': json.dumps([
            {
                'id': t.pk,
                'name': t.full_name,
                'color': t.color,
                'work_days': list(t.work_days.values_list('day_of_week', flat=True)),
            }
            for t in technicians
        ]),
    }
    return render(request, 'appointments/appointment_form.html', context)


def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            messages.success(request, 'อัปเดตนัดหมายเรียบร้อยแล้ว')
            return redirect('appointments:appointment_detail', pk=appointment.pk)
    else:
        form = AppointmentForm(instance=appointment)

    technicians = list(
        Technician.objects.filter(is_active=True).prefetch_related('work_days')
    )
    context = {
        'form': form,
        'appointment': appointment,
        'technicians': technicians,
        'technicians_json': json.dumps([
            {
                'id': t.pk,
                'name': t.full_name,
                'color': t.color,
                'work_days': list(t.work_days.values_list('day_of_week', flat=True)),
            }
            for t in technicians
        ]),
    }
    return render(request, 'appointments/appointment_form.html', context)


@require_POST
def appointment_delete(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    no = appointment.appointment_no
    appointment.delete()
    messages.success(request, f'ลบนัดหมาย {no} เรียบร้อยแล้ว')
    return redirect('appointments:appointment_list')


# ─────────────────────────── Equipment CRUD ───────────────────────────

def equipment_list(request):
    today = date.today()
    thirty_days_later = today + timedelta(days=30)
    filter_type = request.GET.get('filter', 'all')
    search = request.GET.get('search', '')
    customer_id = request.GET.get('customer')

    qs = Equipment.objects.filter(is_active=True).select_related('customer', 'category')

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(serial_number__icontains=search) |
            Q(asset_number__icontains=search) |
            Q(customer__name__icontains=search)
        )
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    if filter_type == 'overdue':
        qs = qs.filter(
            Q(next_maintenance_date__lt=today) |
            Q(requires_calibration=True, next_calibration_date__lt=today)
        )
    elif filter_type == 'due_soon':
        qs = qs.filter(
            Q(next_maintenance_date__gte=today, next_maintenance_date__lte=thirty_days_later) |
            Q(requires_calibration=True,
              next_calibration_date__gte=today,
              next_calibration_date__lte=thirty_days_later)
        )
    elif filter_type == 'calibration':
        qs = qs.filter(requires_calibration=True)

    # summary counts (not affected by current filter)
    base = Equipment.objects.filter(is_active=True)
    overdue_count = base.filter(
        Q(next_maintenance_date__lt=today) |
        Q(requires_calibration=True, next_calibration_date__lt=today)
    ).count()
    due_soon_count = base.filter(
        Q(next_maintenance_date__gte=today, next_maintenance_date__lte=thirty_days_later) |
        Q(requires_calibration=True,
          next_calibration_date__gte=today,
          next_calibration_date__lte=thirty_days_later)
    ).count()

    context = {
        'equipment_list': qs.order_by('next_maintenance_date'),
        'filter_type': filter_type,
        'search': search,
        'customers': Customer.objects.all(),
        'overdue_count': overdue_count,
        'due_soon_count': due_soon_count,
        'today': today,
    }
    return render(request, 'appointments/equipment_list.html', context)


def equipment_detail(request, pk):
    equipment = get_object_or_404(
        Equipment.objects.select_related('customer', 'category'), pk=pk)
    appointments = (equipment.appointments
                    .select_related('technician')
                    .order_by('-scheduled_date')[:15])
    context = {
        'equipment': equipment,
        'appointments': appointments,
        'today': date.today(),
        'status_colors': STATUS_COLORS,
        'service_type_colors': SERVICE_TYPE_COLORS,
    }
    return render(request, 'appointments/equipment_detail.html', context)


def equipment_create(request):
    if request.method == 'POST':
        form = EquipmentForm(request.POST)
        if form.is_valid():
            selected_skill_id = request.POST.get('selected_skill_id')
            selected_skill = None
            if selected_skill_id:
                try:
                    selected_skill = Skill.objects.get(pk=int(selected_skill_id))
                except (Skill.DoesNotExist, ValueError):
                    selected_skill = None
            else:
                # fall back: check name matches a skill
                posted_name = request.POST.get('name', '').strip()
                if posted_name:
                    try:
                        selected_skill = Skill.objects.get(name=posted_name)
                    except Skill.DoesNotExist:
                        selected_skill = None

            if not selected_skill:
                form.add_error('name', 'ชื่อเครื่องต้องเลือกจากรายการทักษะ (โปรดเลือกหนึ่งรายการ)')
            else:
                # ensure the equipment.name is the skill name
                # set hidden name in cleaned_data so form.save() persists correct name
                form.cleaned_data['name'] = selected_skill.name
                equip = form.save()
                equip.repair_required_skills.set([selected_skill])
                messages.success(request, f'เพิ่มเครื่องมือ "{equip.name}" เรียบร้อยแล้ว')
                return redirect('appointments:equipment_detail', pk=equip.pk)
    else:
        form = EquipmentForm()
    return render(request, 'appointments/equipment_form.html', {'form': form})


def equipment_update(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, instance=equipment)
        if form.is_valid():
            selected_skill_id = request.POST.get('selected_skill_id')
            selected_skill = None
            if selected_skill_id:
                try:
                    selected_skill = Skill.objects.get(pk=int(selected_skill_id))
                except (Skill.DoesNotExist, ValueError):
                    selected_skill = None
            else:
                posted_name = request.POST.get('name', '').strip()
                if posted_name:
                    try:
                        selected_skill = Skill.objects.get(name=posted_name)
                    except Skill.DoesNotExist:
                        selected_skill = None

            if not selected_skill:
                form.add_error('name', 'ชื่อเครื่องต้องเลือกจากรายการทักษะ (โปรดเลือกหนึ่งรายการ)')
            else:
                form.cleaned_data['name'] = selected_skill.name
                equip = form.save()
                equip.repair_required_skills.set([selected_skill])
                messages.success(request, 'อัปเดตข้อมูลเครื่องมือเรียบร้อยแล้ว')
                return redirect('appointments:equipment_detail', pk=equipment.pk)
    else:
        form = EquipmentForm(instance=equipment)
    return render(request, 'appointments/equipment_form.html',
                  {'form': form, 'equipment': equipment})


@require_POST
def equipment_delete(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    appointment_count = equipment.appointments.count()
    if appointment_count:
        messages.error(
            request,
            f'ไม่สามารถลบทะเบียนได้ เนื่องจากมีนัดหมาย {appointment_count} รายการผูกอยู่',
        )
        return redirect('appointments:equipment_detail', pk=equipment.pk)

    equipment.delete()
    messages.success(request, 'ลบทะเบียนเครื่องมือเรียบร้อยแล้ว')
    return redirect('appointments:equipment_list')


# ─────────────────────────── Equipment Import ───────────────────────────

_IMPORT_COLUMNS = [
    ('equipment_code',               'รหัสเครื่อง'),
    ('serial_number',                'SerialNo *'),
    ('asset_number',                 'เลขครุภัณฑ์'),
    ('name',                         'ชื่อเครื่อง *'),
    ('name_th',                      'ชื่อเครื่องภาษาไทย'),
    ('model',                        'รุ่น'),
    ('manufacturer',                 'ยี่ห้อ'),
    ('customer_code',                'รหัสลูกค้า *'),
    ('owner_unit_name',              'ชื่อหน่วยงานเจ้าของ'),
    ('user_unit_name',               'ชื่อหน่วยงานที่ใช้'),
    ('department',                   'ภาควิชา/ฝ่าย/งาน'),
    ('maintenance_duration_minutes', 'เวลา PM (นาที)'),
    ('maintenance_interval_months',  'รอบ PM (เดือน)'),
    ('last_maintenance_date',        'PM ล่าสุด (YYYY-MM-DD)'),
    ('next_maintenance_date',        'PM ถัดไป (YYYY-MM-DD)'),
    ('requires_calibration',         'ต้องสอบเทียบ (1/0)'),
    ('calibration_duration_minutes', 'เวลาสอบเทียบ (นาที)'),
    ('calibration_interval_months',  'รอบสอบเทียบ (เดือน)'),
    ('last_calibration_date',        'สอบเทียบล่าสุด (YYYY-MM-DD)'),
    ('next_calibration_date',        'สอบเทียบถัดไป (YYYY-MM-DD)'),
    ('is_active',                    'ใช้งาน (1/0)'),
]


def equipment_import_template(request):
    """Download a pre-filled Excel template for equipment bulk import."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Equipment'

    header_fill = PatternFill('solid', fgColor='1F4E79')
    header_font = Font(bold=True, color='FFFFFF')
    req_fill   = PatternFill('solid', fgColor='C00000')  # red = required

    for col_idx, (field, label) in enumerate(_IMPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.font   = header_font
        cell.fill   = req_fill if label.endswith('*') else header_fill
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(label) + 4, 18)

    # Sample row
    sample = [
        'EQ-0001', 'SN-00001', 'AST-0001', 'Defibrillator', 'เครื่องกระตุ้นหัวใจ',
        'X-200', 'Zoll', 'CUST001', 'ICU', 'ICU Ward', 'อายุรกรรม',
        120, 6, '', '', 0, '', '', '', '', 1,
    ]
    ws.append(sample)

    # Instructions sheet
    ws2 = wb.create_sheet('คำแนะนำ')
    notes = [
        ('คอลัมน์', 'คำอธิบาย'),
        ('SerialNo *',             'จำเป็น – ต้องไม่ซ้ำในระบบ'),
        ('ชื่อเครื่อง *',         'จำเป็น'),
        ('รหัสลูกค้า *',          'จำเป็น – ต้องมีอยู่ในตาราง Customer ก่อน'),
        ('ต้องสอบเทียบ (1/0)',    '1 = ต้องสอบเทียบ, 0 = ไม่ต้อง'),
        ('ใช้งาน (1/0)',           '1 = ใช้งาน (default), 0 = ปิดใช้งาน'),
        ('วันที่',                 'รูปแบบ YYYY-MM-DD เช่น 2025-06-30'),
        ('หมายเหตุ',               'หาก serial_number ซ้ำ ระบบจะอัปเดตแถวนั้น'),
    ]
    for r in notes:
        ws2.append(r)
    ws2.column_dimensions['A'].width = 28
    ws2.column_dimensions['B'].width = 50

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="equipment_import_template.xlsx"'
    return response


def equipment_import(request):
    if request.method != 'POST':
        return render(request, 'appointments/equipment_import.html')

    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        messages.error(request, 'กรุณาเลือกไฟล์ Excel')
        return render(request, 'appointments/equipment_import.html')

    try:
        wb = openpyxl.load_workbook(excel_file, data_only=True)
    except Exception:
        messages.error(request, 'ไม่สามารถอ่านไฟล์ Excel ได้ กรุณาใช้ไฟล์ .xlsx')
        return render(request, 'appointments/equipment_import.html')

    ws = wb.active
    headers = [str(c.value).strip() if c.value is not None else '' for c in ws[1]]
    field_map = {label.rstrip(' *'): field for field, label in _IMPORT_COLUMNS}
    col_index = {}  # field_name -> 0-based column index
    for i, h in enumerate(headers):
        key = h.rstrip(' *')
        if key in field_map:
            col_index[field_map[key]] = i

    required = ['serial_number', 'name', 'customer_code']
    missing_headers = [f for f in required if f not in col_index]
    if missing_headers:
        messages.error(request, f'ไม่พบคอลัมน์ที่จำเป็น: {missing_headers}. กรุณาใช้ template ที่ดาวน์โหลด')
        return render(request, 'appointments/equipment_import.html')

    def cell_val(row, field):
        idx = col_index.get(field)
        if idx is None:
            return None
        v = row[idx].value
        return v

    def to_str(v, default=''):
        return str(v).strip() if v is not None else default

    def to_int(v, default=None):
        try:
            return int(v) if v is not None and str(v).strip() != '' else default
        except (ValueError, TypeError):
            return default

    def to_bool(v, default=False):
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        return str(v).strip() in ('1', 'true', 'True', 'yes', 'Yes', 'ใช่')

    def to_date(v):
        if v is None or str(v).strip() == '':
            return None
        if isinstance(v, (date, datetime)):
            return v.date() if isinstance(v, datetime) else v
        try:
            return datetime.strptime(str(v).strip(), '%Y-%m-%d').date()
        except ValueError:
            return None

    created = updated = skipped = 0
    row_errors = []

    for row_num, row in enumerate(ws.iter_rows(min_row=2), start=2):
        # skip fully-empty rows
        if all(c.value is None for c in row):
            continue

        serial = to_str(cell_val(row, 'serial_number'))
        name   = to_str(cell_val(row, 'name'))
        cust_code = to_str(cell_val(row, 'customer_code'))

        errors = []
        if not serial:
            errors.append('ไม่มี SerialNo')
        if not name:
            errors.append('ไม่มีชื่อเครื่อง')
        if not cust_code:
            errors.append('ไม่มีรหัสลูกค้า')

        if errors:
            row_errors.append({'row': row_num, 'serial': serial or '-', 'errors': errors})
            skipped += 1
            continue

        try:
            customer = Customer.objects.get(code=cust_code)
        except Customer.DoesNotExist:
            row_errors.append({'row': row_num, 'serial': serial, 'errors': [f'ไม่พบลูกค้ารหัส "{cust_code}"']})
            skipped += 1
            continue

        defaults = dict(
            name=name,
            equipment_code=to_str(cell_val(row, 'equipment_code')),
            asset_number=to_str(cell_val(row, 'asset_number')),
            name_th=to_str(cell_val(row, 'name_th')),
            model=to_str(cell_val(row, 'model')),
            manufacturer=to_str(cell_val(row, 'manufacturer')),
            customer=customer,
            owner_unit_name=to_str(cell_val(row, 'owner_unit_name')),
            user_unit_name=to_str(cell_val(row, 'user_unit_name')),
            department=to_str(cell_val(row, 'department')),
            maintenance_duration_minutes=to_int(cell_val(row, 'maintenance_duration_minutes'), 120),
            maintenance_interval_months=to_int(cell_val(row, 'maintenance_interval_months'), 12),
            last_maintenance_date=to_date(cell_val(row, 'last_maintenance_date')),
            next_maintenance_date=to_date(cell_val(row, 'next_maintenance_date')),
            requires_calibration=to_bool(cell_val(row, 'requires_calibration')),
            calibration_duration_minutes=to_int(cell_val(row, 'calibration_duration_minutes')),
            calibration_interval_months=to_int(cell_val(row, 'calibration_interval_months')),
            last_calibration_date=to_date(cell_val(row, 'last_calibration_date')),
            next_calibration_date=to_date(cell_val(row, 'next_calibration_date')),
            is_active=to_bool(cell_val(row, 'is_active'), default=True),
        )

        obj, was_created = Equipment.objects.update_or_create(
            serial_number=serial,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    context = {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'row_errors': row_errors,
    }
    return render(request, 'appointments/equipment_import.html', context)


# ─────────────────────────── Technician CRUD ───────────────────────────

def technician_list(request):
    today = date.today()
    technicians = (Technician.objects
                   .filter(is_active=True)
                   .prefetch_related('skills', 'work_days'))
    for tech in technicians:
        tech.available_today = tech.is_available_on(today)
        tech.today_count = tech.appointments.filter(scheduled_date=today).count()
    context = {'technicians': technicians, 'today': today}
    return render(request, 'appointments/technician_list.html', context)


def technician_detail(request, pk):
    technician = get_object_or_404(Technician, pk=pk)
    today = date.today()

    upcoming = (technician.appointments
                .filter(scheduled_date__gte=today,
                        status__in=['scheduled', 'confirmed'])
                .select_related('equipment', 'equipment__customer')
                .order_by('scheduled_date', 'start_time')[:20])

    leaves       = technician.leaves.filter(leave_date__gte=today).order_by('leave_date')[:10]
    overtime_days = technician.overtime_days.filter(date__gte=today).order_by('date')[:20]

    context = {
        'technician':    technician,
        'upcoming':      upcoming,
        'leaves':        leaves,
        'overtime_days': overtime_days,
        'leave_form':    TechnicianLeaveForm(initial={'technician': technician}),
        'ot_form':       TechnicianOvertimeDayForm(),
        'today':         today,
        'status_colors': STATUS_COLORS,
    }
    return render(request, 'appointments/technician_detail.html', context)


def technician_add_leave(request, pk):
    technician = get_object_or_404(Technician, pk=pk)
    if request.method == 'POST':
        form = TechnicianLeaveForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'บันทึกการลาเรียบร้อยแล้ว')
    return redirect('appointments:technician_detail', pk=pk)


@require_POST
def technician_add_overtime(request, pk):
    technician = get_object_or_404(Technician, pk=pk)
    form = TechnicianOvertimeDayForm(request.POST)
    if form.is_valid():
        ot_date = form.cleaned_data['date']
        _, created = TechnicianOvertimeDay.objects.get_or_create(
            technician=technician, date=ot_date
        )
        dow = ot_date.weekday()
        label = 'นอกเวลา 16:30-20:30' if dow <= 4 else 'เสาร์/อาทิตย์ 08:30-16:30'
        if created:
            messages.success(request, f'เพิ่มวันนอกเวลา {ot_date.strftime("%d/%m/%Y")} ({label}) เรียบร้อยแล้ว')
        else:
            messages.info(request, f'วัน {ot_date.strftime("%d/%m/%Y")} มีอยู่แล้ว')
    else:
        messages.error(request, 'วันที่ไม่ถูกต้อง')
    return redirect('appointments:technician_detail', pk=pk)


@require_POST
def technician_remove_overtime(request, pk, ot_pk):
    ot_day = get_object_or_404(TechnicianOvertimeDay, pk=ot_pk, technician_id=pk)
    ot_day.delete()
    messages.success(request, 'ลบวันนอกเวลาเรียบร้อยแล้ว')
    return redirect('appointments:technician_detail', pk=pk)


def technician_create(request):
    if request.method == 'POST':
        form = TechnicianForm(request.POST)
        if form.is_valid():
            tech = form.save()
            messages.success(request, f'เพิ่มช่าง {tech.full_name} เรียบร้อยแล้ว')
            return redirect('appointments:technician_detail', pk=tech.pk)
    else:
        form = TechnicianForm()
    return render(request, 'appointments/technician_form.html', {'form': form})


def technician_update(request, pk):
    technician = get_object_or_404(Technician, pk=pk)
    if request.method == 'POST':
        form = TechnicianForm(request.POST, instance=technician)
        if form.is_valid():
            form.save()
            messages.success(request, 'อัปเดตข้อมูลช่างเรียบร้อยแล้ว')
            return redirect('appointments:technician_detail', pk=technician.pk)
    else:
        form = TechnicianForm(instance=technician)
    return render(request, 'appointments/technician_form.html',
                  {'form': form, 'technician': technician})


def technician_skill(request):
    """Skill-demand dashboard based on registered equipment PM/CAL needs."""
    today = date.today()
    try:
        horizon_days = int(request.GET.get('days', 30))
    except (TypeError, ValueError):
        horizon_days = 30
    horizon_days = max(7, min(horizon_days, 180))
    horizon_date = today + timedelta(days=horizon_days)

    technicians = list(
        Technician.objects.filter(is_active=True)
        .prefetch_related('skills')
        .order_by('employee_id')
    )
    tech_skill_ids = {
        tech.pk: set(tech.skills.values_list('pk', flat=True))
        for tech in technicians
    }

    equipment_qs = (
        Equipment.objects.filter(is_active=True)
        .select_related('customer', 'category')
        .prefetch_related(
            'maintenance_required_skills',
            'calibration_required_skills',
            'required_skills',
            'category__required_skills',
        )
        .order_by('name')
    )

    demand_by_skill = {}
    required_skill_ids = set()
    unclassified_equipment = []

    for equip in equipment_qs:
        pm_skill_map = {s.pk: s for s in equip.maintenance_required_skills.all()}
        cal_skill_map = {s.pk: s for s in equip.calibration_required_skills.all()}

        # Backward compatibility for old data that used a single required_skills field.
        if not pm_skill_map and not cal_skill_map:
            for s in equip.required_skills.all():
                pm_skill_map.setdefault(s.pk, s)
                if equip.requires_calibration:
                    cal_skill_map.setdefault(s.pk, s)

        if equip.category_id:
            for s in equip.category.required_skills.all():
                pm_skill_map.setdefault(s.pk, s)
                if equip.requires_calibration:
                    cal_skill_map.setdefault(s.pk, s)

        if not pm_skill_map and (not equip.requires_calibration or not cal_skill_map):
            unclassified_equipment.append(equip)
            continue

        pm_due = bool(equip.next_maintenance_date and equip.next_maintenance_date <= horizon_date)
        pm_overdue = bool(equip.next_maintenance_date and equip.next_maintenance_date < today)
        cal_due = bool(
            equip.requires_calibration and equip.next_calibration_date
            and equip.next_calibration_date <= horizon_date
        )
        cal_overdue = bool(
            equip.requires_calibration and equip.next_calibration_date
            and equip.next_calibration_date < today
        )

        all_skill_ids = set(pm_skill_map.keys()) | set(cal_skill_map.keys())
        for skill_id in all_skill_ids:
            skill = pm_skill_map.get(skill_id) or cal_skill_map.get(skill_id)
            required_skill_ids.add(skill_id)
            bucket = demand_by_skill.setdefault(skill_id, {
                'skill': skill,
                'equipment_count': 0,
                'pm_due_count': 0,
                'pm_overdue_count': 0,
                'cal_due_count': 0,
                'cal_overdue_count': 0,
                'samples': [],
            })
            bucket['equipment_count'] += 1
            if pm_due and skill_id in pm_skill_map:
                bucket['pm_due_count'] += 1
            if pm_overdue and skill_id in pm_skill_map:
                bucket['pm_overdue_count'] += 1
            if cal_due and skill_id in cal_skill_map:
                bucket['cal_due_count'] += 1
            if cal_overdue and skill_id in cal_skill_map:
                bucket['cal_overdue_count'] += 1
            if len(bucket['samples']) < 4:
                bucket['samples'].append(f"{equip.name} ({equip.serial_number})")

    skill_rows = []
    skills_by_id = {}
    for skill_id, data in demand_by_skill.items():
        due_total = data['pm_due_count'] + data['cal_due_count']
        overdue_total = data['pm_overdue_count'] + data['cal_overdue_count']
        tech_with_skill = [t for t in technicians if skill_id in tech_skill_ids[t.pk]]
        tech_count = len(tech_with_skill)

        if due_total > 0 and tech_count == 0:
            coverage_status = 'critical'
        elif due_total >= 3 and tech_count == 1:
            coverage_status = 'warning'
        else:
            coverage_status = 'covered'

        row = {
            **data,
            'id': skill_id,
            'due_total': due_total,
            'overdue_total': overdue_total,
            'technician_count': tech_count,
            'technicians': tech_with_skill,
            'coverage_status': coverage_status,
        }
        skill_rows.append(row)
        skills_by_id[skill_id] = data['skill']

    skill_rows.sort(
        key=lambda r: (
            -r['overdue_total'],
            -r['due_total'],
            r['technician_count'],
            r['skill'].name.lower(),
        )
    )

    required_skills = [row['skill'] for row in skill_rows]
    priority_missing_by_tech = defaultdict(list)
    for row in skill_rows:
        if row['due_total'] == 0:
            continue
        for tech in technicians:
            if row['id'] not in tech_skill_ids[tech.pk]:
                priority_missing_by_tech[tech.pk].append(row['skill'])

    technician_rows = []
    total_required = len(required_skill_ids)
    for tech in technicians:
        owned = tech_skill_ids[tech.pk]
        matched_count = len(owned & required_skill_ids)
        coverage_pct = round((matched_count / total_required) * 100) if total_required else 100
        missing_ids = required_skill_ids - owned
        missing_names = [skills_by_id[sid].name for sid in missing_ids if sid in skills_by_id]
        technician_rows.append({
            'technician': tech,
            'coverage_pct': coverage_pct,
            'matched_count': matched_count,
            'missing_names': sorted(missing_names),
            'priority_missing': priority_missing_by_tech.get(tech.pk, [])[:3],
            'owned_skill_ids': owned,
        })

    context = {
        'today': today,
        'horizon_days': horizon_days,
        'horizon_date': horizon_date,
        'skill_rows': skill_rows,
        'required_skills': required_skills,
        'technician_rows': technician_rows,
        'total_required_skills': len(required_skills),
        'equipment_total': equipment_qs.count(),
        'unclassified_equipment': unclassified_equipment[:15],
        'unclassified_count': len(unclassified_equipment),
        'critical_gap_count': sum(1 for row in skill_rows if row['coverage_status'] == 'critical'),
    }
    return render(request, 'appointments/technician_skill.html', context)


# ─────────────────────────── Customer CRUD ───────────────────────────

def _build_customer_tree(by_parent, parent_id=None, level=0):
    rows = []
    for c in by_parent.get(parent_id, []):
        has_children = bool(by_parent.get(c.pk))
        rows.append({
            'customer': c,
            'level': level,
            'indent': level * 20,
            'has_children': has_children,
            'parent_id': c.parent_id,
        })
        rows.extend(_build_customer_tree(by_parent, c.pk, level + 1))
    return rows


def customer_list(request):
    all_customers = Customer.objects.all().order_by('code')
    by_parent = defaultdict(list)
    for c in all_customers:
        by_parent[c.parent_id].append(c)
    rows = _build_customer_tree(by_parent)
    return render(request, 'appointments/customer_list.html', {'rows': rows})


def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            c = form.save()
            messages.success(request, f'เพิ่มลูกค้า "{c.name}" เรียบร้อยแล้ว')
            return redirect('appointments:customer_list')
    else:
        form = CustomerForm()
    return render(request, 'appointments/customer_form.html', {'form': form, 'title': 'เพิ่มลูกค้า / โรงพยาบาล'})


def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, f'แก้ไขลูกค้า "{customer.name}" เรียบร้อยแล้ว')
            return redirect('appointments:customer_detail', pk=pk)
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'appointments/customer_form.html', {'form': form, 'title': f'แก้ไข: {customer.name}', 'customer': customer})


def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    contacts = customer.contacts.all()
    equipment_qs = (
        customer.equipment
        .filter(is_active=True)
        .select_related('category')
        .order_by('name')
    )
    recent_appointments = (
        Appointment.objects
        .filter(equipment__customer=customer)
        .select_related('equipment', 'technician')
        .order_by('-scheduled_date', '-start_time')[:10]
    )
    today = date.today()
    equip_list = list(equipment_qs)
    stats = {
        'equipment_total': len(equip_list),
        'equipment_overdue': sum(1 for e in equip_list if e.maintenance_status == 'overdue'),
        'equipment_due_soon': sum(1 for e in equip_list if e.maintenance_status == 'due_soon'),
        'appointments_pending': Appointment.objects.filter(
            equipment__customer=customer,
            scheduled_date__gte=today,
            status__in=['scheduled', 'confirmed'],
        ).count(),
    }
    contact_form = CustomerContactForm()
    return render(request, 'appointments/customer_detail.html', {
        'customer': customer,
        'contacts': contacts,
        'equipment': equip_list,
        'recent_appointments': recent_appointments,
        'stats': stats,
        'contact_form': contact_form,
    })


def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    equipment_count = customer.equipment.count()
    if request.method == 'POST':
        if equipment_count > 0:
            messages.error(request, f'ไม่สามารถลบได้ มีเครื่องมือ {equipment_count} รายการผูกอยู่')
            return redirect('appointments:customer_detail', pk=pk)
        name = customer.name
        customer.delete()
        messages.success(request, f'ลบลูกค้า "{name}" เรียบร้อยแล้ว')
        return redirect('appointments:customer_list')
    return render(request, 'appointments/customer_delete.html', {
        'customer': customer,
        'equipment_count': equipment_count,
    })


@require_POST
def customer_contact_add(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerContactForm(request.POST)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.customer = customer
        contact.save()
        messages.success(request, 'เพิ่มผู้ติดต่อเรียบร้อยแล้ว')
    else:
        messages.error(request, 'ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง')
    return redirect('appointments:customer_detail', pk=pk)


@require_POST
def customer_contact_delete(request, pk, contact_pk):
    contact = get_object_or_404(CustomerContact, pk=contact_pk, customer_id=pk)
    contact.delete()
    messages.success(request, 'ลบผู้ติดต่อเรียบร้อยแล้ว')
    return redirect('appointments:customer_detail', pk=pk)
