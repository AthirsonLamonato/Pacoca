"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const token =
  new URLSearchParams(location.hash.slice(1)).get("token") ||
  sessionStorage.getItem("pacoca-token") ||
  "";
if (token) {
  sessionStorage.setItem("pacoca-token", token);
  history.replaceState(null, "", location.pathname);
}
const state = {
  page: "chat",
  cid: null,
  activeRun: null,
  status: null,
  settings: {},
  ws: null,
  connected: false,
  speech: false,
  voice: false,
  generating: false,
  automaticVoice: false,
  firstWakeUtterance: false,
  pendingWakeChunks: null,
  wakeCommandFrames: 0,
  voiceEpoch: 0,
  lastVoiceActivity: 0,
  captureStarting: null,
  captureEpoch: 0,
  wake: { ws: null, ready: false, ring: [], packet: [], samples: 0, ack: 0,
    connecting: false, failed: false, paused: false, retryAt: 0, mutedUntil: 0 },
  audioQueue: [],
  player: null,
  playUrl: null,
  ignored: new Set(),
  messages: new Map(),
  chunks: [],
  preRoll: [],
  recording: false,
  silent: 0,
  voiced: 0,
  processing: false,
  stream: null,
  context: null,
  node: null,
  approvals: [],
  currentApproval: null,
  memories: [],
  knowledge: null,
  taskTab: "tasks",
};
const toolLabels = {
  computer_action: 'Conferindo o aplicativo',
  current_time: "Consultando o horário",
  computer_info: "Conhecendo seu computador",
  list_applications: "Encontrando aplicativos",
  open_application: "Abrindo aplicativo",
  list_windows: "Consultando janelas",
  inspect_window: "Lendo a janela",
  focus_window: "Selecionando janela",
  interact_window: "Interagindo com o aplicativo",
  volume: "Ajustando o áudio",
  files: "Consultando seus arquivos",
  write_file: "Salvando arquivo",
  search_knowledge: "Buscando nos seus documentos",
  list_memories: "Consultando minhas lembranças",
  remember: "Guardando uma lembrança",
  forget_memory: "Esquecendo uma lembrança",
  browser: "Trabalhando no navegador",
  create_reminder: "Criando lembrete",
  list_reminders: "Consultando lembretes",
  cancel_reminder: "Cancelando lembrete",
  task_history: "Conferindo o histórico da tarefa",
};
const taskLabels = {
  running: "Em andamento",
  completed: "Concluído",
  failed: "Não concluído",
  cancelled: "Interrompido",
  interrupted: "Precisa de atenção",
  waiting_approval: "Aguardando você",
  unverified: "Não verificado",
};

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function date(value) {
  return new Date(value).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
  });
}
function toast(text, error = false, title = "") {
  const n = el("div", "toast" + (error ? " error" : ""));
  if (title) n.append(el("strong", "", title));
  n.append(el("p", "", text));
  $("#toasts").append(n);
  setTimeout(() => n.remove(), 6500);
}
async function api(path, options = {}) {
  const headers = { "X-Pacoca-Token": token, ...options.headers };
  if (
    options.body &&
    typeof options.body === "object" &&
    !(options.body instanceof ArrayBuffer) &&
    !ArrayBuffer.isView(options.body)
  ) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const r = await fetch("/api" + path, { ...options, headers });
  if (!r.ok) {
    let message = "Não consegui concluir esse pedido.";
    try {
      const j = await r.json();
      message =
        typeof j.detail === "string"
          ? j.detail
          : "Confira os dados informados.";
    } catch {}
    throw Error(message);
  }
  return r;
}
async function json(path, options) {
  return (await api(path, options)).json();
}
function safely(fn) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (e) {
      toast(e.message, true);
      console.error(e);
    }
  };
}
function button(text, cls, fn) {
  const b = el("button", cls, text);
  b.type = "button";
  b.addEventListener("click", safely(fn));
  return b;
}
function empty(target, symbol, title, description) {
  target.replaceChildren();
  const n = el("div", "empty-state");
  n.append(
    el("span", "", symbol),
    el("strong", "", title),
    el("p", "", description),
  );
  target.append(n);
}
function page(name) {
  state.page = name;
  $$(".page").forEach((p) => (p.hidden = p.id !== "page-" + name));
  $$("[data-page]").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === name),
  );
  const titles = {
    chat: "Conversar",
    memory: "Memória",
    knowledge: "Conhecimento",
    tasks: "Atividades",
    settings: "Configurações",
  };
  $("#page-title").textContent = titles[name];
  if (name === "memory") loadMemories();
  if (name === "knowledge") loadKnowledge();
  if (name === "tasks") loadTasks();
  if (name === "settings") loadSettings();
}

function connect() {
  if (!token) {
    toast("Abra a Paçoca pelo aplicativo para entrar no seu espaço.", true);
    return;
  }
  const ws = new WebSocket(
    `ws://${location.host}/events?token=${encodeURIComponent(token)}`,
  );
  state.ws = ws;
  ws.onmessage = (e) => {
    try {
      event(JSON.parse(e.data));
    } catch (err) {
      console.error(err);
    }
  };
  ws.onclose = () => {
    state.connected = false;
    setTimeout(connect, 1800);
  };
  ws.onerror = () => {};
}
async function refreshStatus() {
  try {
    state.status = await json("/status");
    $('#app-version').textContent='Paçoca '+state.status.version;
    if(state.status.update) renderUpdate(state.status.update);
    state.settings = state.status.settings;
    const engine = state.status.engine;
    const ready = engine.status === "ready";
    const label = $("#engine-label");
    label.replaceChildren(
      el(
        "span",
        "status-dot" +
          (ready || engine.status === 'sleeping' ? "" : engine.status === "error" ? " error" : " loading"),
      ),
      document.createTextNode(
        ready
          ? engine.model +
              " · " +
              (engine.backend === "cpu" ? "CPU" : "GPU") +
              " · Local"
          : engine.detail,
      ),
    );
    $("#model-detail").replaceChildren(
      document.createTextNode(engine.model),
      el(
        "small",
        "",
        ready
          ? "Disponível · " +
              (engine.backend === "cpu" ? "Processador" : "Placa de vídeo")
          : engine.detail,
      ),
    );
    $("#profile-name").textContent =
      state.settings.user_name || "Seu espaço pessoal";
    $("#user-avatar").textContent = (state.settings.user_name ||
      "Você")[0].toUpperCase();
    document.body.dataset.theme = state.settings.theme;
    if (!state.settings.onboarding_done && !$("#onboarding").open)
      $("#onboarding").showModal();
    reconcileWake();
  } catch (e) {
    console.warn(e.message);
  }
}

async function loadChats() {
  const rows = await json("/conversations");
  const target = $("#conversation-list");
  target.replaceChildren();
  if (!rows.length) {
    target.append(
      el("div", "empty-recent", "Nossas próximas ideias começam por aqui."),
    );
    return;
  }
  for (const row of rows) {
    const n = el(
      "div",
      "conversation-row" + (state.cid === row.id ? " selected" : ""),
    );
    n.append(
      button(row.title, "", () => openChat(row.id)),
      button("×", "", () => confirmDeleteChat(row)),
    );
    target.append(n);
  }
}
async function confirmDeleteChat(row) {
  modal(
    "Esquecer esta conversa?",
    "As mensagens desta conversa serão apagadas do computador.",
    null,
    [
      { text: "Manter", class: "secondary", fn: closeModal },
      {
        text: "Apagar conversa",
        class: "primary",
        fn: async () => {
          await json("/conversations/" + row.id, { method: "DELETE" });
          if (state.cid === row.id) newChat();
          closeModal();
          await loadChats();
        },
      },
    ],
  );
}
async function openChat(id) {
  stopPlayback();
  if (state.cid && state.cid !== id) await interrupt();
  const row = await json("/conversations/" + id);
  state.cid = id;
  state.activeRun = null;
  state.messages.clear();
  localStorage.setItem("pacoca-conversation", id);
  $("#messages").replaceChildren();
  for (const m of row.messages) {
    addMessage(m.role, m.content, m.id, m.created, m.interrupted);
    if (m.role === "assistant") finishMessage(m.id);
  }
  $("#welcome").hidden = !!row.messages.length;
  $("#messages").hidden = !row.messages.length;
  page("chat");
  loadChats();
  scrollBottom();
}
function newChat() {
  if (state.cid) interrupt();
  state.cid = null;
  state.activeRun = null;
  state.messages.clear();
  localStorage.removeItem("pacoca-conversation");
  $("#messages").replaceChildren();
  $("#messages").hidden = true;
  $("#welcome").hidden = false;
  $("#activity").hidden = true;
  page("chat");
  loadChats();
  $("#prompt").focus();
}
function addMessage(
  role,
  text,
  id,
  created = new Date().toISOString(),
  interrupted = false,
) {
  $("#welcome").hidden = true;
  $("#messages").hidden = false;
  const n = el("article", "message " + role);
  n.dataset.id = id;
  const header = el("div", "message-header");
  if (role === "assistant") {
    const img = el("img");
    img.src = "/static/icon.svg";
    img.alt = "";
    header.append(img, document.createTextNode("Paçoca"));
  } else {
    header.append(
      el(
        "span",
        "avatar",
        (state.settings.user_name || "Você")[0].toUpperCase(),
      ),
      document.createTextNode(state.settings.user_name || "Você"),
    );
  }
  header.append(
    el(
      "time",
      "",
      new Date(created).toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    ),
  );
  const content = el("div", "message-content", text);
  n.append(header, content);
  if (interrupted) n.append(el("div", "message-tools", "Fala interrompida"));
  $("#messages").append(n);
  state.messages.set(id, { element: n, content, text, role });
  return state.messages.get(id);
}
function finishMessage(id) {
  const m = state.messages.get(id);
  if (!m || m.element.querySelector(".message-tools")) return;
  renderAnswer(m.content, m.text);
  const controls = el("div", "message-tools");
  controls.append(
    button("Copiar resposta", "", async () => {
      await navigator.clipboard.writeText(m.text);
      toast("Resposta copiada.");
    }),
  );
  m.element.append(controls);
}
function renderAnswer(target, text) {
  target.replaceChildren();
  const parts = text.split(/(```[\s\S]*?```)/g);
  for (const part of parts) {
    if (part.startsWith("```")) {
      const pre = el("pre", "answer-code");
      pre.append(
        el("code", "", part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")),
      );
      target.append(pre);
    } else {
      for (const bit of part.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)) {
        if (bit.startsWith("**") && bit.endsWith("**"))
          target.append(el("strong", "", bit.slice(2, -2)));
        else if (bit.startsWith("`") && bit.endsWith("`"))
          target.append(el("code", "inline-code", bit.slice(1, -1)));
        else target.append(document.createTextNode(bit));
      }
    }
  }
}
function scrollBottom() {
  const n = $("#messages");
  n.scrollTop = n.scrollHeight;
}
async function send(text) {
  if (!text.trim()) return;
  if (!state.connected)
    throw Error("Estou reconectando. Tente novamente em um instante.");
  await interrupt();
  if (!state.cid) {
    const c = await json("/conversations", { method: "POST" });
    state.cid = c.id;
    localStorage.setItem("pacoca-conversation", c.id);
  }
  const cid = state.cid;
  state.activeRun = null;
  const user = addMessage("user", text, "pending-" + Date.now());
  state.generating = true;
  state.lastVoiceActivity = Date.now();
  let response;
  try {
    response = await json("/chat", {
      method: "POST",
      body: {
        conversation_id: cid,
        text: text.trim(),
        voice: state.voice || state.speech,
      },
    });
  } catch (error) {
    state.generating = false;
    user.element.remove();
    throw error;
  }
  state.activeRun = response.run_id;
  $("#prompt").value = "";
  $("#prompt").style.height = "";
  page("chat");
  loadChats();
  scrollBottom();
}
function stopPlayback() {
  state.audioQueue = [];
  if (state.player) {
    state.player.pause();
    state.player.src = "";
    state.player = null;
  }
  if (state.playUrl) {
    URL.revokeObjectURL(state.playUrl);
    state.playUrl = null;
  }
}
async function interrupt() {
  state.generating = false;
  state.lastVoiceActivity = Date.now();
  const oldRun = state.activeRun;
  if (oldRun) state.ignored.add(oldRun);
  stopPlayback();
  if (oldRun && state.cid && state.ws?.readyState === WebSocket.OPEN)
    state.ws.send(
      JSON.stringify({
        type: "interrupt",
        run_id: oldRun,
        conversation_id: state.cid,
      }),
    );
  state.activeRun = null;
  $("#activity").hidden = true;
}
async function playNext() {
  if (state.player || state.recording || state.processing || !state.audioQueue.length) return;
  const item = state.audioQueue.shift();
  if (state.ignored.has(item.run_id)) return playNext();
  const binary = atob(item.audio);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  const player = new Audio(url);
  state.player = player;
  state.playUrl = url;
  if (state.settings.output_id && player.setSinkId)
    try {
      await player.setSinkId(state.settings.output_id);
    } catch {}
  $("#voice-state").textContent = "Pode me interromper quando quiser";
  player.onended = () => {
    state.lastVoiceActivity = Date.now();
    if (state.ws?.readyState === 1)
      state.ws.send(
        JSON.stringify({
          type: "played",
          run_id: item.run_id,
          text: item.text,
        }),
      );
    URL.revokeObjectURL(url);
    state.player = null;
    state.playUrl = null;
    playNext();
    if (!state.audioQueue.length)
      $("#voice-state").textContent = "Estou ouvindo você";
  };
  player.onerror = () => {
    URL.revokeObjectURL(url);
    state.player = null;
    state.playUrl = null;
    playNext();
  };
  try {
    await player.play();
  } catch {
    state.player = null;
    URL.revokeObjectURL(url);
    toast("Toque no microfone ou na tela para habilitar o áudio.");
  }
}
function event(e) {
  if(e.type==='update'){renderUpdate(e.update);return;}
  if (e.type === "connected") {
    state.connected = true;
    return;
  }
  if (e.type === "reminder") {
    toast(e.text, false, "Seu lembrete");
    return;
  }
  if (e.type === "knowledge_updated") {
    toast(e.message);
    if (state.page === "knowledge") loadKnowledge();
    return;
  }
  if (e.type === "approval_resolved") {
    state.approvals = state.approvals.filter((a) => a.id !== e.id);
    if (state.currentApproval === e.id) {
      closeModal();
      state.currentApproval = null;
      showApproval();
    }
    return;
  }
  if (e.conversation_id !== state.cid) return;
  if (state.ignored.has(e.run_id)) return;
  if (e.type === "interrupted") {
    state.generating = false;
    state.ignored.add(e.run_id);
    stopPlayback();
    $("#activity").hidden = true;
    return;
  }
  if (e.type === "approval") {
    state.approvals.push(e);
    showApproval();
    return;
  }
  if (e.type === "audio") {
    state.audioQueue.push(e);
    playNext();
    return;
  }
  if (e.type === "state") {
    if (e.state !== "idle") {
      state.generating = true;
      state.activeRun = e.run_id;
      $("#activity").hidden = false;
      $("#activity-label").textContent = e.label;
    } else if (state.activeRun === e.run_id) $("#activity").hidden = true;
  }
  if (e.type === "token") {
    let m = state.messages.get(e.run_id);
    if (!m) m = addMessage("assistant", "", e.run_id);
    m.text += e.text;
    m.content.textContent = m.text;
    scrollBottom();
  }
  if (e.type === "tool") {
    let n = $(`[data-tool-run="${e.run_id}-${e.name}"]`);
    if (!n) {
      n = el("div", "tool-chip");
      n.dataset.toolRun = e.run_id + "-" + e.name;
      n.append(
        el("span", "", "✧"),
        el("div", "", toolLabels[e.name] || "Executando ação"),
        el("small", "", "Em andamento"),
      );
      $("#welcome").hidden = true;
      $("#messages").hidden = false;
      $("#messages").append(n);
    }
    n.lastChild.textContent =
      e.state === "running"
        ? "Em andamento"
        : e.state === "completed"
          ? e.result?.data?.verified === false
            ? "Não verificado"
            : "Concluído"
          : "Não concluído";
    scrollBottom();
  }
  if (e.type === "done") {
    state.generating = false;
    state.lastVoiceActivity = Date.now();
    let m = state.messages.get(e.run_id);
    if (!m) m = addMessage("assistant", e.text, e.run_id);
    else {
      m.text = e.text;
      m.content.textContent = e.text;
    }
    finishMessage(e.run_id);
    $("#activity").hidden = true;
    loadChats();
    refreshStatus();
  }
  if (e.type === "error") {
    state.generating = false;
    state.lastVoiceActivity = Date.now();
    $("#activity").hidden = true;
    addMessage("assistant", e.message, "error-" + e.run_id);
    toast(e.message, true);
    scrollBottom();
  }
  if (e.type === "voice_error") toast(e.message, true);
}

function modal(title, subtitle, content, actions = []) {
  const container = $("#modal-content");
  container.replaceChildren(
    el("h2", "modal-heading", title),
    el("p", "modal-subtitle", subtitle),
  );
  if (content) container.append(content);
  if (actions.length) {
    const row = el("div", "modal-actions");
    for (const a of actions) row.append(button(a.text, a.class, a.fn));
    container.append(row);
  }
  if (!$("#modal").open) $("#modal").showModal();
}
function closeModal() {
  $("#modal").close();
}
function showApproval() {
  if (state.currentApproval || !state.approvals.length) return;
  const a = state.approvals[0];
  state.currentApproval = a.id;
  const content = el("div");
  content.append(el("div", "approval-label", "VOCÊ CONTINUA NO CONTROLE"));
  const detail = el("div", "approval-detail");
  const labels = {
    path: "Arquivo",
    content: "Conteúdo",
    action: "Ação",
    url: "Endereço",
    text: "Texto",
    window_id: "Janela",
    ref: "Controle",
    id: "Identificador",
  };
  detail.textContent = Object.entries(a.arguments)
    .filter(([, v]) => v !== "" && v !== null)
    .map(([k, v]) => (labels[k] || k) + ": " + v)
    .join("\n\n");
  content.append(detail);
  const decide = async (allowed) => {
    await json("/approvals/" + a.id, { method: "POST", body: { allowed } });
    closeModal();
  };
  modal(
    a.title,
    "Confira o que vou fazer antes de autorizar. Esta decisão vale para esta ação.",
    content,
    [
      { text: "Agora não", class: "secondary", fn: () => decide(false) },
      { text: "Autorizar ação", class: "primary", fn: () => decide(true) },
    ],
  );
}
$("#modal").addEventListener("cancel", (e) => {
  if (state.currentApproval) {
    e.preventDefault();
    const id = state.currentApproval;
    safely(async () => {
      await json("/approvals/" + id, {
        method: "POST",
        body: { allowed: false },
      });
    })();
  }
});
$(".modal-close").onclick = () => {
  if (state.currentApproval) {
    safely(async () =>
      json("/approvals/" + state.currentApproval, {
        method: "POST",
        body: { allowed: false },
      }),
    )();
  } else closeModal();
};

async function loadMemories() {
  state.memories = await json("/memories");
  renderMemories();
}
function renderMemories() {
  const q = $("#memory-search").value.toLocaleLowerCase();
  const rows = state.memories.filter((m) =>
    m.content.toLocaleLowerCase().includes(q),
  );
  const target = $("#memory-list");
  target.replaceChildren();
  if (!rows.length) {
    empty(
      target,
      "✧",
      "Uma memória construída com você.",
      "Conte algo que gostaria que eu lembrasse. As suas lembranças podem ser editadas ou apagadas a qualquer momento.",
    );
    return;
  }
  for (const m of rows) {
    const n = el("article", "memory-card");
    n.append(el("span", "memory-symbol", "✧"), el("p", "", m.content));
    const meta = el("div", "card-meta");
    meta.append(
      el("span", "", date(m.updated)),
      button("Editar", "", () => editMemory(m)),
      button("Esquecer", "", () => forgetMemory(m)),
    );
    n.append(meta);
    target.append(n);
  }
}
function editMemory(memory = null) {
  const input = el("textarea", "modal-input");
  input.value = memory?.content || "";
  input.maxLength = 2000;
  input.placeholder =
    "Por exemplo: prefiro respostas diretas e trabalho com desenvolvimento.";
  modal(
    memory ? "Vamos ajustar essa lembrança." : "Algo que vale guardar.",
    "Registre uma preferência ou um fato que ajude nas nossas conversas.",
    input,
    [
      { text: "Cancelar", class: "secondary", fn: closeModal },
      {
        text: "Guardar memória",
        class: "primary",
        fn: async () => {
          if (!input.value.trim())
            throw Error("Escreva o que gostaria de guardar.");
          await json("/memories" + (memory ? "/" + memory.id : ""), {
            method: memory ? "PATCH" : "POST",
            body: { content: input.value.trim() },
          });
          closeModal();
          await loadMemories();
          toast("Vou me lembrar disso.");
        },
      },
    ],
  );
  input.focus();
}
function forgetMemory(m) {
  modal(
    "Esquecer essa lembrança?",
    "Ela será removida da memória pessoal. As mensagens da conversa original permanecem no histórico.",
    el("p", "approval-detail", m.content),
    [
      { text: "Manter", class: "secondary", fn: closeModal },
      {
        text: "Esquecer",
        class: "primary",
        fn: async () => {
          await json("/memories/" + m.id, { method: "DELETE" });
          closeModal();
          loadMemories();
        },
      },
    ],
  );
}

async function loadKnowledge() {
  state.knowledge = await json("/knowledge");
  const data = state.knowledge;
  const folders = $("#folder-list");
  folders.replaceChildren();
  data.roots.forEach((path, i) => {
    const n = el("div", "folder-card");
    n.append(el("span", "", "▱"));
    const desc = el("div");
    desc.append(
      el(
        "strong",
        "",
        i === 0
          ? "Espaço de trabalho da Paçoca"
          : path.split(/[\\/]/).filter(Boolean).at(-1),
      ),
      el("small", "", path),
    );
    n.append(desc);
    if (i === 0) n.append(el("span", "badge", "PADRÃO"));
    else n.append(button("Remover acesso", "", () => removeFolder(path)));
    folders.append(n);
  });
  $("#index-state").textContent = data.index.running
    ? "Lendo seus documentos…"
    : data.index.message || data.documents.length + " documentos";
  $("#index-folders").disabled = data.index.running;
  renderDocuments(data.documents);
}
function renderDocuments(rows) {
  const target = $("#document-list");
  target.replaceChildren();
  if (!rows.length) {
    empty(
      target,
      "▧",
      "Dê um lugar para as suas ideias.",
      "Adicione uma pasta e atualize o índice. Posso consultar textos, código, PDF e documentos Word.",
    );
    return;
  }
  for (const d of rows) {
    const n = el("div", "document-row");
    n.append(el("span", "", "▧"));
    const desc = el("div");
    desc.append(el("strong", "", d.title), el("small", "", d.path));
    if (d.excerpt) desc.append(el("p", "", d.excerpt));
    n.append(desc);
    target.append(n);
  }
}
function addFolder() {
  const input = el("input", "modal-input");
  input.style.minHeight = "auto";
  input.placeholder = "C:\\Users\\SeuNome\\Documentos\\Projetos";
  const group = el("div");
  group.append(input);
  if (window.pacocaNative?.chooseFolder)
    group.append(
      button("Escolher no computador…", "text-button", () => {
        window.pacocaNative.chooseFolder((path) => {
          if (path) input.value = path;
        });
      }),
    );
  modal(
    "O que posso conhecer?",
    "Autorize uma pasta para consultar seus arquivos. Subpastas também ficam acessíveis; credenciais conhecidas são ignoradas.",
    group,
    [
      { text: "Cancelar", class: "secondary", fn: closeModal },
      {
        text: "Adicionar pasta",
        class: "primary",
        fn: async () => {
          await json("/knowledge/roots", {
            method: "POST",
            body: { path: input.value.trim() },
          });
          closeModal();
          await loadKnowledge();
          toast(
            "Pasta adicionada. Atualize o índice para consultar os documentos.",
          );
        },
      },
    ],
  );
  input.focus();
}
function removeFolder(path) {
  modal(
    "Remover acesso a essa pasta?",
    "Os arquivos originais permanecem no computador; o índice correspondente será removido.",
    el("p", "approval-detail", path),
    [
      { text: "Manter", class: "secondary", fn: closeModal },
      {
        text: "Remover acesso",
        class: "primary",
        fn: async () => {
          await json("/knowledge/roots", { method: "DELETE", body: { path } });
          closeModal();
          loadKnowledge();
        },
      },
    ],
  );
}
let searchTimer;
$("#knowledge-search").oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(
    safely(async () => {
      const q = $("#knowledge-search").value.trim();
      renderDocuments(
        q
          ? await json("/knowledge/search?q=" + encodeURIComponent(q))
          : state.knowledge.documents,
      );
    }),
    250,
  );
};

async function loadTasks() {
  const rows = await json("/tasks");
  const target = $("#task-list");
  target.replaceChildren();
  if (!rows.length)
    empty(
      target,
      "☷",
      "Vamos fazer coisas acontecerem.",
      "Seus pedidos e os resultados das ações aparecem aqui, com transparência.",
    );
  for (const t of rows) {
    const n = button("", "task-card", () => showTask(t.id));
    n.append(
      el(
        "span",
        "",
        t.status === "completed" ? "✓" : t.status === "running" ? "◌" : "↗",
      ),
    );
    const desc = el("div");
    desc.append(
      el("strong", "", t.request),
      el(
        "small",
        "",
        date(t.created) +
          " · " +
          new Date(t.created).toLocaleTimeString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
          }),
      ),
    );
    n.append(
      desc,
      el("span", "badge " + t.status, taskLabels[t.status] || t.status),
    );
    target.append(n);
  }
  const reminders = await json("/reminders");
  const rtarget = $("#reminder-list");
  rtarget.replaceChildren();
  if (!reminders.length)
    empty(
      rtarget,
      "◷",
      "Pode deixar que eu lembro.",
      "Peça um lembrete com dia e horário. A Paçoca precisa estar aberta para avisar você.",
    );
  for (const r of reminders) {
    const n = el("div", "task-card");
    n.append(el("span", "", "◷"));
    const desc = el("div");
    desc.append(
      el("strong", "", r.text),
      el(
        "small",
        "",
        new Date(r.due).toLocaleString("pt-BR") +
          (r.done ? " · Finalizado" : ""),
      ),
    );
    n.append(
      desc,
      button("Remover", "text-button", async () => {
        await json("/reminders/" + r.id, { method: "DELETE" });
        loadTasks();
      }),
    );
    rtarget.append(n);
  }
}
async function showTask(id) {
  const t = await json("/tasks/" + id);
  const content = el("div");
  content.append(
    el(
      "p",
      "approval-detail",
      t.output || "Este pedido ainda não tem uma resposta final.",
    ),
  );
  for (const e of t.events) {
    if (e.kind === "routing") continue;
    const item = el("div", "document-row");
    const desc = el("div");
    desc.append(
      el(
        "strong",
        "",
        e.kind === "tool"
          ? toolLabels[e.data.name] || e.data.name
          : e.kind === "approval_decision"
            ? e.data.allowed
              ? "Você autorizou a ação"
              : "Você não autorizou a ação"
            : "Aguardando autorização",
      ),
      el("small", "", new Date(e.created).toLocaleTimeString("pt-BR")),
    );
    if (e.kind === "tool")
      desc.append(el("p", "", JSON.stringify(e.data.result, null, 2)));
    item.append(desc);
    content.append(item);
  }
  const actions = [{ text: "Fechar", class: "secondary", fn: closeModal }];
  if (["failed", "cancelled", "interrupted", "unverified"].includes(t.status))
    actions.push({
      text: "Retomar com a Paçoca",
      class: "primary",
      fn: async () => {
        closeModal();
        await openChat(t.conversation_id);
        await send(
          "Quero retomar a tarefa " +
            t.id +
            ". Consulte o histórico dela e os resultados antes de decidir a próxima etapa. Não repita ações já concluídas.",
        );
      },
    });
  modal(t.request, taskLabels[t.status] || t.status, content, actions);
}

async function loadSettings() {
  const s = await json("/settings");
  state.settings = s;
  $("#setting-name").value = s.user_name;
  $("#setting-theme").value = s.theme;
  $("#setting-backend").value = s.backend;
  $('#setting-profile').value=s.model_profile || 'light';
  const advanced=$('#setting-profile option[value="advanced"]');
  advanced.disabled=state.status?.engine?.advanced_available===false;
  advanced.textContent=advanced.disabled ? 'Avançado · 8B (opcional no instalador)' : 'Avançado · 8B';
  $('#setting-threads').value=String(s.cpu_threads || 2);
  $('#setting-idle').value=String(s.idle_seconds || 60);
  $('#setting-game-guard').checked=s.game_guard !== false;
  $('#setting-updates').checked=s.updates_enabled !== false;
  $('#setting-update-exit').checked=s.update_install_on_exit !== false;
  $('#setting-spotify-device').value=s.spotify_device || '';
  $('#application-paths').replaceChildren();
  for(const [key,label] of [['valorant','Valorant'],['cs2','Counter-Strike 2'],['spotify','Spotify']]){
    const row=el('label','',label),input=el('input');
    input.dataset.appPath=key;input.value=s.application_paths?.[key] || '';input.placeholder='Detectar automaticamente';input.maxLength=2000;
    row.append(input);
    if(window.pacocaNative?.chooseApplication){
      const button=el('button','secondary','Escolher executável');button.type='button';
      button.onclick=()=>window.pacocaNative.chooseApplication(path=>{if(path)input.value=path;});row.append(button);
    }
    $('#application-paths').append(row);
  }
  $("#setting-retention").value = String(s.retention_days);
  $("#setting-speed").value = s.voice_speed;
  $('#setting-voice-style').value = s.voice_style || 'male';
  $('#setting-voice-style option[value=female]').disabled = !state.status?.voice?.female_available;
  $('#setting-voice-style option[value=female]').textContent = state.status?.voice?.female_available
    ? 'Feminina · ' + state.status.voice.female_name : 'Feminina · indisponível neste Windows';
  $('#setting-transcription').value = s.transcription_mode || 'fast';
  $('#setting-wake').checked = Boolean(s.wake_enabled);
  $('#setting-wake-sensitivity').value = s.wake_sensitivity || 'normal';
  $('#setting-wake-timeout').value = String(s.wake_timeout || 20);
  $("#speed-output").textContent = s.voice_speed + "×";
  $("#setting-startup").checked = s.start_with_windows;
  $("#setting-alexa").checked = s.alexa_enabled;
  $("#setting-skill-id").value = s.alexa_skill_id;
  $("#setting-alexa-user").value = s.alexa_user_id;
  await enumerateDevices();
}
async function enumerateDevices() {
  if (!navigator.mediaDevices) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const [kind, id, value] of [
      ["audioinput", "#setting-mic", state.settings.microphone_id],
      ["audiooutput", "#setting-output", state.settings.output_id],
    ]) {
      const select = $(id);
      select.replaceChildren(
        el(
          "option",
          "",
          kind === "audioinput" ? "Microfone padrão" : "Saída padrão",
        ),
      );
      select.firstChild.value = "";
      let index = 0;
      for (const d of devices.filter((d) => d.kind === kind)) {
        const o = el(
          "option",
          "",
          d.label ||
            (kind === "audioinput" ? "Microfone " : "Saída ") + ++index,
        );
        o.value = d.deviceId;
        select.append(o);
      }
      select.value = value || "";
    }
  } catch {}
}
async function saveSettings() {
  const body = {
    user_name: $("#setting-name").value.trim(),
    theme: $("#setting-theme").value,
    backend: $("#setting-backend").value,
    model_profile: $('#setting-profile').value,
    cpu_threads: Number($('#setting-threads').value),
    idle_seconds: Number($('#setting-idle').value),
    game_guard: $('#setting-game-guard').checked,
    updates_enabled: $('#setting-updates').checked,
    update_install_on_exit: $('#setting-update-exit').checked,
    application_paths:Object.fromEntries([...document.querySelectorAll('[data-app-path]')].map(input=>[input.dataset.appPath,input.value.trim()])),
    spotify_device:$('#setting-spotify-device').value.trim(),
    retention_days: Number($("#setting-retention").value),
    voice_speed: Number($("#setting-speed").value),
    voice_style: $('#setting-voice-style').value,
    transcription_mode: $('#setting-transcription').value,
    wake_enabled: $('#setting-wake').checked,
    wake_sensitivity: $('#setting-wake-sensitivity').value,
    wake_timeout: Number($('#setting-wake-timeout').value),
    microphone_id: $("#setting-mic").value,
    output_id: $("#setting-output").value,
    alexa_enabled: $("#setting-alexa").checked,
    alexa_skill_id: $("#setting-skill-id").value.trim(),
    alexa_user_id: $("#setting-alexa-user").value.trim(),
  };
  if ($("#setting-startup").checked !== state.settings.start_with_windows)
    body.start_with_windows = $("#setting-startup").checked;
  const restartCapture = body.microphone_id !== state.settings.microphone_id;
  const restartWake = body.wake_sensitivity !== state.settings.wake_sensitivity;
  state.settings = await json("/settings", { method: "PATCH", body });
  state.wake.paused = !body.wake_enabled;
  state.wake.failed = false;
  if (restartCapture) closeCapture();
  if (restartCapture || restartWake) closeWake();
  if (restartCapture && state.voice) {
    try { await ensureCapture(); }
    catch (e) { endVoice(true); throw e; }
  }
  await reconcileWake();
  document.body.dataset.theme = state.settings.theme;
  toast("Preferências salvas.");
  refreshStatus();
}

// One microphone stream supplies either keyword spotting or the active conversation.
async function ensureCapture() {
  if (state.stream) return;
  if (state.captureStarting) return state.captureStarting;
  const epoch = state.captureEpoch;
  state.captureStarting = (async () => {
    if (!navigator.mediaDevices?.getUserMedia) throw Error("Abra a janela da Paçoca para usar o microfone.");
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    if (state.settings.microphone_id) audio.deviceId = { exact: state.settings.microphone_id };
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio }); }
    catch { throw Error("Não consegui acessar o microfone. Confira a permissão e o dispositivo escolhido."); }
    if (epoch !== state.captureEpoch) { stream.getTracks().forEach(t => t.stop()); return; }
    state.stream = stream;
    state.context = new AudioContext();
    await state.context.resume();
    await state.context.audioWorklet.addModule("/static/recorder.js");
    if (epoch !== state.captureEpoch || !state.context) return;
    const source = state.context.createMediaStreamSource(stream);
    state.node = new AudioWorkletNode(state.context, "pacoca-capture");
    state.node.port.onmessage = e => audioChunk(e.data);
    source.connect(state.node);
    const silent = state.context.createGain(); silent.gain.value = 0;
    state.node.connect(silent); silent.connect(state.context.destination);
    stream.getTracks().forEach(track => track.onended = () => {
      closeCapture(); closeWake(); endVoice(true);
      state.wake.retryAt = Date.now() + 3000;
      $('#wake-label').textContent = 'Microfone desconectado. Reconectando…';
    });
    enumerateDevices();
  })();
  try { await state.captureStarting; }
  catch (e) { closeCapture(); throw e; }
  finally { state.captureStarting = null; }
}
function closeCapture() {
  state.captureEpoch++;
  state.stream?.getTracks().forEach(t => { t.onended = null; t.stop(); });
  state.stream = null;
  state.node?.disconnect(); state.node = null;
  state.context?.close(); state.context = null;
}
function beginVoice(automatic = false) {
  state.voiceEpoch++;
  state.voice = true; state.automaticVoice = automatic;
  state.pendingWakeChunks = null; state.wakeCommandFrames = 0;
  state.lastVoiceActivity = Date.now();
  state.chunks = []; state.preRoll = []; state.recording = false;
  state.voiced = 0; state.silent = 0;
  $('#voice-session').hidden = false;
  $('#voice-state').textContent = 'Estou ouvindo você';
  $('#end-voice').textContent = state.settings.wake_enabled ? 'Voltar à espera' : 'Encerrar conversa por voz';
  $('#mic-button').setAttribute('aria-label', 'Encerrar conversa por voz');
  document.body.classList.add('voice-active');
  page('chat'); reportActivity(); renderWake();
}
async function startVoice() {
  if (state.voice) { endVoice(); return; }
  await ensureCapture();
  if (state.stream) beginVoice();
}
function endVoice(force = false) {
  state.voiceEpoch++; state.voice = false; state.automaticVoice = false;
  state.firstWakeUtterance = false; state.recording = false;
  state.pendingWakeChunks = null; state.wakeCommandFrames = 0;
  state.chunks = []; state.preRoll = []; state.voiced = state.silent = 0;
  $('#voice-session').hidden = true;
  document.body.classList.remove('voice-active');
  $('#mic-button').setAttribute('aria-label', 'Iniciar conversa por voz');
  stopPlayback();
  if (force || !state.settings.wake_enabled) { closeCapture(); closeWake(); }
  else resetWake();
  reportActivity(); renderWake();
}
function renderWake(message) {
  const w = state.wake;
  $('#wake-label').textContent = message || (state.voice ? 'Conversa por voz ativa' :
    state.settings.wake_enabled && !w.paused ? (w.failed ? 'Escuta indisponível. Confira o microfone.' :
    w.ready ? 'Diga “Paçoca” · escuta local' : 'Preparando a escuta local…') : 'Microfone pausado');
  $('#wake-toggle').textContent = state.settings.wake_enabled || state.voice ? 'Pausar microfone' : 'Ativar “Paçoca”';
  $('#wake-status').classList.toggle('listening', Boolean(state.stream));
}
function closeWake() {
  const w = state.wake, ws = w.ws;
  w.ws = null; w.ready = false; w.connecting = false;
  w.ring = []; w.packet = []; w.samples = w.ack = 0;
  if (ws) { ws.onclose = null; ws.close(); }
}
function resetWake() {
  const w = state.wake;
  w.ready = false; w.ring = []; w.packet = []; w.samples = w.ack = 0;
  w.mutedUntil = Date.now() + 500;
  if (w.ws?.readyState === WebSocket.OPEN) w.ws.send('reset');
}
async function reconcileWake() {
  const w = state.wake;
  if (!state.settings.wake_enabled || w.paused || !state.settings.onboarding_done) {
    closeWake();
    if (!state.voice && !state.captureStarting) closeCapture();
    renderWake(); return;
  }
  if (w.ws || w.connecting || w.failed || Date.now() < w.retryAt) return;
  w.connecting = true;
  try {
    await ensureCapture();
    if (!state.stream || !state.settings.wake_enabled || w.paused) return;
    const ws = new WebSocket(`ws://${location.host}/wake?token=${encodeURIComponent(token)}`);
    w.ws = ws;
    ws.onmessage = e => {
      if (w.ws !== ws) return;
      const result = JSON.parse(e.data);
      if (result.type === 'ready' || result.type === 'reset') {
        w.ready = true; w.samples = w.ack = 0; w.ring = []; w.packet = [];
        renderWake();
      } else if (result.type === 'error') {
        w.failed = true; closeWake();
        if (!state.voice) closeCapture();
        renderWake(result.message);
      } else if (result.type === 'ack' || result.type === 'wake') {
        w.ack = result.samples;
        if (result.type === 'wake' && w.ready && !state.voice && state.stream && state.settings.wake_enabled) {
          const chunks = w.ring.filter(item => item.end > result.start - 4000).map(item => item.chunk);
          const afterName = w.ring.filter(item => item.end > result.end + 1600);
          beginVoice(true); state.firstWakeUtterance = true;
          state.keywordTailSamples = Math.max(0, result.end + 1600 - w.samples);
          state.wakeCommandFrames = afterName.filter(item => Math.sqrt(item.chunk.reduce((n,v) => n+v*v,0)/item.chunk.length) > 0.01).length;
          state.recording = true; state.chunks = chunks;
          // Quiet acknowledgement uses the existing local audio context, no voice model.
          const oscillator = state.context.createOscillator(), gain = state.context.createGain();
          oscillator.frequency.value = 660; gain.gain.value = 0.035;
          oscillator.connect(gain); gain.connect(state.context.destination);
          oscillator.start(); oscillator.stop(state.context.currentTime + 0.065);
          oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
          w.ring = []; w.packet = [];
        }
      }
    };
    ws.onclose = () => {
      if (w.ws !== ws) return;
      closeWake(); w.retryAt = Date.now() + 3000;
      if (!state.voice) closeCapture();
      renderWake('Escuta desconectada. Reconectando…');
    };
    ws.onerror = () => {};
  } catch (e) {
    w.failed = true; closeWake(); if (!state.voice) closeCapture();
    renderWake(e.message); toast(e.message, true);
  } finally { w.connecting = false; }
}
function wakeChunk(chunk) {
  const w = state.wake;
  if (!w.ready || w.ws?.readyState !== WebSocket.OPEN || !state.settings.wake_enabled) return;
  if (state.player || state.audioQueue.length || state.previewPlaying) { w.needsReset = true; return; }
  if (w.needsReset) { w.needsReset = false; resetWake(); return; }
  if (Date.now() < w.mutedUntil) return;
  // Reject backlog instead of waking on stale audio after a slow or suspended PC.
  if (w.ws.bufferedAmount > 32000 || w.samples - w.ack > 32000) { resetWake(); return; }
  w.samples += chunk.length;
  w.ring.push({ end: w.samples, chunk });
  while (w.ring.length > 125) w.ring.shift(); // Four seconds, memory only.
  w.packet.push(chunk);
  if (w.packet.length >= 5) {
    const pcm = new Int16Array(2560); let at = 0;
    for (const c of w.packet) for (const sample of c) pcm[at++] = Math.max(-32768, Math.min(32767, Math.round(sample * 32768)));
    w.packet = []; w.ws.send(pcm.buffer);
  }
}
async function pauseMicrophone() {
  state.wake.paused = true;
  state.settings.wake_enabled = false;
  state.wake.failed = false;
  endVoice(true);
  // Persist pause so status polling and the next launch cannot silently reopen the mic.
  state.settings = await json('/settings', { method: 'PATCH', body: { wake_enabled: false } });
  renderWake();
}
async function toggleWake() {
  if (state.settings.wake_enabled || state.voice) { await pauseMicrophone(); return; }
  state.wake.failed = false; state.wake.paused = false; state.wake.retryAt = 0;
  state.settings = await json('/settings', { method: 'PATCH', body: { wake_enabled: true } });
  await reconcileWake();
}
function voiceTick() {
  const w = state.wake;
  if (w.ws?.readyState === WebSocket.OPEN && (state.voice || !w.ready)) w.ws.send('ping');
  const busy = state.recording || state.processing || state.generating || state.player || state.audioQueue.length ||
    state.approvals.length || $('#prompt').value.trim() || $('#modal').open;
  if (busy) state.lastVoiceActivity = Date.now();
  if (state.voice && state.automaticVoice && !busy &&
      Date.now() - state.lastVoiceActivity > (state.settings.wake_timeout || 20) * 1000) endVoice();
}
function audioChunk(chunk) {
  if (!state.voice) { wakeChunk(chunk); return; }
  if (state.processing) return;
  const energy = Math.sqrt(chunk.reduce((n, v) => n + v * v, 0) / chunk.length);
  const threshold = state.player ? 0.018 : 0.01;
  const voiced = energy > threshold;
  if (state.firstWakeUtterance && state.recording) {
    if (state.keywordTailSamples > 0) state.keywordTailSamples -= chunk.length;
    else if (voiced) state.wakeCommandFrames++;
  }
  if (voiced) state.lastVoiceActivity = Date.now();
  if (!state.recording) {
    state.preRoll.push(chunk);
    if (state.preRoll.length > 9) state.preRoll.shift();
    state.voiced = voiced ? state.voiced + 1 : 0;
    if (state.voiced >= 4) {
      state.recording = true;
      state.chunks = [...state.preRoll];
      if (state.pendingWakeChunks) {
        state.chunks = [...state.pendingWakeChunks, ...state.chunks];
        state.pendingWakeChunks = null;
        state.wakeCommandFrames = 999;
      }
      state.preRoll = [];
      state.silent = 0;
      // A sound must not cancel an application launch. A recognized new request
      // interrupts in send(); playback pauses immediately for conversational use.
      if (state.player) stopPlayback();
      $("#voice-state").textContent = "Pode falar, estou ouvindo";
    }
  } else {
    state.chunks.push(chunk);
    state.silent = voiced ? 0 : state.silent + 1;
    if (state.silent > 14 || state.chunks.length >= 1300) {
      const chunks = state.chunks;
      state.chunks = [];
      state.recording = false;
      state.voiced = 0;
      state.silent = 0;
      if (state.firstWakeUtterance && state.wakeCommandFrames < 6) {
        // A call by itself waits for the command. Do not start Whisper and lose
        // the next sentence while it loads. Confirm name + command together.
        state.pendingWakeChunks = chunks;
        $('#voice-state').textContent = 'Pode falar seu pedido';
      } else transcribe(chunks);
    }
  }
}
async function transcribe(chunks) {
  const epoch = state.voiceEpoch;
  const confirmWake = state.firstWakeUtterance;
  state.firstWakeUtterance = false;
  state.processing = true;
  $("#voice-state").textContent = "Entendendo o que você disse";
  try {
    const size = chunks.reduce((n, c) => n + c.length, 0);
    const samples = new Float32Array(size);
    let offset = 0;
    for (const c of chunks) {
      samples.set(c, offset);
      offset += c.length;
    }
    const result = await json("/transcribe", {
      method: "POST",
      body: samples.buffer,
      headers: { "Content-Type": "application/octet-stream" },
    });
    if (epoch !== state.voiceEpoch) return;
    let text = result.text || '';
    if (confirmWake) {
      // Transcription confirms the actual name before any command is executed.
      const called = /^(?:(?:oi|ei|e|hey|olá)[,!.?\s]+)?pa(?:ç|c|ss?)o(?:al?)?ca\b[,!.?:\s-]*/i;
      if (!called.test(text)) { endVoice(); return; }
      text = text.replace(called, '').trim();
    }
    if (text && state.voice) {
      if (/^(?:por favor[, ]+)?(?:parar de ouvir|pare de ouvir|pausar (?:o )?microfone|pause (?:o )?microfone)\b/i.test(text)) {
        await pauseMicrophone();
        toast('Microfone pausado.');
        return;
      }
      $("#voice-state").textContent = "Já entendi. Um instante…";
      await send(text);
    } else $("#voice-state").textContent = "Estou ouvindo você";
  } catch (e) {
    toast(e.message, true);
    $("#voice-state").textContent = "Estou ouvindo você";
  } finally {
    state.processing = false;
    state.lastVoiceActivity = Date.now();
    playNext();
  }
}

$$("[data-page]").forEach((b) => (b.onclick = () => page(b.dataset.page)));
$(".brand").onclick = (e) => {
  e.preventDefault();
  page("chat");
};
$("#new-chat").onclick = newChat;
$("#refresh-chats").onclick = safely(loadChats);
$("#composer").onsubmit = (e) => {
  e.preventDefault();
  safely(() => send($("#prompt").value))();
};
$("#prompt").onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    safely(() => send($("#prompt").value))();
  }
};
$("#prompt").oninput = () => {
  $("#prompt").style.height = "auto";
  $("#prompt").style.height = Math.min(160, $("#prompt").scrollHeight) + "px";
};
$$("[data-prompt]").forEach(
  (b) => (b.onclick = safely(() => send(b.dataset.prompt))),
);
$("#start-voice").onclick = safely(startVoice);
$("#mic-button").onclick = safely(startVoice);
$("#end-voice").onclick = () => endVoice();
$("#wake-toggle").onclick = safely(toggleWake);
$("#toggle-speech").onclick = () => {
  state.speech = !state.speech;
  $("#toggle-speech").classList.toggle("active", state.speech);
  $("#toggle-speech").setAttribute(
    "aria-label",
    state.speech ? "Desativar resposta por voz" : "Ativar resposta por voz",
  );
  if (!state.speech) stopPlayback();
};
$("#stop-response").onclick = interrupt;
$("#emergency").onclick = safely(async () => {
  try { await pauseMicrophone(); } catch (e) { toast(e.message, true); }
  await interrupt();
  await json("/stop", { method: "POST" });
  toast("Fala e tarefas interrompidas.");
});
$("#add-memory").onclick = () => editMemory();
$("#memory-search").oninput = renderMemories;
$("#add-folder").onclick = addFolder;
$("#index-folders").onclick = safely(async () => {
  await json("/knowledge/index", { method: "POST" });
  loadKnowledge();
});
$$("[data-task-tab]").forEach(
  (b) =>
    (b.onclick = () => {
      state.taskTab = b.dataset.taskTab;
      $$("[data-task-tab]").forEach((t) =>
        t.classList.toggle("active", t === b),
      );
      $("#task-list").hidden = state.taskTab !== "tasks";
      $("#reminder-list").hidden = state.taskTab !== "reminders";
    }),
);
$("#setting-speed").oninput = () =>
  ($("#speed-output").textContent = $("#setting-speed").value + "×");
$("#save-settings").onclick = safely(saveSettings);
$("#preview-voice").onclick = safely(async () => {
  const b = $("#preview-voice");
  b.disabled = true;
  try {
    const r = await api("/voice/preview", { method: "POST", body: {
      voice_style: $('#setting-voice-style').value, voice_speed: Number($('#setting-speed').value)
    } });
    const url = URL.createObjectURL(await r.blob());
    const a = new Audio(url);
    state.previewPlaying = true;
    a.onended = a.onerror = () => { state.previewPlaying = false; URL.revokeObjectURL(url); };
    if ($("#setting-output").value && a.setSinkId)
      await a.setSinkId($("#setting-output").value);
    try { await a.play(); }
    catch (e) { state.previewPlaying = false; URL.revokeObjectURL(url); throw e; }
  } finally {
    b.disabled = false;
  }
});
$("#restart-engine").onclick = safely(async () => {
  await json("/runtime/restart", { method: "POST" });
  toast("Reiniciando sua inteligência local.");
  refreshStatus();
});
$("#diagnostics").onclick = safely(async () => {
  const data = await json("/diagnostics");
  modal(
    "Um olhar por dentro.",
    "Informações técnicas para entender como a Paçoca está funcionando.",
    el("pre", "diagnostic-log", JSON.stringify(data, null, 2)),
    [{ text: "Fechar", class: "secondary", fn: closeModal }],
  );
});
$("#export-data").onclick = safely(async () => {
  const r = await api("/export");
  const url = URL.createObjectURL(await r.blob());
  const a = el("a");
  a.href = url;
  a.download = "pacoca-backup.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
});
$("#finish-onboarding").onclick = safely(async () => {
  state.settings = await json("/settings", {
    method: "PATCH",
    body: {
      user_name: $("#onboarding-name").value.trim(),
      onboarding_done: true,
    },
  });
  $("#onboarding").close();
  refreshStatus();
  toast("Que bom ter você por aqui. Vamos começar.");
});
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key.toLowerCase() === "n") {
    e.preventDefault();
    newChat();
  }
  if (e.key === "Escape" && !$("#modal").open && !$("#onboarding").open) {
    interrupt();
  }
});
window.addEventListener("beforeunload", () => {
  endVoice(true);
  stopPlayback();
});
async function init() {
  connect();
  await refreshStatus();
  await loadChats();
  const last = localStorage.getItem("pacoca-conversation");
  if (last)
    try {
      await openChat(last);
    } catch {
      localStorage.removeItem("pacoca-conversation");
    }
  setInterval(refreshStatus, 4000);
  setInterval(reportActivity,2000);
  setInterval(voiceTick,1000);
}
safely(init)();

function reportActivity() {
  if(state.ws?.readyState!==WebSocket.OPEN)return;
  state.ws.send(JSON.stringify({type:'activity',voice:state.voice,
    playback:Boolean(state.audioQueue.length || state.player && !state.player.paused),
    draft:Boolean($('#prompt').value.trim() || $('#onboarding').open || $('#modal').open)}));
}

function renderUpdate(update) {
  state.update=update;
  const visible=['available','downloading','ready','installing','failed'].includes(update.phase);
  $('#update-banner').hidden=!visible;
  const text=update.phase==='development' ? 'Atualizações disponíveis no aplicativo instalado.' :
    (update.message || 'Sua Paçoca acompanha as atualizações automaticamente.');
  const suffix=update.phase==='downloading' ? ' · '+update.percent+'%' : '';
  $('#update-banner-text').textContent=text+suffix;
  $('#update-status').textContent=text+(update.version ? ' · versão '+update.version : '')+(update.blocked ? ' · '+update.blocked : '');
  $('#update-progress').hidden=update.phase!=='downloading';
  $('#update-progress').value=update.percent || 0;
  $('#download-update').hidden=update.phase!=='available';
  for(const id of ['#apply-update','#update-banner-apply']) {
    $(id).hidden=update.phase!=='ready';$(id).disabled=Boolean(update.blocked);
    $(id).title=update.blocked || 'Instalar a atualização verificada e reiniciar';
  }
}

$('#check-updates').onclick=safely(async()=>renderUpdate(await json('/updates/check',{method:'POST'})));
$('#download-update').onclick=safely(async()=>renderUpdate(await json('/updates/download',{method:'POST'})));
async function applyUpdate() {
  const result=await json('/updates/apply',{method:'POST'});
  if(!result.ok)toast(result.reason,true);
}
$('#apply-update').onclick=safely(applyUpdate);
$('#update-banner-apply').onclick=safely(applyUpdate);
