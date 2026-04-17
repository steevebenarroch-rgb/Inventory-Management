// PharmaCare Inventory — Client-side helpers

document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts after 5 seconds
  document.querySelectorAll('.alert.alert-dismissible').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 5000);
  });

  // Confirm delete dialogs are handled inline via onsubmit in templates

  // Highlight table rows on search match (client-side instant feedback)
  const searchInputs = document.querySelectorAll('input[name="search"]');
  searchInputs.forEach(input => {
    input.addEventListener('input', () => {
      const term = input.value.toLowerCase();
      const rows = document.querySelectorAll('tbody tr');
      rows.forEach(row => {
        if (!term) {
          row.style.display = '';
          return;
        }
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(term) ? '' : 'none';
      });
    });
  });
});
