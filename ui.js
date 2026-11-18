// Modales propios (sustituyen a alert / confirm / prompt del navegador).
(() => {
  const css = document.createElement('style');
  css.textContent = `
    .ui-backdrop{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:rgba(16,24,40,.45);font-family:Inter,Segoe UI,Arial,sans-serif}
    .ui-modal{width:min(420px,92vw);padding:20px;border-radius:12px;background:#fff;color:#17202a;box-shadow:0 20px 50px rgba(16,24,40,.3)}
    .ui-modal h3{margin:0 0 8px;font-size:16px}
    .ui-modal p{margin:0 0 14px;font-size:14px;line-height:1.5;color:#475467;white-space:pre-wrap}
    .ui-modal input{width:100%;margin-bottom:14px;padding:10px 12px;border:1px solid #d9dee7;border-radius:8px;font:inherit;font-size:14px}
    .ui-modal input:focus{outline:2px solid #155eef;border-color:#155eef}
    .ui-actions{display:flex;justify-content:flex-end;gap:8px}
    .ui-actions button{padding:8px 14px;border:1px solid #d9dee7;border-radius:8px;background:#fff;font:inherit;font-size:14px;font-weight:600;cursor:pointer}
    .ui-actions button.ui-ok{background:#155eef;border-color:#155eef;color:#fff}
    .ui-actions button.ui-danger{background:#d92d20;border-color:#d92d20;color:#fff}
  `;
  document.head.appendChild(css);

  function modal({ title, message, input, value, okText = 'Aceptar', cancelText = 'Cancelar', cancel = true, danger = false }) {
    return new Promise((resolve) => {
      const back = document.createElement('div');
      back.className = 'ui-backdrop';
      const box = document.createElement('div');
      box.className = 'ui-modal';
      box.setAttribute('role', 'dialog');
      box.setAttribute('aria-modal', 'true');
      if (title) { const h = document.createElement('h3'); h.textContent = title; box.appendChild(h); }
      if (message) { const p = document.createElement('p'); p.textContent = message; box.appendChild(p); }
      let field = null;
      if (input) { field = document.createElement('input'); field.value = value || ''; box.appendChild(field); }
      const actions = document.createElement('div');
      actions.className = 'ui-actions';
      const done = (result) => { back.remove(); document.removeEventListener('keydown', onKey, true); resolve(result); };
      if (cancel) {
        const c = document.createElement('button');
        c.textContent = cancelText;
        c.onclick = () => done(input ? null : false);
        actions.appendChild(c);
      }
      const ok = document.createElement('button');
      ok.textContent = okText;
      ok.className = danger ? 'ui-danger' : 'ui-ok';
      ok.onclick = () => done(input ? field.value : true);
      actions.appendChild(ok);
      box.appendChild(actions);
      back.appendChild(box);
      back.addEventListener('mousedown', (e) => { if (e.target === back && cancel) done(input ? null : false); });
      const onKey = (e) => {
        if (e.key === 'Escape' && cancel) { e.stopPropagation(); done(input ? null : false); }
        if (e.key === 'Enter' && (input || e.target === ok)) { e.preventDefault(); e.stopPropagation(); ok.click(); }
      };
      document.addEventListener('keydown', onKey, true);
      document.body.appendChild(back);
      (field || ok).focus();
      if (field) field.select();
    });
  }

  window.uiAlert = (message, title = 'Aviso') => modal({ title, message, cancel: false });
  window.uiConfirm = (message, opts = {}) => modal({ title: opts.title || 'Confirmar', message, okText: opts.okText || 'Aceptar', danger: opts.danger });
  window.uiPrompt = (title, value = '', message = '') => modal({ title, message, input: true, value, okText: 'Guardar' });
})();
