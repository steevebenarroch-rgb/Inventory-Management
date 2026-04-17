document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts after 6 seconds
  document.querySelectorAll('.alert.alert-dismissible').forEach(el => {
    setTimeout(() => bootstrap.Alert.getOrCreateInstance(el)?.close(), 6000);
  });

  // Live client-side search on any table (filters visible rows instantly)
  document.querySelectorAll('input[data-search-table]').forEach(input => {
    const tableId = input.dataset.searchTable;
    const tbody = document.querySelector(`#${tableId} tbody`);
    if (!tbody) return;
    input.addEventListener('input', () => {
      const term = input.value.toLowerCase();
      Array.from(tbody.rows).forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(term) ? '' : 'none';
      });
    });
  });
});
