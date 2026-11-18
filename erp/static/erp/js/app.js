(function () {
  const menu = document.getElementById('mobileMenu');
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  const closeMenu = () => { sidebar?.classList.remove('open'); backdrop?.classList.remove('visible'); };
  menu?.addEventListener('click', () => { sidebar?.classList.toggle('open'); backdrop?.classList.toggle('visible'); });
  backdrop?.addEventListener('click', closeMenu);
  document.querySelectorAll('.message-close').forEach((button) => button.addEventListener('click', () => button.closest('.message')?.remove()));
  const date = document.getElementById('todayLabel');
  if (date) date.textContent = new Intl.DateTimeFormat('en', { weekday: 'short', month: 'short', day: 'numeric' }).format(new Date());
})();
