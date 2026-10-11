(function () {
  'use strict';
  var body = document.body;
  var CSRF = body.dataset.csrf;
  var MOD = body.dataset.mod;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- utilidades ---------- */
  function toast(msg, cls) {
    var box = $('.toasts');
    if (!box) return;
    var t = document.createElement('div');
    t.className = 'toast ' + (cls || '');
    t.textContent = msg;
    box.appendChild(t);
    setTimeout(function () { t.remove(); }, 6000);
  }
  function post(url, data) {
    var fd = data instanceof FormData ? data : new FormData();
    if (!(data instanceof FormData) && data) Object.keys(data).forEach(function (k) { fd.append(k, data[k]); });
    return fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRF-Token': CSRF, 'X-Requested-With': 'fetch' }, credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return { ok: false, message: 'Respuesta inesperada del servidor.' }; }); })
      .catch(function () { return { ok: false, message: 'No se pudo conectar con el servidor.' }; });
  }
  function clearErrors(scope) {
    $$('[data-err]', scope).forEach(function (e) { e.textContent = ''; if (e.classList.contains('alert')) e.hidden = true; });
    $$('.has-err', scope).forEach(function (f) { f.classList.remove('has-err'); });
  }
  function showErrors(scope, errors, message) {
    clearErrors(scope);
    var shown = false;
    Object.keys(errors || {}).forEach(function (k) {
      var el = $('[data-err="' + k + '"]', scope);
      if (el) {
        el.textContent = errors[k]; if (el.classList.contains('alert')) el.hidden = false;
        var f = el.closest('.field'); if (f) f.classList.add('has-err'); shown = true;
      }
    });
    if (!shown && message) { var all = $('[data-err="__all__"]', scope); if (all) { all.textContent = message; all.hidden = false; } else toast(message, 'bad'); }
    else if (message) toast(message, 'bad');
  }
  function openDlg(id) { var d = document.getElementById(id); if (d && !d.open) d.showModal(); return d; }

  function confirmDlg(o) {
    var d = $('#dlg-confirm');
    $('#cf-title').textContent = o.title || 'Confirmar';
    $('#cf-text').textContent = o.text || '';
    $('#cf-ok').textContent = o.ok || 'Confirmar';
    var wrap = $('#cf-reason-wrap'); wrap.hidden = !o.reason; $('#cf-reason').value = ''; $('#cf-err').textContent = '';
    d.showModal();
    return new Promise(function (resolve) {
      var ok = $('#cf-ok');
      function done(v) { ok.removeEventListener('click', onOk); d.removeEventListener('close', onClose); resolve(v); }
      function onOk() {
        if (o.reason && !$('#cf-reason').value.trim()) { $('#cf-err').textContent = 'El motivo es obligatorio.'; return; }
        var v = { reason: $('#cf-reason').value.trim() }; d.close(); done(v);
      }
      function onClose() { done(null); }
      ok.addEventListener('click', onOk); d.addEventListener('close', onClose);
    });
  }

  /* ---------- barra lateral ---------- */
  try { if (localStorage.getItem('side-collapsed') === '1') body.classList.add('collapsed'); } catch (e) {}
  function closeSide() { body.classList.remove('side-open'); var s = $('.scrim[data-action="close-side"]'); if (s) s.hidden = true; }

  /* ---------- panel de detalle ---------- */
  var current = { id: null, tab: 'resumen' };
  function openDetail(id, keepTab) {
    var drawer = $('#drawer'); if (!drawer) return;
    current.id = id; if (!keepTab) current.tab = 'resumen';
    fetch('/m/' + MOD + '/' + id + '/detalle', { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error(); return r.text(); })
      .then(function (html) {
        $('#drawer-body').innerHTML = html; drawer.hidden = false; $('.drawer-scrim').hidden = false;
        selectTab(current.tab);
        var c = $('.dr-head .icon-btn', drawer); if (c) c.focus();
      })
      .catch(function () { toast('No se pudo cargar el detalle.', 'bad'); });
  }
  function closeDrawer() { var d = $('#drawer'); if (d) d.hidden = true; var s = $('.drawer-scrim'); if (s) s.hidden = true; current.id = null; }
  function selectTab(name) {
    var root = $('#drawer-body'); if (!root) return;
    var has = $('[data-tab="' + name + '"]', root); if (!has) name = 'resumen';
    current.tab = name;
    $$('.tab', root).forEach(function (t) { var on = t.dataset.tab === name; t.classList.toggle('on', on); t.setAttribute('aria-selected', on); });
    $$('.tabpanel', root).forEach(function (p) { p.hidden = p.dataset.panel !== name; });
  }

  /* ---------- formulario crear / editar ---------- */
  function openForm(id) {
    var dlg = $('#dlg-form'); if (!dlg) return;
    var form = $('#form'); form.reset(); clearErrors(form);
    form.elements.id.value = id || '';
    $('#form-title').textContent = (id ? 'Editar ' : (MOD === 'incidentes' && !$('#f-estado') ? 'Reportar ' : 'Nuevo ')) + dlg.dataset.singular;
    dlg.showModal();
    if (id) {
      fetch('/m/' + MOD + '/' + id + '/json', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (data) {
        Object.keys(data).forEach(function (k) {
          var el = form.elements[k]; if (!el || el.type === 'file') return;
          el.value = data[k] === null ? '' : data[k];
        });
      });
    }
  }
  var formEl = $('#form');
  if (formEl) formEl.addEventListener('submit', function (e) {
    e.preventDefault();
    var btn = $('#form-save'); btn.disabled = true; btn.textContent = 'Guardando…';
    post(formEl.action, new FormData(formEl)).then(function (res) {
      btn.disabled = false; btn.textContent = 'Guardar';
      if (res.ok) { window.location.reload(); } else { showErrors(formEl, res.errors, res.message); var f = $('.has-err input, .has-err select, .has-err textarea', formEl); if (f) f.focus(); }
    });
  });

  /* ---------- cambio de estado ---------- */
  var estCtx = { id: null };
  function reasonRequired() {
    var cfgEl = $('#reason-cfg'); if (!cfgEl) return false;
    var cfg = JSON.parse(cfgEl.textContent); return cfg.all || cfg.states.indexOf($('#est-nuevo').value) >= 0;
  }
  var estForm = $('#form-estado');
  if (estForm) {
    $('#est-nuevo').addEventListener('change', function () { $('#est-req').hidden = !reasonRequired(); });
    estForm.addEventListener('submit', function (e) {
      e.preventDefault(); clearErrors(estForm);
      post('/m/' + MOD + '/' + estCtx.id + '/estado', new FormData(estForm)).then(function (res) {
        if (res.ok) window.location.reload(); else showErrors(estForm, res.errors, res.message);
      });
    });
  }

  /* ---------- eventos delegados ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-action],[data-post],[data-tab],tr[data-row]');
    var openMenus = $$('.menu-list:not([hidden])');
    if (!e.target.closest('.rowmenu')) openMenus.forEach(function (m) { m.hidden = true; });
    if (!e.target.closest('.popwrap')) $$('.pop').forEach(function (p) { p.hidden = true; });
    if (!t) return;

    if (t.matches('[data-tab]')) { selectTab(t.dataset.tab); return; }
    if (t.matches('[data-post]')) {
      var run = function () { post(t.dataset.post).then(function (r) { toast(r.message || 'Listo', r.ok ? 'ok' : 'bad'); if (r.ok && current.id) openDetail(current.id, true); }); };
      if (t.dataset.confirm) confirmDlg({ title: 'Confirmar acción', text: t.dataset.confirm, ok: 'Sí, continuar' }).then(function (v) { if (v) run(); }); else run();
      return;
    }
    if (t.matches('tr[data-row]')) {
      if (e.target.closest('.act,a,button')) return;
      if ($('[data-action="detail"]', t)) openDetail(t.dataset.id); return;
    }
    var ml = t.closest('.menu-list'); if (ml) ml.hidden = true;
    var a = t.dataset.action, id = t.dataset.id;
    switch (a) {
      case 'toggle-side': body.classList.toggle('collapsed'); try { localStorage.setItem('side-collapsed', body.classList.contains('collapsed') ? '1' : '0'); } catch (x) {} break;
      case 'open-side': body.classList.add('side-open'); $('.scrim[data-action="close-side"]').hidden = false; break;
      case 'close-side': closeSide(); break;
      case 'menu': var l = t.nextElementSibling; var was = l.hidden; $$('.menu-list').forEach(function (m) { m.hidden = true; }); l.hidden = !was; break;
      case 'pop': var p = document.getElementById(t.dataset.target); p.hidden = !p.hidden; break;
      case 'new': openForm(null); break;
      case 'edit': openForm(id); break;
      case 'detail': openDetail(id); break;
      case 'close-drawer': closeDrawer(); break;
      case 'estado':
        estCtx.id = id; var d = $('#dlg-estado'); clearErrors(estForm); estForm.reset();
        var sel = $('#est-nuevo'); for (var i = 0; i < sel.options.length; i++) if (sel.options[i].value === t.dataset.actual) sel.selectedIndex = Math.min(i + 1, sel.options.length - 1);
        $('#est-req').hidden = !reasonRequired(); d.showModal(); break;
      case 'delete':
        confirmDlg({ title: 'Eliminar registro', text: 'Esta acción no se puede deshacer y quedará registrada en la auditoría. ¿Deseas continuar?', ok: 'Eliminar' }).then(function (v) {
          if (v) post('/m/' + MOD + '/' + id + '/eliminar').then(function (r) { if (r.ok) window.location.reload(); else toast(r.message, 'bad'); });
        }); break;
      case 'open-dialog': openDlg(t.dataset.target); break;
      case 'close-dialog': var dd = t.closest('dialog'); if (dd) dd.close(); break;
      case 'read-all': post('/notificaciones/leer', { clave: '*' }).then(function () { window.location.reload(); }); break;
      case 'read-one': post('/notificaciones/leer', { clave: t.dataset.key }).then(function () { window.location.reload(); }); break;
      case 'fill-login': $('#email').value = t.dataset.email; $('#password').value = 'Demo2026!'; $('#password').focus(); break;
    }
  });

  // formularios dentro del panel de detalle (asignar, preguntas)
  document.addEventListener('submit', function (e) {
    var f = e.target.closest('form[data-ajax-drawer]'); if (!f) return;
    e.preventDefault(); clearErrors(f);
    post(f.getAttribute('action'), new FormData(f)).then(function (r) {
      if (r.ok) { toast(r.message, 'ok'); if (current.id) openDetail(current.id, true); } else showErrors(f, r.errors || {}, r.message);
    });
  });

  document.addEventListener('change', function (e) { if (e.target.matches('[data-autosubmit]')) e.target.form.submit(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeDrawer(); closeSide(); } });
  $$('.toast').forEach(function (t) { setTimeout(function () { t.remove(); }, 6000); });

  // cerrar diálogos al hacer clic fuera
  $$('dialog').forEach(function (d) { d.addEventListener('mousedown', function (e) { if (e.target === d) d.close(); }); });
})();
