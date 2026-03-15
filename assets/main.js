// Tab switching
function initTabs() {
  const btns = document.querySelectorAll('.tab-btn');
  const panes = document.querySelectorAll('.tab-pane');
  if (!btns.length) return;

  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      btns.forEach(b => b.classList.remove('active'));
      panes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const pane = document.getElementById('tab-' + target);
      if (pane) {
        pane.classList.add('active');
        // re-trigger animations
        pane.querySelectorAll('.note-card').forEach((card, i) => {
          card.style.animation = 'none';
          card.offsetHeight; // reflow
          card.style.animation = '';
          card.style.animationDelay = (0.05 + i * 0.07) + 's';
        });
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', initTabs);
