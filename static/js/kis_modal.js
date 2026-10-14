(function () {
  const modal = document.getElementById('kis-modal');
  const body = document.getElementById('kis-modal-body');
  const title = document.getElementById('kis-modal-title');
  if (!modal || !body) return;

  function close() {
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    body.innerHTML = '';
  }
  function open(url, label) {
    title.textContent = label || 'Action';
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    body.innerHTML = '<div class="kis-modal-loading">Chargement…</div>';
    fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
      .then(r => r.text().then(html => ({ok:r.ok, html:html})))
      .then(result => {
      body.innerHTML = result.html;
      if (window.htmx) window.htmx.process(body);
      initTeachingForm(body);
    });
  }

  /*
   * Formulaire d'affectation (page et fenêtre modale).
   * Ordre : Enseignant > Classe > Type > Matière. La matière dépend de la
   * classe : tant qu'aucune classe n'est choisie, la liste l'indique au lieu
   * d'être simplement grisée.
   */
  function bindTeachingForm(form, ids) {
    if (!form || form.dataset.initialized === '1') return;
    const teacher = form.querySelector('#id_teacher');
    const assignmentType = form.querySelector('#id_assignment_type');
    const subjectGroup = form.querySelector(ids.group);
    const subject = form.querySelector('#id_subject');
    const classe = form.querySelector('#id_classe');
    const mode = form.querySelector(ids.mode);
    const help = form.querySelector(ids.help);
    if (!teacher || !assignmentType || !subjectGroup || !subject || !classe) return;
    form.dataset.initialized = '1';
    let profiles = {}; let classSubjects = {};
    try { profiles = JSON.parse(form.dataset.teacherProfiles || '{}'); } catch (_) {}
    try { classSubjects = JSON.parse(form.dataset.classSubjects || '{}'); } catch (_) {}
    let wanted = subject.value;

    function fillSubjects() {
      const items = classSubjects[classe.value] || [];
      subject.innerHTML = '';
      const first = document.createElement('option');
      first.value = '';
      if (!classe.value) first.textContent = '— Choisissez d’abord la classe —';
      else if (!items.length) first.textContent = '— Aucune matière au programme de cette classe —';
      else first.textContent = '— Sélectionner une matière —';
      subject.appendChild(first);
      items.forEach(function (item) {
        const option = document.createElement('option');
        option.value = item.id; option.textContent = item.name;
        if (String(item.id) === String(wanted)) option.selected = true;
        subject.appendChild(option);
      });
      subject.disabled = !classe.value || !items.length;
      if (help) {
        if (!classe.value) help.textContent = 'Choisissez la classe : la liste affiche alors les matières de son programme.';
        else if (!items.length) help.textContent = 'Le programme de cette classe ne contient aucune matière : vérifiez le référentiel pédagogique.';
        else help.textContent = '';
      }
    }

    function update() {
      const profile = profiles[teacher.value] || '';
      // Le profil propose seulement : tout enseignant peut être affecté à tout niveau,
      // en responsabilité de classe ou pour une matière (retours du 08/10).
      const generaliste = profile === 'generaliste';
      const responsibility = assignmentType.value === 'class_responsibility';
      subjectGroup.hidden = responsibility;
      if (responsibility) { subject.value = ''; subject.disabled = true; } else fillSubjects();
      if (mode) {
        mode.hidden = !profile;
        if (responsibility) mode.textContent = 'Responsabilité de classe : l’enseignant est affecté à toute la classe, sans matière précise.';
        else mode.textContent = 'Enseignement d’une matière : choisissez une matière prévue au programme de la classe.';
      }
    }

    teacher.addEventListener('change', function () {
      // Type proposé selon le profil ; l'utilisateur peut toujours le changer ensuite.
      const profile = profiles[teacher.value] || '';
      if (profile) assignmentType.value = profile === 'generaliste' ? 'class_responsibility' : 'subject_teaching';
      update();
    });
    assignmentType.addEventListener('change', update);
    classe.addEventListener('change', update);
    subject.addEventListener('change', function () { wanted = subject.value; });
    // Le type désactivé (généraliste) n'est pas envoyé par le navigateur :
    // on le réactive juste avant l'envoi pour que le serveur le reçoive.
    form.addEventListener('submit', function () { assignmentType.disabled = false; subject.disabled = false; });
    update();
  }

  function initTeachingForm(root) {
    bindTeachingForm(root.querySelector('.kis-modal-teaching-form'),
      { group: '#modal-subject-group', mode: '#modal-assignment-mode', help: '#modal-subject-help' });
  }
  window.kisBindTeachingForm = bindTeachingForm;

  document.addEventListener('click', function (event) {
    // Un clic sur le voile ferme la modale : il ne doit jamais rester
    // un overlay invisible qui bloque toute la page.
    if (event.target === modal || event.target.classList.contains('kis-modal-backdrop')) {
      close();
      return;
    }
    const opener = event.target.closest('[data-modal-url]');
    if (opener) {
      event.preventDefault();
      let modalUrl = opener.dataset.modalUrl;
      if (opener.dataset.modalNext) {
        modalUrl += (modalUrl.includes('?') ? '&' : '?') + 'next=' + encodeURIComponent(opener.dataset.modalNext);
      }
      open(modalUrl, opener.dataset.modalTitle);
      return;
    }
    if (event.target.closest('[data-modal-close]')) close();
  });

  document.addEventListener('kisClassCreated', function () {
    close();
    setTimeout(function(){
      const select = document.getElementById('classe');
      if (select && select.value) select.dispatchEvent(new Event('change', {bubbles:true}));
    }, 0);
  });
  // Depuis la page Classes, le formulaire est soumis par HTMX avec ?list=1.
  // Le serveur demande alors explicitement le rafraîchissement de la liste.
  document.addEventListener('kisModalReload', function () {
    close();
    window.location.reload();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !modal.hidden) close();
  });
  document.addEventListener('kisFeeCreated', function () {
    close();
    const enrollmentFees = document.getElementById('enrollment-fees');
    const classe = document.getElementById('classe');
    if (enrollmentFees && classe && classe.value) {
      const url = enrollmentFees.getAttribute('hx-get') + '?classe=' + encodeURIComponent(classe.value);
      if (window.htmx) {
        window.htmx.ajax('GET', url, {target:'#enrollment-fees', swap:'innerHTML'});
      } else {
        fetch(url, {headers:{'X-Requested-With':'XMLHttpRequest'}}).then(r => r.text()).then(html => {
          enrollmentFees.innerHTML = html;
          classe.dispatchEvent(new Event('change', {bubbles:true}));
        });
      }
    } else {
      window.location.reload();
    }
  });
  document.addEventListener('htmx:afterRequest', function (event) {
    if (event.detail && event.detail.xhr && event.detail.xhr.getResponseHeader('X-KIS-Class-Id')) close();
  });

  function submitModalForm(form) {
    const fd = new FormData(form);
    return fetch(form.action || window.location.href, {
      method: 'POST',
      body: fd,
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    }).then(async r => ({
      ok: r.ok,
      text: await r.text(),
      id: r.headers.get('X-KIS-Class-Id'),
      trigger: r.headers.get('HX-Trigger')
    })).then(result => {
      if (result.ok && result.trigger === 'kisModalReload') {
        close();
        window.location.reload();
        return;
      }
      if (result.ok && result.id) {
        const select = document.getElementById('classe');
        const wrap = document.createElement('div'); wrap.innerHTML = result.text.trim();
        if (select && wrap.firstElementChild) { select.appendChild(wrap.firstElementChild); select.value = result.id; }
        close();
        return;
      }
      if (result.ok && result.trigger === 'kisFeeCreated') {
        close();
        document.dispatchEvent(new Event('kisFeeCreated'));
        return;
      }
      body.innerHTML = result.text;
      if (window.htmx) window.htmx.process(body);
      initTeachingForm(body);
    });
  }

  // Secondary forms loaded in the generic KIS modal are submitted here so
  // validation stays inside the modal and successful changes refresh the page.
  document.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-modal-form]');
    if (!form || !form.dataset.modalReload) return;
    event.preventDefault();
    submitModalForm(form);
  });

  // Fallback for existing modal forms where HTMX is unavailable.
  document.addEventListener('submit', function (event) {
    const form = event.target.closest('[data-modal-form]');
    if (!form || form.dataset.modalReload || window.htmx) return;
    event.preventDefault();
    submitModalForm(form);
  });

  window.kisModal = {open: open, close: close};
})();


/* Ajout d'un document : la liste des élèves suit la classe choisie, et les
   libellés suivent la catégorie. Gestion déléguée : fonctionne aussi dans la
   fenêtre modale, où les scripts du formulaire chargé ne s'exécutent pas. */
(function () {
  function labels(form) {
    const category = form.querySelector('[name="category"]');
    const cl = form.querySelector('#document-classe-label');
    const st = form.querySelector('#document-student-label');
    if (!category || !cl || !st) return;
    const c = category.value;
    if (c === 'STUDENT') { cl.textContent = 'Classe de l’élève'; st.textContent = 'Élève concerné'; }
    else if (c === 'PEDAGOGY') { cl.textContent = 'Classe concernée'; st.textContent = 'Élève concerné (facultatif)'; }
    else if (c === 'FINANCE') { cl.textContent = 'Classe concernée'; st.textContent = 'Élève concerné'; }
    else { cl.textContent = 'Classe concernée (facultatif)'; st.textContent = 'Élève concerné (facultatif)'; }
  }
  document.addEventListener('change', function (event) {
    const form = event.target.closest && event.target.closest('form[data-document-form]');
    if (!form) return;
    if (event.target.name === 'category') labels(form);
    if (event.target.name !== 'classe') return;
    const student = form.querySelector('select[name="student"]');
    if (!student) return;
    if (!event.target.value) { student.innerHTML = '<option value="">—</option>'; return; }
    student.innerHTML = '<option value="">Chargement…</option>';
    const url = form.dataset.studentsUrl.replace(/\/0\/students\/$/, '/' + encodeURIComponent(event.target.value) + '/students/');
    fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
      .then(function (html) { student.innerHTML = html; })
      .catch(function () { student.innerHTML = '<option value="">Liste des élèves indisponible</option>'; });
  });
  document.addEventListener('focusin', function (event) {
    const form = event.target.closest && event.target.closest('form[data-document-form]');
    if (form && !form.dataset.labelsReady) { form.dataset.labelsReady = '1'; labels(form); }
  });
})();
