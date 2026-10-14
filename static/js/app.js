document.addEventListener("DOMContentLoaded", function () {

    if (window.lucide) {
        lucide.createIcons();
    }

    const toggles = document.querySelectorAll(".kis-dropdown-toggle");

    toggles.forEach(toggle => {

        toggle.addEventListener("click", function (e) {

            e.stopPropagation();

            const menu = this.nextElementSibling;

            document.querySelectorAll(".kis-dropdown-menu").forEach(item => {

                if(item !== menu){
                    item.classList.remove("show");
                }

            });

            menu.classList.toggle("show");

        });

    });

    document.addEventListener("click", function () {

        document.querySelectorAll(".kis-dropdown-menu").forEach(menu => {

            menu.classList.remove("show");

        });

    });

});
// Retours V8-5 : la molette de la souris ne doit jamais modifier un montant ou une note.
// Sur un champ numérique qui a le focus, la molette fait défiler la page au lieu
// d'incrémenter/décrémenter la valeur.
(function () {
  document.addEventListener('wheel', function (e) {
    const el = e.target;
    if (el && el.tagName === 'INPUT' && el.type === 'number' && document.activeElement === el) {
      el.blur();
    }
  }, { passive: true, capture: true });
})();

// Retours V8-6 : envoi assisté par WhatsApp. Un bouton [data-wa] ouvre WhatsApp
// avec le message prérempli ; s'il porte data-wa-pdf, le PDF (reçu, bulletin…)
// est téléchargé en même temps pour être joint dans la conversation.
(function () {
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-wa]');
    if (!btn) return;
    const pdf = btn.getAttribute('data-wa-pdf');
    if (pdf) {
      const a = document.createElement('a');
      a.href = pdf; a.download = btn.getAttribute('data-wa-pdf-name') || 'document.pdf';
      document.body.appendChild(a); a.click(); a.remove();
    }
    btn.classList.add('kis-wa-sent');
    if (!btn.dataset.waLabel) { btn.dataset.waLabel = btn.textContent; btn.textContent = '✓ ' + btn.textContent.trim(); }
  });
})();
