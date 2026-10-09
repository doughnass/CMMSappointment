(function () {
  // Show current date in topbar
  const dateEl = document.getElementById('js-date');
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString('th-TH',
      { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  }

  // Mobile sidebar: toggle, backdrop, Escape and close-on-navigate
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  const toggle = document.getElementById('sidebar-toggle');
  function setOpen(open) {
    sidebar.classList.toggle('show', open);
    backdrop.classList.toggle('show', open);
    document.body.classList.toggle('sidebar-open', open);
    toggle.setAttribute('aria-expanded', String(open));
  }
  toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('show')));
  backdrop.addEventListener('click', () => setOpen(false));
  sidebar.addEventListener('click', e => { if (e.target.closest('a')) setOpen(false); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && sidebar.classList.contains('show')) { setOpen(false); toggle.focus(); }
  });

  // Make elements that navigate via onclick reachable and operable by keyboard
  document.querySelectorAll('[onclick*="location.href"]').forEach(el => {
    el.setAttribute('tabindex', '0');
    el.setAttribute('role', 'link');
    el.setAttribute('data-row-link', '');
    el.addEventListener('keydown', e => {
      if (e.target === el && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        el.click();
      }
    });
  });

  // Confirmation modal for forms marked with data-confirm="message"
  const modalEl = document.getElementById('confirm-modal');
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  const messageEl = document.getElementById('confirm-modal-message');
  const okBtn = document.getElementById('confirm-modal-ok');
  let pendingForm = null;

  document.addEventListener('submit', e => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-confirm')) return;
    e.preventDefault();
    pendingForm = form;
    messageEl.textContent = form.getAttribute('data-confirm');
    modal.show();
  });

  okBtn.addEventListener('click', () => {
    if (!pendingForm) return;
    const form = pendingForm;
    pendingForm = null;
    modal.hide();
    // HTMLFormElement.submit() skips the submit event, so the modal is not shown again
    form.submit();
  });

  modalEl.addEventListener('hidden.bs.modal', () => { pendingForm = null; });
  modalEl.addEventListener('shown.bs.modal', () => okBtn.focus());
})();
