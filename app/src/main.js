// GameDub — tela de revisão. Sem framework: só window.__TAURI__.
const { invoke, convertFileSrc } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const { open } = window.__TAURI__.dialog;

const $ = (s) => document.querySelector(s);
const estado = { work: null, falas: [], pacote: "", sel: null, rodando: false };

// ------------------------------------------------------------ projeto
$("#btn-abrir").onclick = async () => {
  const dir = await open({ directory: true, title: "Pasta work do projeto (com falas.csv)" });
  if (dir) await abrir(dir);
};

async function abrir(work) {
  try {
    const p = await invoke("abrir_projeto", { work });
    estado.work = work;
    estado.falas = p.falas;
    estado.pacote = "";
    estado.sel = null;
    $("#work-path").textContent = work;
    localStorage.setItem("ultimo_work", work);
    renderPacotes();
    renderPersonagens();
    renderTabela();
    renderDetalhe();
    habilitarEtapas();
    log(`projeto aberto: ${p.falas.length} falas`);
  } catch (e) { log(String(e), "err"); }
}

async function recarregar() {
  if (!estado.work) return;
  const p = await invoke("abrir_projeto", { work: estado.work });
  estado.falas = p.falas;
  renderPacotes(); renderPersonagens(); renderTabela(); renderDetalhe();
}

// ------------------------------------------------------------ listas
function renderPacotes() {
  const cont = {};
  for (const f of estado.falas) cont[f.pacote] = (cont[f.pacote] || 0) + 1;
  const ul = $("#lista-pacotes");
  ul.innerHTML = "";
  const todos = document.createElement("li");
  todos.innerHTML = `<span>todos</span><span class="n">${estado.falas.length}</span>`;
  todos.className = estado.pacote === "" ? "ativo" : "";
  todos.onclick = () => { estado.pacote = ""; renderPacotes(); renderTabela(); };
  ul.appendChild(todos);
  for (const [p, n] of Object.entries(cont).sort()) {
    const li = document.createElement("li");
    li.innerHTML = `<span title="${p}">${p.split("/").pop()}</span><span class="n">${n}</span>`;
    li.className = estado.pacote === p ? "ativo" : "";
    li.onclick = () => { estado.pacote = p; renderPacotes(); renderTabela(); };
    ul.appendChild(li);
  }
}

function renderPersonagens() {
  const sel = $("#filtro-personagem");
  const atual = sel.value;
  const nomes = [...new Set(estado.falas.map((f) => f.personagem))].sort();
  sel.innerHTML = `<option value="">todos os personagens</option>` +
    nomes.map((n) => `<option value="${n}">${n}</option>`).join("");
  sel.value = atual;
}

function filtradas() {
  const q = $("#busca").value.trim().toLowerCase();
  const pers = $("#filtro-personagem").value;
  const st = $("#filtro-status").value;
  return estado.falas.filter((f) =>
    (!estado.pacote || f.pacote === estado.pacote) &&
    (!pers || f.personagem === pers) &&
    (!st || (st === "erro" ? f.status.startsWith("erro") : f.status === st)) &&
    (!q || f.id.toLowerCase().includes(q) || f.texto_en.toLowerCase().includes(q) || f.texto_pt.toLowerCase().includes(q)));
}

function renderTabela() {
  const lista = filtradas();
  const tb = $("#tbody");
  tb.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const f of lista.slice(0, 2000)) {           // paginação simples; filtros cobrem o resto
    const tr = document.createElement("tr");
    if (estado.sel && estado.sel.id === f.id) tr.className = "sel";
    const stClass = f.status.startsWith("erro") ? "erro" : f.status;
    tr.innerHTML = `<td>${esc(f.personagem)}</td><td class="txt" title="${esc(f.texto_en)}">${esc(f.texto_en)}</td>` +
      `<td class="txt" title="${esc(f.texto_pt)}">${esc(f.texto_pt)}</td><td>${Number(f.duracao_s).toFixed(1)}s</td>` +
      `<td><span class="st ${stClass}" title="${esc(f.status)}">${esc(f.status.split(":")[0])}</span></td>`;
    tr.onclick = () => { estado.sel = f; renderTabela(); renderDetalhe(); };
    frag.appendChild(tr);
  }
  tb.appendChild(frag);
  $("#contagem").textContent = `${lista.length} falas${lista.length > 2000 ? " (mostrando 2000)" : ""}`;
}
["#busca", "#filtro-personagem", "#filtro-status"].forEach((s) => ($(s).oninput = renderTabela));

// ------------------------------------------------------------ detalhe
function renderDetalhe() {
  const f = estado.sel;
  $("#detalhe-vazio").hidden = !!f;
  $("#detalhe-conteudo").hidden = !f;
  if (!f) return;
  $("#d-id").textContent = f.id;
  $("#d-personagem").value = f.personagem;
  $("#d-en").textContent = f.texto_en || "(sem transcrição)";
  $("#d-pt").value = f.texto_pt;
  $("#play-pt").disabled = !f.audio_pt;
  medir();
}
$("#d-pt").oninput = medir;
function medir() {
  const f = estado.sel; if (!f) return;
  const en = f.texto_en.length, pt = $("#d-pt").value.length;
  const el = $("#d-medida");
  el.textContent = `${pt} caracteres (original ${en}) · ${Number(f.duracao_s).toFixed(1)}s disponíveis`;
  el.className = pt > en * 1.15 ? "muted estourou" : "muted";
}

$("#btn-salvar").onclick = async () => {
  const f = estado.sel; if (!f) return;
  try {
    await invoke("salvar_fala", { work: estado.work, id: f.id, textoPt: $("#d-pt").value, personagem: $("#d-personagem").value });
    f.texto_pt = $("#d-pt").value; f.personagem = $("#d-personagem").value;
    if (f.status === "transcrito" && f.texto_pt) f.status = "traduzido";
    renderTabela(); renderPersonagens();
    log(`salvo: ${f.id}`, "ok");
  } catch (e) { log(String(e), "err"); }
};

$("#btn-regerar").onclick = async () => {
  const f = estado.sel; if (!f) return;
  await $("#btn-salvar").onclick();
  await invoke("limpar_audio_pt", { work: estado.work, id: f.id });
  f.audio_pt = ""; renderDetalhe();
  await rodar("synth", [estado.work]);
};

function tocar(caminho) {
  if (!caminho) return;
  const p = $("#player");
  p.src = convertFileSrc(caminho);
  p.play().catch((e) => log(`não toquei ${caminho}: ${e}`, "err"));
}
$("#play-orig").onclick = () => estado.sel && tocar(estado.sel.arquivo);
$("#play-pt").onclick = () => estado.sel && tocar(estado.sel.audio_pt);

// ------------------------------------------------------------ etapas
function habilitarEtapas() {
  document.querySelectorAll("button[data-etapa]").forEach((b) => (b.disabled = !estado.work || estado.rodando));
}
document.querySelectorAll("button[data-etapa]").forEach((b) => {
  b.onclick = () => {
    const etapa = b.dataset.etapa;
    const args = etapa === "inject" ? [estado.work, "--out", estado.work + "/../saida"] : [estado.work];
    rodar(etapa, args);
  };
});

async function rodar(etapa, args) {
  if (estado.rodando) return;
  estado.rodando = true; habilitarEtapas();
  log(`▶ ${etapa} ${args.join(" ")}`);
  try {
    const ok = await invoke("rodar_etapa", { etapa, args });
    if (!ok) log(`${etapa} terminou com erro`, "err");
  } catch (e) { log(String(e), "err"); }
  estado.rodando = false; habilitarEtapas();
  await recarregar();
}

listen("progresso", (ev) => {
  const p = ev.payload;
  log(p.linha, p.terminou ? (p.ok ? "ok" : "err") : "");
});

// ------------------------------------------------------------ util
function log(msg, cls = "") {
  const el = $("#log");
  const div = document.createElement("div");
  if (cls) div.className = cls;
  div.textContent = msg;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

const ultimo = localStorage.getItem("ultimo_work");
if (ultimo) abrir(ultimo);
