(() => {
  const $ = (id) => document.getElementById(id);
  const I = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const ICON = {
    back: I('<path d="M19 12H5M12 19l-7-7 7-7"/>'),
    file: I('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
    plus: I('<path d="M12 5v14M5 12h14"/>'),
    save: I('<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>'),
    play: I('<path d="M6 4l14 8-14 8z"/>'),
    swap: I('<path d="M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>'),
    down: I('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>'),
    print: I('<path d="M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6a1 1 0 0 1-1 1h-2"/><path d="M7 14h10v7H7z"/>'),
    chev: I('<path d="M6 9l6 6 6-6"/>'),
  };

  const lab = document.createElement('div');
  lab.id = 'lab';
  lab.innerHTML = `
    <div class="lab-bar">
      <button class="btn sec" id="labClose" title="Volver al visor">${ICON.back}<span class="lbl">Volver</span></button>
      <span class="sep"></span>
      <label class="file-pick" title="Abrir otro archivo .tex / .md">
        <span class="file-chip">${ICON.file}<span class="fname" id="labName"><i>Ningún archivo abierto</i></span><span class="dot" title="Cambios sin guardar"></span></span>
        <select id="labFiles"></select>
      </label>
      <button class="btn icon" id="labNew" title="Nuevo .tex">${ICON.plus}</button>

      <div class="group right">
        <button class="btn" id="labSave" title="Guardar (Ctrl+S)">${ICON.save}<span class="lbl">Guardar</span></button>
        <button class="btn primary" id="labCompile" title="Compilar a PDF (Ctrl+Enter)">${ICON.play}<span class="lbl">Compilar</span> <kbd>Ctrl+↵</kbd></button>
        <span class="sep"></span>
        <div class="menu" id="labMenu">
          <button class="btn sec" id="labConvert" title="Convertir entre PDF, Markdown y LaTeX">${ICON.swap}<span class="lbl">Convertir</span>${ICON.chev}</button>
          <div class="menu-list">
            <button class="menu-item" id="labToMd"><b>PDF → Markdown</b><span>Convierte el PDF abierto en el visor (o el último compilado) en un .md limpio.</span></button>
            <button class="menu-item" id="labToTex"><b>Markdown → LaTeX</b><span>Genera el .tex final desde el Markdown abierto.</span></button>
          </div>
        </div>
        <a class="btn sec" id="labDownload" title="Descargar el PDF" download>${ICON.down}<span class="lbl">Descargar</span></a>
        <button class="btn sec" id="labPrint" title="Abrir el PDF para imprimir">${ICON.print}<span class="lbl">Imprimir</span></button>
      </div>
    </div>

    <div class="lab-body">
      <div class="pane">
        <textarea id="labEditor" spellcheck="false" placeholder="Abre un archivo con la lista de arriba, o crea uno nuevo con +"></textarea>
        <div class="log" id="labLogBox">
          <div class="log-head"><b>Error de compilación</b><span class="grow" id="labLogSummary"></span><button id="labLogClose">Cerrar ✕</button></div>
          <pre id="labLog"></pre>
        </div>
      </div>
      <div class="pane"><iframe id="labPreview" title="Vista previa"></iframe><div id="labMd"></div></div>
    </div>

    <div class="lab-foot">
      <span class="pill" id="labStatus">Listo</span>
      <label class="switch" title="Guarda y compila solo, 2 s después de dejar de escribir"><input type="checkbox" id="labAuto"> Compilar automáticamente</label>
      <span class="grow"></span>
      <span id="labCount"></span>
      <span>Ctrl+S guardar · Ctrl+Enter compilar</span>
    </div>`;
  (document.querySelector('main') || document.body).appendChild(lab);

  const ed = $('labEditor'), status = $('labStatus'), logBox = $('labLogBox'), logEl = $('labLog');
  let cur = null, lastPdf = null, published = null, dirty = false, compiling = false, autoTimer = null;

  // ---- estado visual ----
  const say = (text, kind = '') => { status.textContent = text; status.className = 'pill ' + kind; };
  const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const setDirty = (value) => {
    dirty = value;
    lab.classList.toggle('dirty', value);
    if (value && !compiling) say('Sin guardar', 'warn');
  };
  const refreshCount = () => {
    const lines = ed.value ? ed.value.split('\n').length : 0;
    $('labCount').textContent = cur ? `${lines.toLocaleString('es')} líneas · ${ed.value.length.toLocaleString('es')} caracteres` : '';
  };
  const setName = () => {
    const box = $('labName');
    if (!cur) { box.innerHTML = '<i>Ningún archivo abierto</i>'; return; }
    const parts = cur.split('/');
    const name = parts.pop();
    box.textContent = '';
    if (parts.length) { const s = document.createElement('span'); s.textContent = parts.join(' › ') + ' › '; box.appendChild(s); }
    const b = document.createElement('b'); b.textContent = name; box.appendChild(b);
    box.title = cur;
  };
  const pdfOf = () => (isMd() ? lastPdf : (cur || '').replace(/\.tex$/i, '.pdf'));
  const syncButtons = () => {
    const md = isMd();
    $('labPreview').style.display = md ? 'none' : '';
    $('labMd').style.display = md ? 'block' : 'none';
    $('labCompile').disabled = !!md || !cur || compiling;
    $('labSave').disabled = !cur;
    $('labToTex').disabled = !md;
    const pdf = pdfOf();
    $('labDownload').style.pointerEvents = pdf ? '' : 'none';
    $('labDownload').style.opacity = pdf ? '' : '.45';
    $('labPrint').disabled = !pdf;
    // Si el PDF se publicó en el tema ("<original> VersionLatex.pdf") se descarga/imprime ese; si no, el compilado.
    const target = (!isMd() && published) || pdf;
    if (target) { $('labDownload').href = pdfSrc(target).split('#')[0].split('?')[0]; $('labDownload').download = target.split('/').pop(); }
  };

  const api = async (url, body) => {
    const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' });
    const t = await r.text();
    try { return JSON.parse(t); }
    catch (e) { return { ok: false, error: 'Servidor antiguo: cierra iniciar.bat y vuelve a ejecutarlo' }; }
  };
  const showPdf = (url) => { const f = $('labPreview'); f.removeAttribute('srcdoc'); f.src = url; };
  const isMd = () => cur && cur.toLowerCase().endsWith('.md');
  const pdfSrc = (p, m) => '/files/' + p.split('/').map(encodeURIComponent).join('/') + '?v=' + (m || Date.now()) + '#view=FitH';

  function renderMd() {
    const box = $('labMd');
    if (window.marked) box.innerHTML = window.marked.parse(ed.value);
    else { box.innerHTML = '<pre style="white-space:pre-wrap"></pre>'; box.firstChild.textContent = ed.value; }
  }

  async function refreshList(select) {
    const d = await api('/api/tex-files');
    const sel = $('labFiles');
    sel.innerHTML = '<option value="">Abrir archivo…</option>' +
      (d.files || []).map((f) => `<option value="${f.path}">${f.path}</option>`).join('');
    if (select) {
      if (![...sel.options].some((o) => o.value === select)) sel.insertAdjacentHTML('beforeend', `<option value="${select}">${select}</option>`);
      sel.value = select;
    }
  }

  async function open(path) {
    if (dirty && !(await uiConfirm('Hay cambios sin guardar. ¿Descartarlos?', { title: 'Cambios sin guardar', okText: 'Descartar', danger: true }))) { $('labFiles').value = cur || ''; return; }
    const d = await api('/api/tex-read?path=' + encodeURIComponent(path));
    if (!d.ok) return say(d.error, 'err');
    cur = path; ed.value = d.content; setDirty(false); published = null;
    logBox.classList.remove('show');
    setName(); refreshCount();
    await refreshList(path);
    syncButtons();
    if (isMd()) { renderMd(); say('Listo', 'ok'); return; }
    // El PDF compilado se guarda junto al .tex: si existe y está al día se muestra sin recompilar.
    const pdf = path.replace(/\.tex$/i, '.pdf');
    const state = d.pdf || {};
    if (state.exists && !state.stale) {
      lastPdf = pdf; published = state.published || null; syncButtons();
      showPdf(pdfSrc(pdf, state.mtime)); say('PDF guardado · sin recompilar', 'ok');
    }
    else {
      $('labPreview').srcdoc = '<p style="font:15px Segoe UI,Arial,sans-serif;color:#667085;padding:24px">' +
        (state.stale ? 'El .tex cambió desde la última compilación: recompilando…' : 'Generando el PDF por primera vez…') + '</p>';
      compile();
    }
  }

  async function save() {
    if (!cur) return false;
    const d = await api('/api/tex-save', { path: cur, content: ed.value });
    if (d.ok) { setDirty(false); say('Guardado ' + stamp(), 'ok'); }
    else say(d.error, 'err');
    return d.ok;
  }

  function summarize(log) {
    const lines = (log || '').split('\n');
    const bang = lines.findIndex((l) => l.startsWith('!'));
    if (bang >= 0) return lines.slice(bang, bang + 2).join(' ').slice(0, 160);
    const err = lines.find((l) => /error/i.test(l));
    return (err || lines.filter(Boolean).pop() || '').slice(0, 160);
  }

  async function compile() {
    if (!cur || isMd() || compiling) return;
    clearTimeout(autoTimer);
    compiling = true; syncButtons();
    say('Compilando… (la primera vez descarga paquetes)', 'busy');
    try {
      const d = await api('/api/tex-compile', { path: cur, content: ed.value });
      setDirty(false);
      logEl.textContent = d.log || d.error || '';
      logBox.classList.toggle('show', !d.ok);
      $('labLogSummary').textContent = d.ok ? '' : summarize(d.log || d.error);
      if (d.ok) {
        lastPdf = d.pdf; published = d.published || null;
        showPdf(pdfSrc(d.pdf, d.mtime));
        say(published ? 'Compilado · guardado como ' + published.split('/').pop() : 'Compilado ' + stamp(), 'ok');
      }
      else {
        say('Error de compilación', 'err');
        const f = $('labPreview');
        if (f.srcdoc) f.srcdoc = '<p style="font:15px Segoe UI,Arial,sans-serif;color:#b42318;padding:24px">No se pudo generar el PDF. Corrige el error del registro y pulsa Compilar.</p>';
      }
    } catch (e) { say(String(e), 'err'); }
    compiling = false; syncButtons();
  }

  // ---- eventos ----
  $('labClose').onclick = () => lab.classList.remove('open');
  $('labFiles').onchange = (e) => e.target.value && open(e.target.value);
  $('labSave').onclick = save;
  $('labCompile').onclick = compile;
  $('labLogClose').onclick = () => logBox.classList.remove('show');

  ed.addEventListener('input', () => {
    setDirty(true); refreshCount();
    if (isMd()) renderMd();
    clearTimeout(autoTimer);
    if ($('labAuto').checked && !isMd() && cur) autoTimer = setTimeout(compile, 2000);
  });
  lab.addEventListener('keydown', (e) => {
    if (e.target === ed && e.key === 'Tab') { e.preventDefault(); document.execCommand('insertText', false, '  '); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); compile(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); }
  });
  try { $('labAuto').checked = localStorage.getItem('labAuto') === '1'; } catch (e) { /* sin almacenamiento */ }
  $('labAuto').onchange = () => { try { localStorage.setItem('labAuto', $('labAuto').checked ? '1' : '0'); } catch (e) { /* ignorar */ } };

  // menú Convertir
  const menu = $('labMenu');
  $('labConvert').onclick = (e) => { e.stopPropagation(); menu.classList.toggle('open'); };
  document.addEventListener('click', () => menu.classList.remove('open'));

  $('labNew').onclick = async () => {
    const subject = (cur || (typeof currentPath !== 'undefined' && currentPath) || 'Asignatura').split('/')[0];
    const name = await uiPrompt('Nuevo archivo .tex', subject + '/nuevo.tex', 'Ruta dentro de tu carpeta fuente, p. ej. Redes/apuntes.tex');
    if (!name) return;
    const d = await api('/api/tex-new', { path: name });
    if (!d.ok) return say(d.error, 'err');
    setDirty(false); await open(d.path);
  };

  $('labToMd').onclick = async () => {
    menu.classList.remove('open');
    const src = (typeof currentPath !== 'undefined' && currentPath) || lastPdf;
    if (!src) return uiAlert('Abre un PDF en el visor de la izquierda (o compila uno) y vuelve a intentarlo.', 'No hay PDF');
    say('Convirtiendo ' + src.split('/').pop() + ' a Markdown…', 'busy');
    const d = await api('/api/pdf-to-md', { path: src });
    if (!d.ok) return say(d.error, 'err');
    setDirty(false); await open(d.path);
  };

  $('labToTex').onclick = async () => {
    menu.classList.remove('open');
    if (!isMd()) return;
    await save();
    say('Generando LaTeX…', 'busy');
    const d = await api('/api/md-to-tex', { path: cur });
    if (!d.ok) return say(d.error, 'err');
    setDirty(false); await open(d.path); say('Generado ' + d.path.split('/').pop(), 'ok');
  };

  $('labPrint').onclick = () => {
    const pdf = (!isMd() && published) || pdfOf();
    if (pdf) window.open(pdfSrc(pdf).replace('#view=FitH', ''), '_blank');
  };

  window.openLab = async () => { lab.classList.add('open'); await refreshList(cur); syncButtons(); };
  window.closeLab = () => lab.classList.remove('open');
  window.openLabFile = async (path) => { lab.classList.add('open'); await open(path); };
  window.addEventListener('beforeunload', (e) => { if (dirty) e.preventDefault(); });

  const btn = document.createElement('button');
  btn.textContent = 'Taller LaTeX';
  btn.className = 'panel-toggle';
  btn.onclick = window.openLab;
  document.querySelector('.toolbar-left').appendChild(btn);

  syncButtons(); setName();

  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js';
  s.onload = () => { if (isMd()) renderMd(); };
  document.head.appendChild(s);
})();
