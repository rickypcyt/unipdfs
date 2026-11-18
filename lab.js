(() => {
  const $ = (id) => document.getElementById(id);
  const lab = document.createElement('div');
  lab.id = 'lab';
  lab.innerHTML = `
    <div class="lab-bar">
      <button id="labClose">← Volver</button>
      <select id="labFiles" title="Archivos .tex y .md"></select>
      <button id="labNew">Nuevo .tex</button>
      <button id="labSave">Guardar</button>
      <button id="labCompile" class="primary" title="Ctrl+Enter">Compilar → PDF</button>
      <span class="sep"></span>
      <button id="labToMd" title="Convierte el PDF abierto en el visor (o el último compilado) a Markdown">PDF → Markdown</button>
      <button id="labToTex" title="Genera un .tex final desde el Markdown abierto">Markdown → LaTeX</button>
      <button id="labPrint" title="Abre el PDF para imprimir">Imprimir PDF</button>
      <span class="status" id="labStatus"></span>
    </div>
    <div class="lab-body">
      <div class="pane"><textarea id="labEditor" spellcheck="false" placeholder="Crea o abre un .tex / .md"></textarea><pre id="labLog"></pre></div>
      <div class="pane"><iframe id="labPreview" title="Vista previa"></iframe><div id="labMd"></div></div>
    </div>`;
  document.body.appendChild(lab);

  const ed = $('labEditor'), status = $('labStatus'), logEl = $('labLog');
  let cur = null, lastPdf = null, dirty = false;

  const say = (t, err) => { status.textContent = t; status.className = 'status' + (err ? ' err' : ''); };
  const api = async (url, body) => {
    const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' });
    return r.json();
  };
  const isMd = () => cur && cur.toLowerCase().endsWith('.md');
  const pdfSrc = (p, m) => '/files/' + p.split('/').map(encodeURIComponent).join('/') + '?v=' + (m || Date.now()) + '#view=FitH';

  function showPane() {
    const md = isMd();
    $('labPreview').style.display = md ? 'none' : '';
    $('labMd').style.display = md ? 'block' : 'none';
    $('labCompile').disabled = !!md || !cur;
    $('labToTex').disabled = !md;
  }

  function renderMd() {
    const box = $('labMd');
    if (window.marked) box.innerHTML = window.marked.parse(ed.value);
    else box.innerHTML = '<pre style="white-space:pre-wrap"></pre>', box.firstChild.textContent = ed.value;
  }

  async function refreshList(select) {
    const d = await api('/api/tex-files');
    const sel = $('labFiles');
    sel.innerHTML = '<option value="">— elige archivo —</option>' +
      (d.files || []).map((f) => `<option value="${f.path}">${f.path}</option>`).join('');
    if (select) {
      if (![...sel.options].some((o) => o.value === select)) sel.insertAdjacentHTML('beforeend', `<option value="${select}">${select}</option>`);
      sel.value = select;
    }
  }

  async function open(path) {
    if (dirty && !confirm('Hay cambios sin guardar. ¿Descartarlos?')) { $('labFiles').value = cur || ''; return; }
    const d = await api('/api/tex-read?path=' + encodeURIComponent(path));
    if (!d.ok) return say(d.error, true);
    cur = path; ed.value = d.content; dirty = false;
    await refreshList(path);
    showPane();
    if (isMd()) renderMd();
    else $('labPreview').src = pdfSrc(path.replace(/\.tex$/i, '.pdf'));
    say(path);
  }

  async function save() {
    if (!cur) return false;
    const d = await api('/api/tex-save', { path: cur, content: ed.value });
    if (d.ok) { dirty = false; say('Guardado ' + new Date().toLocaleTimeString()); }
    else say(d.error, true);
    return d.ok;
  }

  async function compile() {
    if (!cur || isMd()) return;
    say('Compilando… (la primera vez descarga paquetes)');
    $('labCompile').disabled = true;
    try {
      const d = await api('/api/tex-compile', { path: cur, content: ed.value });
      dirty = false;
      logEl.textContent = d.log || '';
      logEl.style.display = d.ok ? 'none' : 'block';
      if (d.ok) { lastPdf = d.pdf; $('labPreview').src = pdfSrc(d.pdf, d.mtime); say('Compilado ' + new Date().toLocaleTimeString()); }
      else say('Error de compilación (ver registro)', true);
    } catch (e) { say(String(e), true); }
    $('labCompile').disabled = false;
  }

  $('labClose').onclick = () => lab.classList.remove('open');
  $('labFiles').onchange = (e) => e.target.value && open(e.target.value);
  $('labSave').onclick = save;
  $('labCompile').onclick = compile;
  ed.addEventListener('input', () => { dirty = true; if (isMd()) renderMd(); });
  ed.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') { e.preventDefault(); document.execCommand('insertText', false, '  '); }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); compile(); }
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); }
  });

  $('labNew').onclick = async () => {
    const name = prompt('Ruta del nuevo archivo (ej. Redes/apuntes.tex):', ((document.getElementById('subject') || {}).value || 'Asignatura') + '/nuevo.tex');
    if (!name) return;
    const d = await api('/api/tex-new', { path: name });
    if (!d.ok) return say(d.error, true);
    dirty = false; await open(d.path);
  };

  $('labToMd').onclick = async () => {
    const src = (typeof currentPath !== 'undefined' && currentPath) || lastPdf;
    if (!src) return say('Abre un PDF en el visor o compila uno primero', true);
    say('Convirtiendo ' + src + ' a Markdown…');
    const d = await api('/api/pdf-to-md', { path: src });
    if (!d.ok) return say(d.error, true);
    dirty = false; await open(d.path);
  };

  $('labToTex').onclick = async () => {
    if (!isMd()) return;
    await save();
    const d = await api('/api/md-to-tex', { path: cur });
    if (!d.ok) return say(d.error, true);
    dirty = false; await open(d.path); say('Generado ' + d.path + ' — ya puedes compilarlo');
  };

  $('labPrint').onclick = () => {
    const pdf = isMd() ? lastPdf : (cur || '').replace(/\.tex$/i, '.pdf');
    if (pdf) window.open(pdfSrc(pdf).replace('#view=FitH', ''), '_blank');
  };

  window.openLab = async () => { lab.classList.add('open'); await refreshList(cur); showPane(); };
  window.addEventListener('beforeunload', (e) => { if (dirty) e.preventDefault(); });

  const btn = document.createElement('button');
  btn.textContent = 'Taller LaTeX';
  btn.className = 'panel-toggle';
  btn.onclick = window.openLab;
  document.querySelector('.toolbar-left').appendChild(btn);

  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js';
  s.onload = () => { if (isMd()) renderMd(); };
  document.head.appendChild(s);
})();
