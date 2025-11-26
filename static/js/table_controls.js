document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.sort-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const formId = button.dataset.form;
      const form = formId ? document.getElementById(formId) : button.closest('form');
      if (!form) {
        return;
      }

      const sortInput = form.querySelector('input[name="sort"]');
      const dirInput = form.querySelector('input[name="dir"]');
      if (!sortInput || !dirInput) {
        return;
      }

      const selectedField = button.dataset.sort;
      if (!selectedField) {
        return;
      }

      const currentField = sortInput.value;
      const currentDir = dirInput.value === 'desc' ? 'desc' : 'asc';
      const nextDir = currentField === selectedField && currentDir === 'asc' ? 'desc' : 'asc';

      sortInput.value = selectedField;
      dirInput.value = nextDir;

      form.submit();
    });
  });
});
