/* ══════════════════════════════════════════════════════════════════
   Chess Fragments AI Arena — app.js
   Real-time 5x5 board UI, Move Review / Scrubbing, Rock-Solid Clocks,
   Auto-Flip Board, Stylized Right Piece, Audio Synthesizer
   ══════════════════════════════════════════════════════════════════ */

"use strict";

// ── Piece Unicode Symbols ─────────────────────────────────────────
const PIECE_SYMBOLS = {
  king:   { white: "♔", black: "♚" },
  queen:  { white: "♕", black: "♛" },
  right:  { white: "♜", black: "♜" }, // Standard fallback
  bishop: { white: "♗", black: "♝" },
  knight: { white: "♘", black: "♞" },
  pawn:   { white: "♙", black: "♟" },
};

// ── Web Audio API Synthesizer (Zero External Audio Files) ────────
class SoundSynthesizer {
  constructor() {
    this.ctx = null;
    this.enabled = true;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.ctx = new AudioCtx();
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  playMove() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(260, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(80, this.ctx.currentTime + 0.08);

    gain.gain.setValueAtTime(0.28, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.08);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + 0.09);
  }

  playCapture() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    const now = this.ctx.currentTime;
    const osc1 = this.ctx.createOscillator();
    const osc2 = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    osc1.type = "sine";
    osc2.type = "triangle";
    osc1.frequency.setValueAtTime(420, now);
    osc1.frequency.exponentialRampToValueAtTime(140, now + 0.12);
    osc2.frequency.setValueAtTime(240, now);
    osc2.frequency.exponentialRampToValueAtTime(90, now + 0.12);

    gain.gain.setValueAtTime(0.35, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(this.ctx.destination);

    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + 0.13);
    osc2.stop(now + 0.13);
  }

  playVictory() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    const notes = [523.25, 659.25, 783.99, 1046.50];
    notes.forEach((freq, idx) => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      const startTime = this.ctx.currentTime + idx * 0.12;

      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, startTime);
      gain.gain.setValueAtTime(0.18, startTime);
      gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.45);

      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(startTime);
      osc.stop(startTime + 0.46);
    });
  }
}

const sounds = new SoundSynthesizer();

// ── SocketIO Setup ────────────────────────────────────────────────
const socket = io({ transports: ["websocket", "polling"] });

// ── App State ─────────────────────────────────────────────────────
let state = {
  active: false,
  ply: 1,
  human_side: "white",
  agent_side: "black",
  result: null,
  initial_board_grid: null,
  board: null,
  selected: null,
  legal_targets: [],
  move_history: [],
  agent_name: "agent.py",
  board_sample: "sample0",
  opponent_type: "baseline",
  watch_delay: 0.5,
  time_control: 300.0,
  white_time_left: 300.0,
  black_time_left: 300.0,
  base_white_time: 300.0,
  base_black_time: 300.0,
  turn_start_time: null,
  server_now: null,
  can_undo: false,
  current_player: null,
  white_material: 0,
  black_material: 0,
  white_advantage: 0,
  black_advantage: 0,
  captured_by_white: [],
  captured_by_black: [],
  agent_stats: { time: 0, depth: 0, nodes: 0 },
};

let lastFrom = null;
let lastTo = null;
let myChoice = "white"; // selected side ("white", "black", "watch")
let isFlipped = false;  // board perspective: true = Black at bottom, false = White at bottom
let agentThinking = false;
let reviewIndex = -1;   // -1 = live, 0 = initial position, 1..N = after move N
let serverTimeOffset = 0; // ms difference between server timestamp and client clock
let rightPieceStyle = localStorage.getItem("chess_right_style") || "fairy"; // "fairy" | "hybrid" | "standard"

// ── DOM References ────────────────────────────────────────────────
const boardEl          = document.getElementById("board");
const statusEl         = document.getElementById("status-text");
const historyEl        = document.getElementById("move-history");
const moveCountBadge   = document.getElementById("move-count-badge");
const logEl            = document.getElementById("log-panel");
const agentSelect      = document.getElementById("agent-select");
const headerAgentName  = document.getElementById("header-agent-name");
const boardSelect      = document.getElementById("board-select");
const rightStyleSelect = document.getElementById("right-style-select");
const tcSelect         = document.getElementById("tc-select");
const oppSelect        = document.getElementById("opp-select");
const sidePicker       = document.getElementById("side-picker");
const speedRange       = document.getElementById("speed-range");
const speedVal         = document.getElementById("speed-val");
const btnNewGame       = document.getElementById("btn-new-game");
const btnResign        = document.getElementById("btn-resign");
const btnUndoAction    = document.getElementById("btn-undo-action");
const btnUndoMove      = document.getElementById("btn-undo-move");
const btnLoadAgent     = document.getElementById("btn-load-agent");
const btnPromoteAgent  = document.getElementById("btn-promote-agent");
const btnClearLog      = document.getElementById("btn-clear-log");
const btnFlipBoard     = document.getElementById("btn-flip-board");
const btnSoundToggle   = document.getElementById("btn-sound-toggle");
const btnStopHosting   = document.getElementById("btn-stop-hosting");
const soundIcon        = document.getElementById("sound-icon");
const resultOverlay    = document.getElementById("result-overlay");
const resultIcon       = document.getElementById("result-icon");
const resultTitle      = document.getElementById("result-title");
const resultSub        = document.getElementById("result-sub");
const btnPlayAgain     = document.getElementById("btn-play-again");
const btnCloseResult   = document.getElementById("btn-close-result");
const connDot          = document.getElementById("conn-dot");
const connLabel        = document.getElementById("conn-label");
const whiteBar         = document.getElementById("player-white-bar");
const blackBar         = document.getElementById("player-black-bar");
const whiteRole        = document.getElementById("white-role");
const blackRole        = document.getElementById("black-role");
const whiteSpinner     = document.getElementById("white-spinner");
const blackSpinner     = document.getElementById("black-spinner");
const whiteCaptured    = document.getElementById("white-captured");
const blackCaptured    = document.getElementById("black-captured");
const whiteLeadBadge   = document.getElementById("white-lead-badge");
const blackLeadBadge   = document.getElementById("black-lead-badge");
const whiteClock       = document.getElementById("white-clock");
const blackClock       = document.getElementById("black-clock");
const whiteTimer       = document.getElementById("white-timer");
const blackTimer       = document.getElementById("black-timer");
const evalBarFill      = document.getElementById("eval-bar-fill");
const evalScoreBadge   = document.getElementById("eval-score-badge");
const guideModal       = document.getElementById("guide-modal");
const btnOpenGuide     = document.getElementById("btn-open-guide");
const btnCloseGuide    = document.getElementById("btn-close-guide");
const btnGuideGotIt    = document.getElementById("btn-guide-got-it");

// Scrubbing & Review Controls
const btnNavFirst      = document.getElementById("btn-nav-first");
const btnNavPrev       = document.getElementById("btn-nav-prev");
const btnNavNext       = document.getElementById("btn-nav-next");
const btnNavLast       = document.getElementById("btn-nav-last");
const navStatusDot     = document.getElementById("nav-status-dot");
const navPlyText       = document.getElementById("nav-ply-text");
const reviewBanner     = document.getElementById("review-banner");
const reviewPlyNum     = document.getElementById("review-ply-num");
const btnJumpLive      = document.getElementById("btn-jump-live");

// Initialize Right style select
if (rightStyleSelect) {
  rightStyleSelect.value = rightPieceStyle;
}

// ── Toast Banner Notification ─────────────────────────────────────
function showToast(msg, duration = 3000) {
  let toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove("show"), duration);
}

// ── SocketIO Handlers ─────────────────────────────────────────────
socket.on("connect", () => {
  connDot.className = "dot connected";
  connLabel.textContent = "Online";
  socket.emit("get_state");
  socket.emit("list_agents");
});

socket.on("disconnect", () => {
  connDot.className = "dot disconnected";
  connLabel.textContent = "Offline";
});

socket.on("state_update", (data) => {
  if (data.server_now) {
    serverTimeOffset = (data.server_now * 1000) - Date.now();
  }

  const prevHistLen = (state.move_history || []).length;
  const isFreshGame = data.ply === 1 && prevHistLen > 0;
  state = { ...state, ...data };

  // If a brand new match just started, reset review mode and auto-flip if playing Black
  if (isFreshGame || (state.active && prevHistLen === 0)) {
    reviewIndex = -1;
    if (state.human_side === "black") {
      isFlipped = true;
    } else if (state.human_side === "white") {
      isFlipped = false;
    }
  }

  // Audio cues on new move
  const newHist = state.move_history || [];
  if (newHist.length > prevHistLen && newHist.length > 0) {
    const lastMove = newHist[newHist.length - 1];
    if (lastMove.captured) {
      sounds.playCapture();
    } else {
      sounds.playMove();
    }
  }

  // If user was viewing live, stay at live; if reviewing, keep reviewIndex
  renderAll();
});

socket.on("agent_list", ({ agents }) => {
  agentSelect.innerHTML = "";
  agents.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    if (name === state.agent_name) opt.selected = true;
    agentSelect.appendChild(opt);
  });
});

socket.on("agent_loaded", ({ name, ok, error }) => {
  if (ok) {
    headerAgentName.textContent = name;
    showToast(`✓ Loaded agent: ${name}`);
  } else {
    showToast(`✗ Failed to load agent: ${error || "error"}`);
  }
});

socket.on("main_agent_updated", ({ ok, source, error }) => {
  if (ok) {
    showToast(`👑 ${source} is now active as primary agent.py!`);
    headerAgentName.textContent = "agent.py";
    socket.emit("list_agents");
  } else {
    showToast(`✗ Error updating agent.py: ${error || "unknown"}`);
  }
});

socket.on("agent_thinking", ({ side }) => {
  agentThinking = true;
  connDot.className = "dot thinking";
  if (side === "white") {
    whiteSpinner.style.display = "flex";
    blackSpinner.style.display = "none";
    whiteBar.classList.add("active-turn");
    blackBar.classList.remove("active-turn");
  } else {
    blackSpinner.style.display = "flex";
    whiteSpinner.style.display = "none";
    blackBar.classList.add("active-turn");
    whiteBar.classList.remove("active-turn");
  }
  statusEl.textContent = `AI (${side.toUpperCase()}) is computing optimal move…`;
});

socket.on("log", ({ msg, level, ts }) => {
  addLog(msg, level, ts);
});

function addLog(msg, level = "info", ts = null) {
  const entry = document.createElement("div");
  entry.className = `log-entry ${level}`;
  const time = ts || new Date().toLocaleTimeString("en-GB", { hour12: false });
  entry.innerHTML = `<span class="log-ts">[${time}]</span><span class="log-msg">${escapeHtml(msg)}</span>`;
  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
  while (logEl.children.length > 300) logEl.removeChild(logEl.firstChild);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Piece Symbol Resolver (Respects Custom Right Piece Style) ─────
function getPieceUnicode(name, color) {
  if (name === "right") {
    if (rightPieceStyle === "fairy") return "ℝ";
    if (rightPieceStyle === "hybrid") return "♜ᴷ";
    return PIECE_SYMBOLS.right[color] || "♜";
  }
  return PIECE_SYMBOLS[name]?.[color] ?? "?";
}

// ── Clocks Ticking (Rock-Solid Server-Epoch Synchronized) ─────────
function formatClockTime(seconds) {
  if (seconds >= 99999 || state.time_control === 0) return "∞";
  const s = Math.max(0, seconds);
  const mins = Math.floor(s / 60);
  const secs = Math.floor(s % 60);

  if (s < 10) {
    const tenths = Math.floor((s % 1) * 10);
    return `0${mins}:${secs < 10 ? "0" : ""}${secs}.${tenths}`;
  }
  return `${mins < 10 ? "0" : ""}${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

function calculateCurrentClocks() {
  // If reviewing a past move snapshot, display that move's recorded clock time
  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const snap = state.move_history[reviewIndex - 1];
    if (snap.white_time !== undefined && snap.black_time !== undefined) {
      return {
        white: snap.white_time,
        black: snap.black_time,
      };
    }
  }

  // Unlimited time or inactive game
  if (!state.active || state.result || state.time_control === 0) {
    return {
      white: state.white_time_left ?? 300,
      black: state.black_time_left ?? 300,
    };
  }

  // Exact live calculation from turn_start_time and server offset
  const now = (Date.now() + serverTimeOffset) / 1000;
  const turnStart = state.turn_start_time || now;
  const elapsed = Math.max(0, now - turnStart);

  let wSec = state.base_white_time ?? state.white_time_left ?? 300;
  let bSec = state.base_black_time ?? state.black_time_left ?? 300;

  if (state.current_player === "white") {
    wSec = Math.max(0, wSec - elapsed);
  } else if (state.current_player === "black") {
    bSec = Math.max(0, bSec - elapsed);
  }

  return { white: wSec, black: bSec };
}

setInterval(() => {
  renderClocks();
}, 100);

function renderClocks() {
  const clocks = calculateCurrentClocks();
  const wSec = clocks.white;
  const bSec = clocks.black;

  whiteTimer.textContent = formatClockTime(wSec);
  blackTimer.textContent = formatClockTime(bSec);

  whiteClock.classList.toggle("warning-clock", wSec <= 30 && wSec > 10);
  whiteClock.classList.toggle("critical-clock", wSec <= 10 && wSec > 0);

  blackClock.classList.toggle("warning-clock", bSec <= 30 && bSec > 10);
  blackClock.classList.toggle("critical-clock", bSec <= 10 && bSec > 0);
}

// ── Rendering Functions ───────────────────────────────────────────
function renderAll() {
  headerAgentName.textContent = state.agent_name || "agent.py";
  renderBoard();
  renderHistory();
  renderStats();
  renderPlayerBars();
  renderEvaluation();
  renderClocks();
  renderStatus();
  renderResult();
  updateNavControls();
  agentThinking = false;
  connDot.className = state.active ? "dot connected" : "dot connected";
}

function getActiveBoardGrid() {
  if (reviewIndex === 0) {
    return state.initial_board_grid || state.board;
  }
  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    return state.move_history[reviewIndex - 1].board_grid || state.board;
  }
  return state.board;
}

function getActiveMoveHighlights() {
  if (reviewIndex === 0) {
    return { from: null, to: null };
  }
  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const mv = state.move_history[reviewIndex - 1];
    return { from: mv.from, to: mv.to };
  }
  // Live position: highlight last move in history
  if (state.move_history && state.move_history.length > 0) {
    const last = state.move_history[state.move_history.length - 1];
    return { from: last.from, to: last.to };
  }
  return { from: null, to: null };
}

function renderBoard() {
  boardEl.innerHTML = "";
  const currentGrid = getActiveBoardGrid();

  if (!currentGrid) {
    boardEl.innerHTML = `
      <div style="grid-column: 1/-1; grid-row: 1/-1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.5rem; color:#5b727c; font-size:0.85rem; text-align:center;">
        <span style="font-size:2rem; color:#2dd4bf; opacity:0.4;">♟</span>
        Click <strong>▶ Start Match</strong><br/>to begin game
      </div>`;
    whiteSpinner.style.display = "none";
    blackSpinner.style.display = "none";
    return;
  }

  const isReviewing = reviewIndex >= 0;
  const legalSet = isReviewing ? new Set() : new Set((state.legal_targets || []).map(([x, y]) => `${x},${y}`));
  const highlights = getActiveMoveHighlights();

  // Auto-flip: when isFlipped is true, Black rank 0 is at bottom, White rank 4 is at top
  const yCoords = isFlipped ? [0, 1, 2, 3, 4] : [4, 3, 2, 1, 0];
  const xCoords = isFlipped ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];

  updateCoordinateLabels(yCoords, xCoords);

  for (let r = 0; r < 5; r++) {
    const y = yCoords[r];
    for (let c = 0; c < 5; c++) {
      const x = xCoords[c];
      const sq = document.createElement("div");
      const isLight = (x + y) % 2 === 0;
      sq.className = `sq ${isLight ? "light" : "dark"}`;
      sq.dataset.x = x;
      sq.dataset.y = y;

      const cell = currentGrid[y] ? currentGrid[y][x] : null;

      if (!isReviewing && state.selected && state.selected[0] === x && state.selected[1] === y) {
        sq.classList.add("selected");
      }

      if (highlights.from && highlights.from[0] === x && highlights.from[1] === y) {
        sq.classList.add("last-from");
      }
      if (highlights.to && highlights.to[0] === x && highlights.to[1] === y) {
        sq.classList.add("last-to");
      }

      if (legalSet.has(`${x},${y}`)) {
        sq.classList.add("legal-target");
        if (cell) sq.classList.add("has-piece");
      }

      if (cell) {
        const pieceEl = document.createElement("span");
        pieceEl.className = `piece ${cell.color}-piece`;
        pieceEl.textContent = getPieceUnicode(cell.piece, cell.color);

        if (cell.piece === "right") {
          if (rightPieceStyle === "fairy") {
            pieceEl.classList.add("piece-right-fairy");
          } else if (rightPieceStyle === "standard") {
            pieceEl.classList.add("piece-right-badge");
          }
        }

        pieceEl.title = `${cell.color.toUpperCase()} ${cell.piece} at (${x},${y})`;
        sq.appendChild(pieceEl);
      }

      sq.addEventListener("click", () => onSquareClick(x, y));
      boardEl.appendChild(sq);
    }
  }

  // Active turn glow on player bars (only in live mode)
  if (state.active && !agentThinking && !isReviewing) {
    if (state.current_player === "white") {
      whiteBar.classList.add("active-turn");
      blackBar.classList.remove("active-turn");
    } else {
      blackBar.classList.add("active-turn");
      whiteBar.classList.remove("active-turn");
    }
  } else if (isReviewing) {
    whiteBar.classList.remove("active-turn");
    blackBar.classList.remove("active-turn");
  }
}

function updateCoordinateLabels(yCoords, xCoords) {
  const colLeft = document.getElementById("coords-y-left");
  const colRight = document.getElementById("coords-y-right");
  const rowBottom = document.getElementById("coords-x");

  if (colLeft) colLeft.innerHTML = yCoords.map((y) => `<span>${y}</span>`).join("");
  if (colRight) colRight.innerHTML = yCoords.map((y) => `<span>${y}</span>`).join("");
  if (rowBottom) rowBottom.innerHTML = xCoords.map((x) => `<span>${x}</span>`).join("");
}

function onSquareClick(x, y) {
  if (reviewIndex >= 0) {
    showToast("Reviewing past move. Click '⚡ Return to Live' to make moves.");
    return;
  }
  if (!state.active || state.result) return;
  const human = state.human_side;
  if (human && state.current_player !== human) return;
  sounds.init();
  socket.emit("select_square", { x, y });
}

function renderHistory() {
  const hist = state.move_history || [];
  moveCountBadge.textContent = `${hist.length} plies`;
  if (hist.length === 0) {
    historyEl.innerHTML = '<div class="history-empty">No moves recorded yet</div>';
    return;
  }

  historyEl.innerHTML = "";
  hist.forEach((m, idx) => {
    const row = document.createElement("div");
    row.className = "move-row";
    row.dataset.idx = idx;

    if (reviewIndex === -1 && idx === hist.length - 1) {
      row.classList.add("active-move");
    } else if (reviewIndex === idx + 1) {
      row.classList.add("active-review-move");
    }

    const pSymbol = getPieceUnicode(m.piece, m.player);
    const notation = `${pSymbol} (${m.from[0]},${m.from[1]}) → (${m.to[0]},${m.to[1]})`;
    const capHtml = m.captured ? '<span class="cap-mark">×</span>' : "";
    const timeHtml = m.agent_time ? `<span class="move-time-tag">${m.agent_time}s</span>` : "";

    row.innerHTML = `
      <span class="move-num">${m.ply}.</span>
      <span class="move-cell">${notation} ${capHtml}</span>
      ${timeHtml}
    `;

    // Click on any move to scrub / review directly
    row.addEventListener("click", () => {
      setReviewIndex(idx + 1);
    });

    historyEl.appendChild(row);
  });

  // Auto-scroll history to active item
  const activeItem = historyEl.querySelector(".active-review-move") || historyEl.querySelector(".active-move");
  if (activeItem) {
    activeItem.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } else if (reviewIndex === -1) {
    historyEl.scrollTop = historyEl.scrollHeight;
  }
}

function renderStats() {
  const s = state.agent_stats || {};
  document.getElementById("stat-time").textContent = s.time ? `${s.time}s` : "—";
  document.getElementById("stat-depth").textContent = s.depth ? `${s.depth} plies` : "—";
  document.getElementById("stat-nodes").textContent = s.nodes ? s.nodes.toLocaleString() : "—";
  document.getElementById("stat-ply").textContent = reviewIndex >= 0 ? `${reviewIndex} (Rev)` : (state.ply || "—");
}

function renderPlayerBars() {
  const human = state.human_side;
  if (human === "white") {
    whiteRole.textContent = "You (Human)";
    blackRole.textContent = `AI (${state.agent_name || "Agent"})`;
  } else if (human === "black") {
    blackRole.textContent = "You (Human)";
    whiteRole.textContent = `AI (${state.agent_name || "Agent"})`;
  } else {
    whiteRole.textContent = `AI (${state.agent_name || "Agent"})`;
    blackRole.textContent = `Opponent (${state.opponent_type || "AI"})`;
  }

  // Perspective bar ordering: player's side always sits at the bottom
  if (isFlipped) {
    whiteBar.style.order = "1";
    blackBar.style.order = "4";
  } else {
    blackBar.style.order = "1";
    whiteBar.style.order = "4";
  }

  // Captured pieces tray (reflects reviewed position if in review mode)
  let capWhite = state.captured_by_white || [];
  let capBlack = state.captured_by_black || [];

  if (reviewIndex === 0) {
    capWhite = [];
    capBlack = [];
  } else if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const snap = state.move_history[reviewIndex - 1];
    capWhite = snap.captured_by_white || [];
    capBlack = snap.captured_by_black || [];
  }

  whiteCaptured.innerHTML = capWhite
    .map(
      (p) =>
        `<span class="cap-chip" title="Captured Black ${p}">${getPieceUnicode(p, "black")}</span>`
    )
    .join("");

  blackCaptured.innerHTML = capBlack
    .map(
      (p) =>
        `<span class="cap-chip" title="Captured White ${p}">${getPieceUnicode(p, "white")}</span>`
    )
    .join("");

  // Material Advantage badges
  let wAdv = state.white_advantage || 0;
  let bAdv = state.black_advantage || 0;

  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const snap = state.move_history[reviewIndex - 1];
    const diff = (snap.white_material || 0) - (snap.black_material || 0);
    wAdv = diff > 0 ? diff : 0;
    bAdv = diff < 0 ? Math.abs(diff) : 0;
  } else if (reviewIndex === 0) {
    wAdv = 0;
    bAdv = 0;
  }

  if (wAdv > 0) {
    whiteLeadBadge.style.display = "inline-block";
    whiteLeadBadge.textContent = `+${wAdv}`;
    blackLeadBadge.style.display = "none";
  } else if (bAdv > 0) {
    blackLeadBadge.style.display = "inline-block";
    blackLeadBadge.textContent = `+${bAdv}`;
    whiteLeadBadge.style.display = "none";
  } else {
    whiteLeadBadge.style.display = "none";
    blackLeadBadge.style.display = "none";
  }
}

function renderEvaluation() {
  let wMat = state.white_material || 0;
  let bMat = state.black_material || 0;

  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const snap = state.move_history[reviewIndex - 1];
    wMat = snap.white_material ?? wMat;
    bMat = snap.black_material ?? bMat;
  } else if (reviewIndex === 0) {
    wMat = 0;
    bMat = 0;
    const init = state.initial_board_grid;
    if (init) {
      for (let y = 0; y < 5; y++) {
        for (let x = 0; x < 5; x++) {
          const c = init[y][x];
          if (c) {
            const val = { king: 100, queen: 9, right: 7, bishop: 3, knight: 3, pawn: 1 }[c.piece] || 1;
            if (c.color === "white") wMat += val;
            else bMat += val;
          }
        }
      }
    }
  }

  const diff = wMat - bMat;
  const total = wMat + bMat;
  let pct = 50;

  if (total > 0) {
    pct = 50 + (diff / Math.max(1, total)) * 40;
    pct = Math.max(8, Math.min(92, pct));
  }

  evalBarFill.style.height = `${pct}%`;

  if (diff > 0) {
    evalScoreBadge.textContent = `+${diff.toFixed(1)}`;
  } else if (diff < 0) {
    evalScoreBadge.textContent = `${diff.toFixed(1)}`;
  } else {
    evalScoreBadge.textContent = `0.0`;
  }
}

function renderStatus() {
  if (reviewIndex >= 0) {
    statusEl.textContent = `Review Mode — Viewing position at Ply ${reviewIndex}. (Keys: [←/→] step, [End] live)`;
    btnResign.style.display = "none";
    return;
  }

  if (!state.active) {
    if (state.result) {
      statusEl.textContent = `Game Over — ${state.result}`;
    } else {
      statusEl.textContent = "Configure match parameters and click Start Match";
    }
    btnResign.style.display = "none";
    return;
  }

  btnResign.style.display = state.human_side ? "inline-flex" : "none";
  const cp = state.current_player;
  const human = state.human_side;
  if (!cp) return;

  if (!human) {
    statusEl.textContent = `Ply ${state.ply} — Watching AI match (${cp.toUpperCase()} to move)`;
  } else if (cp === human) {
    statusEl.textContent = `Ply ${state.ply} — Your turn to move as ${cp.toUpperCase()}`;
  } else {
    statusEl.textContent = `Ply ${state.ply} — AI (${cp.toUpperCase()}) is thinking…`;
  }
}

function renderResult() {
  if (!state.result) {
    resultOverlay.style.display = "none";
    return;
  }

  resultOverlay.style.display = "flex";
  const res = state.result.toLowerCase();

  if (res.includes("draw")) {
    resultIcon.textContent = "🤝";
    resultTitle.textContent = "Draw Game";
    resultTitle.style.color = "#f59e0b";
  } else if (res.includes("white") && (res.includes("wins") || !res.includes("loses"))) {
    resultIcon.textContent = "♔";
    resultTitle.textContent = "White Wins!";
    resultTitle.style.color = "#99f6e4";
    sounds.playVictory();
  } else if (res.includes("black") && (res.includes("wins") || !res.includes("loses"))) {
    resultIcon.textContent = "♚";
    resultTitle.textContent = "Black Wins!";
    resultTitle.style.color = "#38bdf8";
    sounds.playVictory();
  } else {
    resultIcon.textContent = "🏁";
    resultTitle.textContent = "Match Concluded";
    resultTitle.style.color = "#f59e0b";
  }

  resultSub.textContent = state.result;
  whiteSpinner.style.display = "none";
  blackSpinner.style.display = "none";
  whiteBar.classList.remove("active-turn");
  blackBar.classList.remove("active-turn");
}

// ── Scrubbing / Move Review Controller ────────────────────────────
function setReviewIndex(idx) {
  const total = (state.move_history || []).length;
  if (total === 0) {
    reviewIndex = -1;
    renderAll();
    return;
  }

  if (idx < -1) idx = -1;
  if (idx > total) idx = -1; // wrap past last move back to live

  reviewIndex = idx;
  renderBoard();
  renderHistory();
  renderPlayerBars();
  renderEvaluation();
  renderClocks();
  renderStatus();
  updateNavControls();
}

function updateNavControls() {
  const total = (state.move_history || []).length;
  if (!btnNavFirst) return;

  if (total === 0) {
    btnNavFirst.disabled = true;
    btnNavPrev.disabled = true;
    btnNavNext.disabled = true;
    btnNavLast.disabled = true;
    navStatusDot.className = "nav-status-dot live-dot";
    navPlyText.textContent = "Live Game";
    reviewBanner.style.display = "none";
    return;
  }

  if (reviewIndex === -1) {
    // Live Game mode
    btnNavFirst.disabled = false;
    btnNavPrev.disabled = false;
    btnNavNext.disabled = true;
    btnNavLast.disabled = true;
    navStatusDot.className = "nav-status-dot live-dot";
    navPlyText.textContent = state.active ? `Live • Ply ${state.ply}` : (state.result ? "Game Over" : "Live Game");
    reviewBanner.style.display = "none";
  } else {
    // Review mode active
    btnNavFirst.disabled = (reviewIndex === 0);
    btnNavPrev.disabled = (reviewIndex === 0);
    btnNavNext.disabled = false;
    btnNavLast.disabled = false;
    navStatusDot.className = "nav-status-dot review-dot";
    navPlyText.textContent = `Review Ply ${reviewIndex} / ${total}`;
    reviewBanner.style.display = "flex";

    if (reviewIndex === 0) {
      reviewPlyNum.textContent = "0 (Initial Board)";
    } else {
      const mv = state.move_history[reviewIndex - 1];
      const pDesc = mv ? `${mv.player.toUpperCase()} ${mv.piece}` : `Move ${reviewIndex}`;
      reviewPlyNum.textContent = `${reviewIndex} (${pDesc})`;
    }
  }
}

// Navigation button bindings
btnNavFirst.addEventListener("click", () => {
  if ((state.move_history || []).length > 0) {
    setReviewIndex(0);
  }
});

btnNavPrev.addEventListener("click", () => {
  const total = (state.move_history || []).length;
  if (total === 0) return;
  if (reviewIndex === -1) {
    setReviewIndex(Math.max(0, total - 1));
  } else {
    setReviewIndex(Math.max(0, reviewIndex - 1));
  }
});

btnNavNext.addEventListener("click", () => {
  const total = (state.move_history || []).length;
  if (reviewIndex >= 0) {
    if (reviewIndex < total) {
      setReviewIndex(reviewIndex + 1);
    } else {
      setReviewIndex(-1); // Return to live
    }
  }
});

btnNavLast.addEventListener("click", () => {
  setReviewIndex(-1);
});

btnJumpLive.addEventListener("click", () => {
  setReviewIndex(-1);
  showToast("⚡ Returned to Live Position");
});

// ── Event Handlers & Interactions ─────────────────────────────────

// Side Picker (with Auto-Flip)
sidePicker.querySelectorAll(".side-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    sidePicker.querySelectorAll(".side-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    myChoice = btn.dataset.side;

    // Auto flip board perspective according to chosen color
    if (myChoice === "black") {
      isFlipped = true;
    } else if (myChoice === "white" || myChoice === "watch") {
      isFlipped = false;
    }

    renderAll();
    showToast(isFlipped ? "Perspective: Black (Auto-Flipped to bottom)" : "Perspective: White (Bottom)");
  });
});

// Right Piece Style Selector
if (rightStyleSelect) {
  rightStyleSelect.addEventListener("change", (e) => {
    rightPieceStyle = e.target.value;
    localStorage.setItem("chess_right_style", rightPieceStyle);
    renderAll();
    showToast(`Right piece style: ${rightStyleSelect.options[rightStyleSelect.selectedIndex].text}`);
  });
}

// Watch Speed Range Slider
speedRange.addEventListener("input", (e) => {
  const val = parseFloat(e.target.value);
  speedVal.textContent = `${val.toFixed(1)}s`;
  socket.emit("set_watch_speed", { delay: val });
});

// Start New Game
btnNewGame.addEventListener("click", () => {
  sounds.init();
  lastFrom = null;
  lastTo = null;
  reviewIndex = -1;
  resultOverlay.style.display = "none";

  // Auto flip according to side choice
  if (myChoice === "black") {
    isFlipped = true;
  } else if (myChoice === "white" || myChoice === "watch") {
    isFlipped = false;
  }

  socket.emit("new_game", {
    human_side: myChoice,
    board_sample: boardSelect.value,
    opponent_type: oppSelect.value,
    watch_delay: parseFloat(speedRange.value),
    time_control: parseFloat(tcSelect.value),
  });

  addLog(
    `Initiating match: Variant=${boardSelect.value} | Mode=${myChoice} | Clock=${tcSelect.options[tcSelect.selectedIndex].text}`,
    "info"
  );
});

btnPlayAgain.addEventListener("click", () => {
  btnNewGame.click();
});
btnCloseResult.addEventListener("click", () => {
  resultOverlay.style.display = "none";
});

// Undo Move
function triggerUndo() {
  if (!state.active && !state.result) {
    showToast("No match active to undo");
    return;
  }
  reviewIndex = -1;
  socket.emit("undo_move");
  sounds.playMove();
}
btnUndoMove.addEventListener("click", triggerUndo);
btnUndoAction.addEventListener("click", triggerUndo);

// Resign
btnResign.addEventListener("click", () => {
  if (confirm("Are you sure you want to resign this game?")) {
    socket.emit("resign");
  }
});

// Manual Flip Board Toggle
btnFlipBoard.addEventListener("click", () => {
  isFlipped = !isFlipped;
  renderAll();
  showToast(isFlipped ? "Board flipped (Black perspective)" : "Board flipped (White perspective)");
});

// Sound Toggle
btnSoundToggle.addEventListener("click", () => {
  sounds.enabled = !sounds.enabled;
  soundIcon.textContent = sounds.enabled ? "🔊" : "🔇";
  showToast(sounds.enabled ? "Move sounds enabled" : "Move sounds muted");
});

// Stop Hosting
btnStopHosting.addEventListener("click", () => {
  if (confirm("Stop hosting the Chess Fragments server?\nThe server process will terminate.")) {
    socket.emit("shutdown_server");
    showToast("Server stopping. You may close this tab.");
    setTimeout(() => {
      document.body.innerHTML = `
        <div style="height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:sans-serif;color:#94a3b8;background:#090f12;gap:1rem;">
          <h2 style="color:#f8fafc;">Server Stopped</h2>
          <p>The Chess Fragments UI server on port 5000 has been shut down.</p>
          <p>To restart hosting, double-click <code style="color:#2dd4bf;">start_ui.bat</code> in the project folder.</p>
        </div>`;
    }, 500);
  }
});

// Load Agent
btnLoadAgent.addEventListener("click", () => {
  const name = agentSelect.value;
  if (!name) return;
  socket.emit("load_agent", { filename: name });
});

// Quick Chips
document.querySelectorAll(".chip-btn").forEach((chip) => {
  chip.addEventListener("click", () => {
    const filename = chip.dataset.file;
    if (filename) {
      agentSelect.value = filename;
      socket.emit("load_agent", { filename });
    }
  });
});

// Promote to Main agent.py
btnPromoteAgent.addEventListener("click", () => {
  const chosen = agentSelect.value;
  if (!chosen) {
    showToast("Please select an agent file first");
    return;
  }
  if (confirm(`Set '${chosen}' as your primary tournament agent.py?\n(Current agent.py will be backed up automatically)`)) {
    socket.emit("set_as_main_agent", { filename: chosen });
  }
});

// Runner Guide Modal
btnOpenGuide.addEventListener("click", () => {
  guideModal.style.display = "flex";
});
btnCloseGuide.addEventListener("click", () => {
  guideModal.style.display = "none";
});
btnGuideGotIt.addEventListener("click", () => {
  guideModal.style.display = "none";
});

// Keyboard Shortcuts
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;

  // Move Scrubbing Navigation Keys
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    btnNavPrev.click();
    return;
  }
  if (e.key === "ArrowRight") {
    e.preventDefault();
    btnNavNext.click();
    return;
  }
  if (e.key === "Home") {
    e.preventDefault();
    btnNavFirst.click();
    return;
  }
  if (e.key === "End") {
    e.preventDefault();
    btnNavLast.click();
    return;
  }

  // Quick action shortcuts
  if (e.key === "u" || e.key === "U" || (e.ctrlKey && (e.key === "z" || e.key === "Z"))) {
    e.preventDefault();
    triggerUndo();
  }
  if (e.key === "n" || e.key === "N") btnNewGame.click();
  if ((e.key === "r" || e.key === "R") && state.active && state.human_side) btnResign.click();
  if (e.key === "f" || e.key === "F") btnFlipBoard.click();
  if (e.key === "Escape") {
    resultOverlay.style.display = "none";
    guideModal.style.display = "none";
  }
});

// Initial boot
socket.emit("list_agents");
addLog("Chess Fragments Grandmaster UI ready", "info");
