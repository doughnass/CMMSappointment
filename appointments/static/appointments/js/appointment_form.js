function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Show a non-blocking notice when a helper API fails; the form stays usable.
const apiErrorEl = document.getElementById('form-api-error');
const apiFailures = new Set();
function reportApiError(key, message, error) {
  console.error(message, error);
  apiFailures.add(key);
  apiErrorEl.textContent = `${message} คุณยังสามารถกรอกข้อมูลและบันทึกนัดหมายได้ตามปกติ`;
  apiErrorEl.classList.remove('d-none');
}
function clearApiError(key) {
  apiFailures.delete(key);
  if (!apiFailures.size) apiErrorEl.classList.add('d-none');
}

// Ignore responses from superseded requests
const requestSeq = {};
function nextSeq(name) { return requestSeq[name] = (requestSeq[name] || 0) + 1; }
function isStale(name, seq) { return requestSeq[name] !== seq; }

const OFFICE_START = [8, 30];
const OFFICE_END   = [16, 30];
const OFFICE_DAYS  = [1, 2, 3, 4, 5]; // Mon-Fri (JS: 0=Sun)

function isOfficeHours(dateStr, timeStr) {
  if (!dateStr || !timeStr) return null;
  const d = new Date(dateStr);
  const dow = d.getDay(); // 0=Sun
  if (!OFFICE_DAYS.includes(dow)) return false;
  const [h, m] = timeStr.split(':').map(Number);
  const t = h * 60 + m;
  const s = OFFICE_START[0] * 60 + OFFICE_START[1];
  const e = OFFICE_END[0] * 60 + OFFICE_END[1];
  return t >= s && t < e;
}

function updateEndTime() {
  const startVal = document.getElementById('id_start_time').value;
  const durVal   = parseInt(document.getElementById('id_duration_minutes').value);
  if (!startVal || isNaN(durVal) || durVal <= 0) return;
  const [h, m] = startVal.split(':').map(Number);
  const total = h * 60 + m + durVal;
  const eh = Math.floor(total / 60) % 24;
  const em = total % 60;
  document.getElementById('id_end_time').value =
    `${String(eh).padStart(2,'0')}:${String(em).padStart(2,'0')}`;
  updateTimeTypeBadge();
}

function updateTimeTypeBadge() {
  const dateVal  = document.getElementById('id_scheduled_date').value;
  const startVal = document.getElementById('id_start_time').value;
  const badge    = document.getElementById('time-type-display');
  const office   = isOfficeHours(dateVal, startVal);
  if (office === null) {
    badge.innerHTML = '<span class="badge bg-secondary time-type-badge">–</span>';
  } else if (office) {
    badge.innerHTML = '<span class="badge badge-office time-type-badge"><i class="bi bi-sun me-1"></i>ในเวลาราชการ</span>';
  } else {
    badge.innerHTML = '<span class="badge badge-overtime time-type-badge"><i class="bi bi-moon me-1"></i>นอกเวลาราชการ</span>';
  }
}

async function fetchEquipmentInfo(pk) {
  return fetchJson(`/api/equipment/${pk}/info/`);
}

async function fetchAvailability(techId, dateStr) {
  if (!techId || !dateStr) return null;
  return fetchJson(`/api/technician-availability/?technician_id=${encodeURIComponent(techId)}&date=${encodeURIComponent(dateStr)}`);
}

function selectedServiceType() {
  return document.getElementById('id_service_type').value || 'PM';
}

// ── Equipment select ──
document.getElementById('id_equipment').addEventListener('change', async function () {
  const pk = this.value;
  const infoEl = document.getElementById('equipment-info');
  const seq = nextSeq('equipment');
  if (!pk) { infoEl.textContent = ''; return; }
  let data;
  try {
    data = await fetchEquipmentInfo(pk);
  } catch (err) {
    if (!isStale('equipment', seq)) reportApiError('equipment', 'โหลดข้อมูลเครื่องมือไม่สำเร็จ', err);
    return;
  }
  if (isStale('equipment', seq)) return;
  clearApiError('equipment');
  infoEl.textContent =
    `${data.customer} – ${data.department || ''} | PM: ${data.maintenance_duration} นาที` +
    (data.requires_calibration
      ? ` + CAL: ${data.calibration_duration} นาที (รวม ${data.total_duration} นาที)`
      : '');
  document.getElementById('id_duration_minutes').value = data.total_duration;
  const stEl = document.getElementById('id_service_type') || null;
  if (stEl) stEl.value = data.default_service_type;
  updateEndTime();
  fetchTechSuggestions();
  loadCalendarAvailability(datePicker);
});

// ── Equipment autocomplete search ──
const eqSearchInput = document.getElementById('equipment-search-input');
const eqSearchResults = document.getElementById('equipment-search-results');
const eqSelect = document.getElementById('id_equipment');
let eqSearchTimer = null;

eqSearchInput.setAttribute('role', 'combobox');
eqSearchInput.setAttribute('aria-expanded', 'false');
eqSearchInput.setAttribute('aria-controls', 'equipment-search-results');
eqSearchResults.setAttribute('role', 'listbox');

function showEqResults(show) {
  eqSearchResults.classList.toggle('d-none', !show);
  eqSearchInput.setAttribute('aria-expanded', String(show));
}

function renderEquipmentResults(results) {
  if (!results.length) {
    eqSearchResults.innerHTML = '<div class="result-item text-muted">ไม่พบเครื่องมือ ลองค้นด้วยรหัส Serial No. หรือชื่ออื่น</div>';
  } else {
    eqSearchResults.innerHTML = results.map(r => `
      <div class="result-item" role="option" tabindex="0" data-id="${escapeHtml(r.id)}" data-label="${escapeHtml(r.code)} – ${escapeHtml(r.serial_number)}">
        <div class="fw-500">${escapeHtml(r.code)} <span class="text-muted">– ${escapeHtml(r.serial_number)}</span></div>
        <div class="small text-muted">${escapeHtml(r.name)}${r.name_th ? ' (' + escapeHtml(r.name_th) + ')' : ''} | ${escapeHtml(r.customer)}${r.department ? ' – ' + escapeHtml(r.department) : ''}</div>
      </div>
    `).join('');
  }
  showEqResults(true);
}

async function searchEquipment(q) {
  const data = await fetchJson(`/api/equipment-search/?q=${encodeURIComponent(q)}`);
  return data.results;
}

eqSearchInput.addEventListener('input', function () {
  const q = this.value.trim();
  clearTimeout(eqSearchTimer);
  if (q.length < 1) { nextSeq('eqSearch'); showEqResults(false); return; }
  eqSearchTimer = setTimeout(async () => {
    const seq = nextSeq('eqSearch');
    eqSearchResults.innerHTML = '<div class="result-item text-muted"><span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>กำลังค้นหา…</div>';
    showEqResults(true);
    try {
      const results = await searchEquipment(q);
      if (isStale('eqSearch', seq)) return;
      clearApiError('eqSearch');
      renderEquipmentResults(results);
    } catch (err) {
      if (isStale('eqSearch', seq)) return;
      eqSearchResults.innerHTML = '<div class="result-item text-danger">ค้นหาไม่สำเร็จ กรุณาลองอีกครั้ง</div>';
      reportApiError('eqSearch', 'ค้นหาเครื่องมือไม่สำเร็จ', err);
    }
  }, 250);
});

eqSearchInput.addEventListener('focus', function () {
  if (this.value.trim().length >= 1 && eqSearchResults.innerHTML) {
    showEqResults(true);
  }
});

eqSearchInput.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { showEqResults(false); }
  if (e.key === 'ArrowDown') {
    const first = eqSearchResults.querySelector('.result-item[data-id]');
    if (first) { e.preventDefault(); first.focus(); }
  }
});

document.addEventListener('click', function (e) {
  if (!eqSearchResults.contains(e.target) && e.target !== eqSearchInput) {
    showEqResults(false);
  }
});

function chooseEquipment(item) {
  eqSelect.value = item.dataset.id;
  eqSearchInput.value = item.dataset.label;
  showEqResults(false);
  eqSelect.dispatchEvent(new Event('change'));
  updateSummary();
}

eqSearchResults.addEventListener('click', function (e) {
  const item = e.target.closest('.result-item[data-id]');
  if (item) chooseEquipment(item);
});

eqSearchResults.addEventListener('keydown', function (e) {
  const item = e.target.closest('.result-item[data-id]');
  if (!item) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); chooseEquipment(item); }
  else if (e.key === 'ArrowDown' && item.nextElementSibling) { e.preventDefault(); item.nextElementSibling.focus(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); (item.previousElementSibling || eqSearchInput).focus(); }
  else if (e.key === 'Escape') { showEqResults(false); eqSearchInput.focus(); }
});

// ── Technician suggestions (based on equipment code + date) ──
async function fetchTechSuggestions() {
  const eqId = eqSelect.value;
  const dateStr = document.getElementById('id_scheduled_date').value;
  const listEl = document.getElementById('tech-suggest-list');
  const hintEl = document.getElementById('tech-suggest-hint');
  const recommendationEl = document.getElementById('ai-recommendation');
  const seq = nextSeq('suggestions');
  if (!eqId || !dateStr) {
    listEl.innerHTML = '';
    recommendationEl.classList.add('d-none');
    hintEl.classList.remove('d-none');
    return;
  }
  hintEl.classList.add('d-none');
  listEl.setAttribute('aria-busy', 'true');
  let data;
  try {
    data = await fetchJson(`/api/technician-suggestions/?equipment_id=${encodeURIComponent(eqId)}&date=${encodeURIComponent(dateStr)}&service_type=${encodeURIComponent(selectedServiceType())}`);
  } catch (err) {
    if (isStale('suggestions', seq)) return;
    listEl.removeAttribute('aria-busy');
    listEl.innerHTML = '';
    recommendationEl.classList.add('d-none');
    reportApiError('suggestions', 'โหลดคำแนะนำช่างไม่สำเร็จ', err);
    return;
  }
  if (isStale('suggestions', seq)) return;
  listEl.removeAttribute('aria-busy');
  clearApiError('suggestions');
  if (data.error) { listEl.innerHTML = ''; recommendationEl.classList.add('d-none'); return; }

  if (data.recommendation) {
    recommendationEl.classList.remove('no-match');
    recommendationEl.innerHTML = `<div class="d-flex align-items-start gap-2">
      <i class="bi bi-stars text-success fs-5"></i>
      <div><div class="small text-success fw-600">คำแนะนำอัจฉริยะจากข้อมูลระบบ</div>
      <div class="recommendation-name">${escapeHtml(data.recommendation.name)}</div>
      <div class="small text-muted">${data.recommendation.reasons.map(escapeHtml).join(' · ')}</div></div>
    </div>`;
    recommendationEl.classList.remove('d-none');
  } else if (data.message) {
    recommendationEl.classList.add('no-match');
    recommendationEl.innerHTML = `<div class="d-flex align-items-start gap-2">
      <i class="bi bi-exclamation-triangle text-danger fs-5"></i>
      <div><div class="small text-danger fw-600">ยังไม่สามารถแนะนำช่างได้</div>
      <div class="recommendation-name">${escapeHtml(data.message)}</div>
      <div class="small text-muted">กรุณาตรวจสอบทักษะที่กำหนดให้เครื่องมือ หรือเลือกวันอื่น</div></div>
    </div>`;
    recommendationEl.classList.remove('d-none');
  } else {
    recommendationEl.classList.remove('no-match');
    recommendationEl.classList.add('d-none');
  }

  const currentTechId = document.getElementById('id_technician').value;

  listEl.innerHTML = data.technicians.map(t => {
    const statusText = t.on_leave ? 'ลา' : (!t.is_work_day ? 'ไม่มีเวรวันนี้' : 'ว่าง');
    const statusBadge = t.available
      ? `<span class="badge bg-success">${statusText}</span>`
      : `<span class="badge bg-danger">${statusText}</span>`;
    const skillBadge = t.skill_match
      ? '<span class="badge bg-info text-dark">ทักษะตรง</span>'
      : '<span class="badge bg-secondary">ทักษะไม่ตรง</span>';
    const capacityBadge = t.available
      ? (t.capacity_remaining > 0
          ? `<span class="badge bg-primary capacity-badge">รับได้อีก ${Number(t.capacity_remaining)} เครื่อง</span>`
          : `<span class="badge bg-warning text-dark capacity-badge">งานเต็มแล้ว</span>`)
      : '';
    const isSelected = String(t.id) === currentTechId;
    const selectedCls = isSelected ? 'selected' : '';
    const unavailCls = !t.available ? 'unavailable' : '';
    return `
      <div class="col-md-6 col-lg-4">
        <div class="tech-suggest-card ${selectedCls} ${unavailCls}" data-id="${escapeHtml(t.id)}"
             role="button" tabindex="0" aria-pressed="${isSelected}">
          <div class="d-flex justify-content-between align-items-center">
            <span class="fw-500">${escapeHtml(t.name)}</span>
            <span class="badge" style="background:${escapeHtml(t.color)}">&nbsp;</span>
          </div>
          <div class="mt-1 d-flex gap-1 flex-wrap">
            ${statusBadge} ${skillBadge} ${capacityBadge}
          </div>
          <div class="small text-muted mt-1">งานวันนี้: ${Number(t.job_count_today)} งาน (${Number(t.busy_minutes)} นาที)</div>
        </div>
      </div>
    `;
  }).join('');
}

function chooseTechnicianCard(card) {
  const techSelect = document.getElementById('id_technician');
  techSelect.value = card.dataset.id;
  techSelect.dispatchEvent(new Event('change'));
  document.querySelectorAll('.tech-suggest-card').forEach(c => {
    c.classList.remove('selected');
    c.setAttribute('aria-pressed', 'false');
  });
  card.classList.add('selected');
  card.setAttribute('aria-pressed', 'true');
}

document.getElementById('tech-suggest-list').addEventListener('click', function (e) {
  const card = e.target.closest('.tech-suggest-card');
  if (card) chooseTechnicianCard(card);
});
document.getElementById('tech-suggest-list').addEventListener('keydown', function (e) {
  const card = e.target.closest('.tech-suggest-card');
  if (card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); chooseTechnicianCard(card); }
});

// ── Date-picker calendar with availability colouring ──
let calendarAvailability = {};

async function loadCalendarAvailability(fpInstance) {
  if (!fpInstance) return;
  const eqId = eqSelect.value;
  const techId = document.getElementById('id_technician').value;
  const params = new URLSearchParams({
    year: fpInstance.currentYear,
    month: fpInstance.currentMonth + 1,
    service_type: selectedServiceType(),
  });
  if (eqId) params.set('equipment_id', eqId);
  if (techId) params.set('technician_id', techId);

  const seq = nextSeq('calendar');
  let data;
  try {
    data = await fetchJson(`/api/calendar-availability/?${params.toString()}`);
  } catch (err) {
    if (!isStale('calendar', seq)) reportApiError('calendar', 'โหลดสถานะวันว่างไม่สำเร็จ', err);
    return;
  }
  if (isStale('calendar', seq)) return;
  clearApiError('calendar');
  calendarAvailability = {};
  (data.days || []).forEach(d => { calendarAvailability[d.date] = d; });
  renderDateRecommendations(data.days || []);
  fpInstance.redraw();
}

function renderDateRecommendations(days) {
  const container = document.getElementById('date-recommendations');
  const today = new Date().toISOString().slice(0, 10);
  const availableDays = days
    .filter(day => day.date >= today && ['available', 'limited'].includes(day.status))
    .sort((a, b) => b.capacity - a.capacity || a.date.localeCompare(b.date))
    .slice(0, 3);
  if (!eqSelect.value || !availableDays.length) {
    container.classList.add('d-none');
    return;
  }
  container.innerHTML = `<div class="small fw-600 text-warning-emphasis mb-1"><i class="bi bi-stars me-1"></i>วันที่แนะนำที่ยังมีคิวว่าง</div>
    <div class="d-flex flex-wrap gap-1">${availableDays.map(day =>
      `<button type="button" class="btn date-recommendation" data-date="${escapeHtml(day.date)}">
        ${formatRecommendationDate(day.date)} · เหลือ ${Number(day.capacity)} คิว
      </button>`).join('')}</div>`;
  container.classList.remove('d-none');
}

function formatRecommendationDate(dateStr) {
  return new Intl.DateTimeFormat('th-TH', { day: 'numeric', month: 'short', year: 'numeric' })
    .format(new Date(`${dateStr}T00:00:00`));
}

document.getElementById('date-recommendations').addEventListener('click', function (e) {
  const button = e.target.closest('[data-date]');
  if (!button) return;
  datePicker.setDate(button.dataset.date, true);
});

const datePicker = flatpickr('#id_scheduled_date', {
  locale: 'th',
  dateFormat: 'Y-m-d',
  altInput: true,
  altFormat: 'j F Y',
  allowInput: true,
  minDate: 'today',
  onDayCreate: function (dObj, dStr, fpInstance, dayElem) {
    const iso = fpInstance.formatDate(dayElem.dateObj, 'Y-m-d');
    const info = calendarAvailability[iso];
    if (!info) return;
    dayElem.classList.add(`day-${info.status}`);
    const labels = {
      available: `ว่างมาก (รับได้อีก ${info.capacity} เครื่อง)`,
      limited: `เหลือน้อย (รับได้อีก ${info.capacity} เครื่อง)`,
      full: 'เต็มแล้ว ไม่ว่างรับงานเพิ่ม',
      closed: 'ไม่มีเวรช่างวันนี้ (วันหยุด/ลาทั้งหมด)',
    };
    dayElem.title = labels[info.status] || '';
  },
  onChange: function () {
    onDateOrTechChange();
    fetchTechSuggestions();
  },
  onMonthChange: function (selectedDates, dateStr, fpInstance) {
    loadCalendarAvailability(fpInstance);
  },
  onOpen: function (selectedDates, dateStr, fpInstance) {
    loadCalendarAvailability(fpInstance);
  },
});

// ── Date / Technician change ──
async function onDateOrTechChange() {
  const techId  = document.getElementById('id_technician').value;
  const dateStr = document.getElementById('id_scheduled_date').value;
  const infoEl  = document.getElementById('availability-info');

  updateTimeTypeBadge();

  const seq = nextSeq('availability');
  if (!techId || !dateStr) { infoEl.innerHTML = ''; return; }

  let data;
  try {
    data = await fetchAvailability(techId, dateStr);
  } catch (err) {
    if (!isStale('availability', seq)) {
      infoEl.innerHTML = '';
      reportApiError('availability', 'โหลดตารางงานของช่างไม่สำเร็จ', err);
    }
    return;
  }
  if (isStale('availability', seq)) return;
  clearApiError('availability');
  if (!data) { infoEl.innerHTML = ''; return; }

  const dot = data.available
    ? '<span class="availability-indicator bg-success me-1"></span>'
    : '<span class="availability-indicator bg-danger me-1"></span>';

  let html = `<div class="d-flex align-items-center gap-2 flex-wrap">
    ${dot}
    <span class="fw-500">${escapeHtml(data.technician_name)}</span>
    <span class="badge ${data.available ? 'bg-success' : 'bg-danger'}">${data.available ? 'ว่างในวันนี้' : 'ไม่อยู่'}</span>`;

  if (data.busy_slots && data.busy_slots.length > 0) {
    html += `<span class="text-muted small">| นัดที่มีอยู่แล้ว:</span>`;
    data.busy_slots.forEach(s => {
      html += `<span class="busy-slot">${escapeHtml(s.start_time)}–${escapeHtml(s.end_time)} (${escapeHtml(s.appointment_no)})</span>`;
    });
  }
  html += '</div>';
  infoEl.innerHTML = html;
}

document.getElementById('id_technician').addEventListener('change', function () {
  onDateOrTechChange();
  loadCalendarAvailability(datePicker);
});
document.getElementById('id_scheduled_date').addEventListener('change', function () {
  onDateOrTechChange();
  fetchTechSuggestions();
});
document.getElementById('id_start_time').addEventListener('change', function () {
  updateEndTime();
  updateTimeTypeBadge();
});
document.getElementById('id_duration_minutes').addEventListener('input', updateEndTime);

// ── Quick time buttons ──
document.querySelectorAll('.quick-time').forEach(btn => {
  btn.addEventListener('click', function () {
    document.getElementById('id_start_time').value = this.dataset.time;
    updateEndTime();
    updateTimeTypeBadge();
    updateSummary();
  });
});

// ── Summary sidebar updater ──
function updateSummary() {
  // Equipment
  const eqOpt = eqSelect.options[eqSelect.selectedIndex];
  document.getElementById('sum-equipment').textContent =
    eqSelect.value ? eqOpt.text.split(' –')[0] : '–';
  // Service type
  const stEl = document.getElementById('id_service_type');
  document.getElementById('sum-service-type').textContent =
    stEl.value ? stEl.options[stEl.selectedIndex].text : '–';
  // Date
  const dateEl = document.getElementById('id_scheduled_date');
  document.getElementById('sum-date').textContent = dateEl.value || '–';
  // Technician
  const techEl = document.getElementById('id_technician');
  document.getElementById('sum-technician').textContent =
    techEl.value ? techEl.options[techEl.selectedIndex].text : '–';
  // Time
  const start = document.getElementById('id_start_time').value;
  const end   = document.getElementById('id_end_time').value;
  const dur   = document.getElementById('id_duration_minutes').value;
  document.getElementById('sum-time').textContent =
    start ? `${start}–${end} (${dur} นาที)` : '–';
  // Coordinator
  const coord = document.getElementById('id_coordinator_name').value;
  document.getElementById('sum-coordinator').textContent = coord || '–';
}

// ── LocalStorage: remember coordinator ──
const coordEl = document.getElementById('id_coordinator_name');
const LS_KEY  = 'cmms_coordinator';
coordEl.addEventListener('input', function () {
  if (this.value.trim()) localStorage.setItem(LS_KEY, this.value.trim());
  updateSummary();
});

// ── Prevent double submission ──
const appointmentForm = document.getElementById('appointment-form');
const submitBtn = document.getElementById('btn-submit');
const submitBtnHtml = submitBtn.innerHTML;
appointmentForm.addEventListener('submit', function (e) {
  if (submitBtn.disabled) { e.preventDefault(); return; }
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> กำลังบันทึก…';
});
// Restore the button when returning via the browser back button
window.addEventListener('pageshow', function (e) {
  if (e.persisted) { submitBtn.disabled = false; submitBtn.innerHTML = submitBtnHtml; }
});

// ── Ctrl+Enter shortcut ──
document.addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    submitBtn.click();
  }
});

// Hook updateSummary to existing change events
document.getElementById('id_service_type').addEventListener('change', updateSummary);
document.getElementById('id_service_type').addEventListener('change', function () {
  fetchTechSuggestions();
  loadCalendarAvailability(datePicker);
});
document.getElementById('id_technician').addEventListener('change', updateSummary);
document.getElementById('id_scheduled_date').addEventListener('change', updateSummary);
document.getElementById('id_start_time').addEventListener('change', updateSummary);
document.getElementById('id_duration_minutes').addEventListener('input', updateSummary);

// ── Init on load ──
window.addEventListener('DOMContentLoaded', function () {
  updateTimeTypeBadge();
  // Restore coordinator from localStorage
  const savedCoord = localStorage.getItem(LS_KEY);
  if (savedCoord && !coordEl.value) coordEl.value = savedCoord;

  const eq      = eqSelect.value;
  const techEl  = document.getElementById('id_technician');
  const dateVal = document.getElementById('id_scheduled_date').value;

  // Equipment pre-fill
  if (eq) {
    const selectedOption = eqSelect.options[eqSelect.selectedIndex];
    if (selectedOption) eqSearchInput.value = selectedOption.text;
    fetchEquipmentInfo(eq).then(data => {
      document.getElementById('equipment-info').textContent =
        `${data.customer} – ${data.department || ''} | PM: ${data.maintenance_duration} นาที`;
    }).catch(err => reportApiError('equipment', 'โหลดข้อมูลเครื่องมือไม่สำเร็จ', err));
    fetchTechSuggestions();
  }

  // Date pre-fill: sync flatpickr (dispatch board or edit form)
  if (dateVal) {
    datePicker.setDate(dateVal, false);
  }

  // Tech + Date both pre-filled (dispatch board): show availability slots immediately
  if (techEl.value && dateVal) {
    onDateOrTechChange();
  }

  loadCalendarAvailability(datePicker);
  updateSummary();
});
