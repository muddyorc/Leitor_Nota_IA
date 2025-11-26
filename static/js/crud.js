document.addEventListener('DOMContentLoaded', () => {
  const HIDDEN_CLASS = 'hidden';

  function findPanel(button) {
    const panelId = button?.dataset?.form;
    if (!panelId) {
      return null;
    }
    return document.getElementById(panelId);
  }

  function getForm(panel) {
    return panel ? panel.querySelector('form') : null;
  }

  function setPanelTitle(panel, mode) {
    if (!panel) {
      return;
    }
    const titleEl = panel.querySelector('[data-role="crud-title"]');
    if (!titleEl) {
      return;
    }
    if (mode === 'edit' && panel.dataset.titleEdit) {
      titleEl.textContent = panel.dataset.titleEdit;
    } else if (panel.dataset.titleNew) {
      titleEl.textContent = panel.dataset.titleNew;
    }
  }

  function resetForm(form) {
    if (!form) {
      return;
    }
    form.reset();
    const defaults = form.querySelectorAll('[data-default]');
    defaults.forEach((field) => {
      if (field.type === 'checkbox') {
        field.checked = field.dataset.default === 'true' || field.dataset.default === '1';
        return;
      }
      field.value = field.dataset.default ?? '';
    });
    const multiSelects = form.querySelectorAll('select[multiple]');
    multiSelects.forEach((select) => {
      Array.from(select.options).forEach((option) => {
        option.selected = false;
      });
    });
  }

  function setFieldValue(field, value) {
    if (!field) {
      return;
    }

    if (field instanceof RadioNodeList) {
      Array.from(field).forEach((radio) => {
        radio.checked = String(value ?? '') === radio.value;
      });
      return;
    }

    if (field.type === 'checkbox') {
      field.checked = Boolean(value);
      return;
    }

    if (field.tagName === 'SELECT' && field.multiple) {
      const values = Array.isArray(value)
        ? value.map((val) => String(val))
        : value != null
          ? [String(value)]
          : [];
      Array.from(field.options).forEach((option) => {
        option.selected = values.includes(option.value);
      });
      return;
    }

    if (field.tagName === 'SELECT') {
      field.value = value ?? '';
      return;
    }

    field.value = value ?? '';
  }

  function populateForm(form, record) {
    if (!form || !record || typeof record !== 'object') {
      return;
    }

    Object.entries(record).forEach(([key, value]) => {
      const field = form.elements.namedItem(key);
      setFieldValue(field, value);
    });
  }

  function openForm(button) {
    const panel = findPanel(button);
    if (!panel) {
      return;
    }
    const form = getForm(panel);
    const recordAttr = button.getAttribute('data-record');
    let record = null;
    if (recordAttr) {
      try {
        record = JSON.parse(recordAttr);
      } catch (error) {
        console.warn('Não foi possível interpretar o registro:', error);
      }
    }

    if (record) {
      populateForm(form, record);
      setPanelTitle(panel, 'edit');
    } else {
      resetForm(form);
      setPanelTitle(panel, 'new');
    }

    panel.classList.remove(HIDDEN_CLASS);
    const firstInput = panel.querySelector('input:not([type="hidden"]), select, textarea');
    if (firstInput) {
      firstInput.focus();
    }
  }

  function closeForm(button) {
    const panel = findPanel(button);
    if (!panel) {
      return;
    }
    const form = getForm(panel);
    resetForm(form);
    setPanelTitle(panel, 'new');
    panel.classList.add(HIDDEN_CLASS);
  }

  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-action]');
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === 'open-form') {
      event.preventDefault();
      openForm(target);
      return;
    }
    if (action === 'cancel-form') {
      event.preventDefault();
      closeForm(target);
    }
  });

  document.addEventListener('keyup', (event) => {
    if (event.key !== 'Escape') {
      return;
    }
    document.querySelectorAll('.crud-panel').forEach((panel) => {
      if (!panel.classList.contains(HIDDEN_CLASS)) {
        const form = getForm(panel);
        resetForm(form);
        panel.classList.add(HIDDEN_CLASS);
      }
    });
  });
});
