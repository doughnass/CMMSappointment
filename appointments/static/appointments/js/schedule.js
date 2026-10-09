(function () {
  const calEl = document.getElementById('calendar');
  const eventsUrl = calEl.dataset.eventsUrl;
  const overtimeToggle = document.getElementById('toggle-overtime');
  let selectedTech = 'all';

  function setState({ loading, error, empty }) {
    document.getElementById('calendar-loading').classList.toggle('show', !!loading);
    if (error !== undefined) {
      const el = document.getElementById('calendar-error');
      el.classList.toggle('d-none', !error);
      el.classList.toggle('d-flex', !!error);
    }
    if (empty !== undefined || error) {
      document.getElementById('calendar-empty').classList.toggle('d-none', !empty);
    }
  }

  // ── Calendar init ──
  const calendar = new FullCalendar.Calendar(calEl, {
    locale: 'th',
    initialView: 'timeGridWeek',
    height: 'auto',
    slotMinTime: '06:00',
    slotMaxTime: '22:00',
    slotDuration: '00:30',
    slotLabelInterval: '01:00',
    slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
    eventTimeFormat:  { hour: '2-digit', minute: '2-digit', hour12: false },
    allDaySlot: false,
    nowIndicator: true,
    weekNumbers: false,
    businessHours: {
      daysOfWeek: [1, 2, 3, 4, 5],
      startTime: '08:30',
      endTime: '16:30',
    },
    headerToolbar: {
      left:   'prev,next today',
      center: 'title',
      right:  'dayGridMonth,timeGridWeek,timeGridDay',
    },
    buttonText: {
      today: 'วันนี้',
      month: 'เดือน',
      week:  'สัปดาห์',
      day:   'วัน',
    },
    events: function (info, successCb, failureCb) {
      const params = new URLSearchParams({
        start: info.startStr,
        end:   info.endStr,
        technician: selectedTech,
        include_overtime: overtimeToggle.checked ? '1' : '0',
      });
      setState({ loading: true, error: false });
      fetch(`${eventsUrl}?${params}`)
        .then(r => {
          if (!r.ok) throw new Error(r.status);
          return r.json();
        })
        .then(events => {
          setState({ loading: false, empty: events.length === 0 });
          successCb(events);
        })
        .catch(err => {
          setState({ loading: false, error: true });
          failureCb(err);
        });
    },
    eventClick: function (info) {
      showEventModal(info.event);
    },
    eventDidMount: function (info) {
      // Dashed border for overtime
      if (info.event.extendedProps.is_overtime) {
        info.el.style.borderStyle = 'dashed';
        info.el.style.borderWidth = '2px';
      }
    },
  });
  calendar.render();

  // ── Tech filter buttons ──
  document.querySelectorAll('.tech-badge').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tech-badge').forEach(b => {
        b.classList.remove('fw-bold');
        b.setAttribute('aria-pressed', 'false');
      });
      this.classList.add('fw-bold');
      this.setAttribute('aria-pressed', 'true');
      selectedTech = this.dataset.tech;
      calendar.refetchEvents();
    });
  });

  // ── Overtime toggle ──
  overtimeToggle.addEventListener('change', function () {
    calendar.refetchEvents();
  });

  document.getElementById('calendar-retry').addEventListener('click', function () {
    calendar.refetchEvents();
  });

  // ── Event modal ──
  function showEventModal(event) {
    const p = event.extendedProps;
    document.getElementById('modal-title').textContent =
      `${p.appointment_no} – ${p.service_type}`;
    const header = document.getElementById('modal-header');
    header.style.borderLeftColor = event.backgroundColor;
    header.style.borderLeftWidth = '4px';
    header.style.borderLeftStyle = 'solid';

    const rows = [
      ['เครื่องมือ',   p.equipment],
      ['Serial No.',   p.serial_number],
      ['โรงพยาบาล',   p.customer],
      ['แผนก',        p.department || '–'],
      ['ช่าง',         p.technician],
      ['ประเภทงาน',   p.service_type],
      ['ช่วงเวลา',    p.time_type, p.is_overtime ? 'badge-overtime' : 'badge-office'],
      ['ระยะเวลา',    `${p.duration} นาที`],
      ['สถานะ',       p.status],
      ['หมายเหตุ',    p.notes || '–'],
    ];
    const dl = document.getElementById('modal-body-dl');
    dl.replaceChildren();
    rows.forEach(([label, value, badgeClass]) => {
      const dt = document.createElement('dt');
      dt.className = 'col-5';
      dt.textContent = label;
      const dd = document.createElement('dd');
      dd.className = 'col-7 mb-1';
      if (badgeClass) {
        const badge = document.createElement('span');
        badge.className = `badge ${badgeClass}`;
        badge.textContent = value;
        dd.appendChild(badge);
      } else {
        dd.textContent = value;
      }
      dl.append(dt, dd);
    });
    document.getElementById('modal-detail-btn').href = p.detail_url;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('event-modal')).show();
  }
})();
