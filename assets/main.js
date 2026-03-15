// Tab switching
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = document.getElementById('tab-' + target);
      if (panel) {
        panel.classList.add('active');
        // re-trigger animations
        panel.querySelectorAll('.note-card').forEach((card, i) => {
          card.style.animation = 'none';
          card.offsetHeight;
          card.style.animation = '';
          card.style.animationDelay = (0.05 + i * 0.07) + 's';
        });
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', initTabs);
