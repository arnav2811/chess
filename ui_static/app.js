/* ══════════════════════════════════════════════════════════════════
   Chess Fragments AI Arena — app.js
   Royal English Emerald & Bone White Theme Inspired by Chess.com
   ══════════════════════════════════════════════════════════════════ */

"use strict";

// ── High-Definition Vector Chess Piece Library (Staunton / Neo) ───
// Self-contained, resolution-independent vector pieces inspired by Chess.com
const SVG_PIECES = {
  white: {
    pawn: `<svg viewBox="0 0 45 45" class="piece-svg">
      <path d="M 22.5 9 C 20.3 9 18.5 10.8 18.5 13 C 18.5 13.9 18.8 14.7 19.3 15.4 C 17.3 16.5 16 18.6 16 21 C 16 23 16.9 24.8 18.4 26 C 15.4 27.1 11 31.6 11 39.5 L 34 39.5 C 34 31.6 29.6 27.1 26.6 26 C 28.1 24.8 29 23 29 21 C 29 18.6 27.7 16.5 25.7 15.4 C 26.2 14.7 26.5 13.9 26.5 13 C 26.5 10.8 24.7 9 22.5 9 Z" fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
      <path d="M 12 39.5 L 33 39.5" stroke="#16241a" stroke-width="1.6"/>
    </svg>`,
    knight: `<svg viewBox="0 0 45 45" class="piece-svg">
      <path d="M 22 10 C 32.5 11 38.5 18 38 39 L 14 39 C 14 30.5 23.5 32 22 17 C 22 17 20 16 18 19 C 16.5 21 14.5 21.5 12.5 20 C 11 18.5 12 16 13.5 14.5 C 15 13 17.5 11.5 19.5 11 C 20 8.5 21 6.5 22 10 Z" fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round"/>
      <circle cx="16" cy="17" r="1.5" fill="#16241a"/>
      <path d="M 12 39 L 37 39" stroke="#16241a" stroke-width="1.6"/>
      <path d="M 24 16 C 26 21 28 26 33 29" fill="none" stroke="#16241a" stroke-width="1.3" stroke-linecap="round"/>
    </svg>`,
    bishop: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 C 36 34.5 31.5 32 30 29 C 33 25.5 34.5 20 31.5 14 C 28.5 8 22.5 8 22.5 8 C 22.5 8 16.5 8 13.5 14 C 10.5 20 12 25.5 15 29 C 13.5 32 9 34.5 9 39 Z"/>
        <circle cx="22.5" cy="6" r="2.2" fill="#ffffff"/>
        <path d="M 17.5 26 L 27.5 26"/>
        <path d="M 22.5 13 L 22.5 21" stroke-width="1.4"/>
        <path d="M 19 16 L 26 16" stroke-width="1.4"/>
      </g>
    </svg>`,
    rook: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 22 L 35 19 L 35 11 L 30.5 11 L 30.5 15 L 26.5 15 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 15 L 14.5 15 L 14.5 11 L 10 11 L 10 19 L 12 22 L 12 33.5 L 9 35.5 Z"/>
        <path d="M 12 35.5 L 33 35.5"/>
        <path d="M 13 22 L 32 22"/>
      </g>
    </svg>`,
    queen: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 L 37 34 L 33 24 L 38 15 L 29.5 23 L 22.5 12 L 15.5 23 L 7 15 L 12 24 L 8 34 Z"/>
        <circle cx="7" cy="13.5" r="2"/>
        <circle cx="15.5" cy="11.5" r="2"/>
        <circle cx="22.5" cy="9.5" r="2"/>
        <circle cx="29.5" cy="11.5" r="2"/>
        <circle cx="38" cy="13.5" r="2"/>
        <path d="M 11 34 L 34 34"/>
      </g>
    </svg>`,
    king: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 22.5 11.5 L 22.5 5 M 19 8 L 26 8" stroke-width="2"/>
        <path d="M 9 39 L 36 39 L 36 34 C 36 31 32 28 32 25 C 36 21 35 14 31 13 C 27 12 23 16 22.5 16 C 22 16 18 12 14 13 C 10 14 9 21 13 25 C 13 28 9 31 9 34 Z"/>
        <circle cx="22.5" cy="19.5" r="2.5" fill="#16241a"/>
        <path d="M 12 35 L 33 35"/>
      </g>
    </svg>`,
    right: {
      fairy: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <!-- Castle Tower Body -->
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 14.5 L 26.5 14.5 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 14.5 L 14.5 14.5 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <path d="M 13 21 L 32 21"/>
        </g>
        <!-- Stylized Double-Struck ℝ Insignia -->
        <text x="22.5" y="30.5" font-family="'Cambria Math', 'Times New Roman', serif" font-size="12" font-weight="900" fill="#16241a" text-anchor="middle">ℝ</text>
      </svg>`,
      hybrid: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 14.5 L 26.5 14.5 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 14.5 L 14.5 14.5 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <!-- Knight Crest Head -->
          <path d="M 18 29 C 19 23 23 21 27 23 C 25 25 24 28 22 29 Z" fill="#2d6a4f" stroke="#16241a" stroke-width="1.2"/>
        </g>
      </svg>`,
      standard: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#ffffff" stroke="#16241a" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 15 L 26.5 15 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 15 L 14.5 15 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <path d="M 13 21 L 32 21"/>
        </g>
      </svg>`
    }
  },
  black: {
    pawn: `<svg viewBox="0 0 45 45" class="piece-svg">
      <path d="M 22.5 9 C 20.3 9 18.5 10.8 18.5 13 C 18.5 13.9 18.8 14.7 19.3 15.4 C 17.3 16.5 16 18.6 16 21 C 16 23 16.9 24.8 18.4 26 C 15.4 27.1 11 31.6 11 39.5 L 34 39.5 C 34 31.6 29.6 27.1 26.6 26 C 28.1 24.8 29 23 29 21 C 29 18.6 27.7 16.5 25.7 15.4 C 26.2 14.7 26.5 13.9 26.5 13 C 26.5 10.8 24.7 9 22.5 9 Z" fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
      <path d="M 12 39.5 L 33 39.5" stroke="#f0f7f2" stroke-width="1.4"/>
    </svg>`,
    knight: `<svg viewBox="0 0 45 45" class="piece-svg">
      <path d="M 22 10 C 32.5 11 38.5 18 38 39 L 14 39 C 14 30.5 23.5 32 22 17 C 22 17 20 16 18 19 C 16.5 21 14.5 21.5 12.5 20 C 11 18.5 12 16 13.5 14.5 C 15 13 17.5 11.5 19.5 11 C 20 8.5 21 6.5 22 10 Z" fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round"/>
      <circle cx="16" cy="17" r="1.5" fill="#f0f7f2"/>
      <path d="M 12 39 L 37 39" stroke="#f0f7f2" stroke-width="1.4"/>
      <path d="M 24 16 C 26 21 28 26 33 29" fill="none" stroke="#52b788" stroke-width="1.2" stroke-linecap="round"/>
    </svg>`,
    bishop: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 C 36 34.5 31.5 32 30 29 C 33 25.5 34.5 20 31.5 14 C 28.5 8 22.5 8 22.5 8 C 22.5 8 16.5 8 13.5 14 C 10.5 20 12 25.5 15 29 C 13.5 32 9 34.5 9 39 Z"/>
        <circle cx="22.5" cy="6" r="2.2" fill="#18251e"/>
        <path d="M 17.5 26 L 27.5 26"/>
        <path d="M 22.5 13 L 22.5 21" stroke-width="1.4" stroke="#52b788"/>
        <path d="M 19 16 L 26 16" stroke-width="1.4" stroke="#52b788"/>
      </g>
    </svg>`,
    rook: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 22 L 35 19 L 35 11 L 30.5 11 L 30.5 15 L 26.5 15 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 15 L 14.5 15 L 14.5 11 L 10 11 L 10 19 L 12 22 L 12 33.5 L 9 35.5 Z"/>
        <path d="M 12 35.5 L 33 35.5"/>
        <path d="M 13 22 L 32 22"/>
      </g>
    </svg>`,
    queen: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 9 39 L 36 39 L 37 34 L 33 24 L 38 15 L 29.5 23 L 22.5 12 L 15.5 23 L 7 15 L 12 24 L 8 34 Z"/>
        <circle cx="7" cy="13.5" r="2"/>
        <circle cx="15.5" cy="11.5" r="2"/>
        <circle cx="22.5" cy="9.5" r="2"/>
        <circle cx="29.5" cy="11.5" r="2"/>
        <circle cx="38" cy="13.5" r="2"/>
        <path d="M 11 34 L 34 34"/>
      </g>
    </svg>`,
    king: `<svg viewBox="0 0 45 45" class="piece-svg">
      <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
        <path d="M 22.5 11.5 L 22.5 5 M 19 8 L 26 8" stroke-width="2" stroke="#52b788"/>
        <path d="M 9 39 L 36 39 L 36 34 C 36 31 32 28 32 25 C 36 21 35 14 31 13 C 27 12 23 16 22.5 16 C 22 16 18 12 14 13 C 10 14 9 21 13 25 C 13 28 9 31 9 34 Z"/>
        <circle cx="22.5" cy="19.5" r="2.5" fill="#52b788"/>
        <path d="M 12 35 L 33 35"/>
      </g>
    </svg>`,
    right: {
      fairy: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 14.5 L 26.5 14.5 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 14.5 L 14.5 14.5 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <path d="M 13 21 L 32 21"/>
        </g>
        <text x="22.5" y="30.5" font-family="'Cambria Math', 'Times New Roman', serif" font-size="12" font-weight="900" fill="#74c69d" text-anchor="middle">ℝ</text>
      </svg>`,
      hybrid: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 14.5 L 26.5 14.5 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 14.5 L 14.5 14.5 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <path d="M 18 29 C 19 23 23 21 27 23 C 25 25 24 28 22 29 Z" fill="#52b788" stroke="#f0f7f2" stroke-width="1.2"/>
        </g>
      </svg>`,
      standard: `<svg viewBox="0 0 45 45" class="piece-svg piece-right-svg">
        <g fill="#18251e" stroke="#f0f7f2" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M 9 39 L 36 39 L 36 35.5 L 33 33.5 L 33 21 L 35 18 L 35 11 L 30.5 11 L 30.5 15 L 26.5 15 L 26.5 11 L 22.5 11 L 18.5 11 L 18.5 15 L 14.5 15 L 14.5 11 L 10 11 L 10 18 L 12 21 L 12 33.5 L 9 35.5 Z"/>
          <path d="M 12 35.5 L 33 35.5"/>
          <path d="M 13 21 L 32 21"/>
        </g>
      </svg>`
    }
  }
};

// ── Piece Unicode Symbols (Classic Fallback) ──────────────────────
const PIECE_SYMBOLS = {
  king:   { white: "♔", black: "♚" },
  queen:  { white: "♕", black: "♛" },
  right:  { white: "♜", black: "♜" },
  bishop: { white: "♗", black: "♝" },
  knight: { white: "♘", black: "♞" },
  pawn:   { white: "♙", black: "♟" },
};

// ── Web Audio Synthesizer (Authentic Tournament Wood Board Taps) ──
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
    const now = this.ctx.currentTime;

    // High transient piece-contact click
    const oscClick = this.ctx.createOscillator();
    const gainClick = this.ctx.createGain();
    oscClick.type = "sine";
    oscClick.frequency.setValueAtTime(820, now);
    oscClick.frequency.exponentialRampToValueAtTime(110, now + 0.024);
    gainClick.gain.setValueAtTime(0.35, now);
    gainClick.gain.exponentialRampToValueAtTime(0.001, now + 0.024);
    oscClick.connect(gainClick);
    gainClick.connect(this.ctx.destination);
    oscClick.start(now);
    oscClick.stop(now + 0.025);

    // Deep resonant acoustic wood thump (Chess.com wood piece impact)
    const oscWood = this.ctx.createOscillator();
    const gainWood = this.ctx.createGain();
    oscWood.type = "triangle";
    oscWood.frequency.setValueAtTime(205, now);
    oscWood.frequency.exponentialRampToValueAtTime(80, now + 0.085);
    gainWood.gain.setValueAtTime(0.42, now);
    gainWood.gain.exponentialRampToValueAtTime(0.001, now + 0.085);
    oscWood.connect(gainWood);
    gainWood.connect(this.ctx.destination);
    oscWood.start(now);
    oscWood.stop(now + 0.09);
  }

  playCapture() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    const now = this.ctx.currentTime;

    // Crisp double-wood strike
    const osc1 = this.ctx.createOscillator();
    const gain1 = this.ctx.createGain();
    osc1.type = "triangle";
    osc1.frequency.setValueAtTime(440, now);
    osc1.frequency.exponentialRampToValueAtTime(130, now + 0.075);
    gain1.gain.setValueAtTime(0.48, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.075);
    osc1.connect(gain1);
    gain1.connect(this.ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.08);

    const osc2 = this.ctx.createOscillator();
    const gain2 = this.ctx.createGain();
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(180, now + 0.015);
    osc2.frequency.exponentialRampToValueAtTime(65, now + 0.11);
    gain2.gain.setValueAtTime(0.38, now + 0.015);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
    osc2.connect(gain2);
    gain2.connect(this.ctx.destination);
    osc2.start(now + 0.015);
    osc2.stop(now + 0.115);
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
let isFlipped = false;  // board perspective
let agentThinking = false;
let reviewIndex = -1;   // -1 = live, 0 = initial position, 1..N = after move N
let serverTimeOffset = 0; // ms difference between server timestamp and client clock

// User Preferences & Visual Theme State
let currentBoardTheme = localStorage.getItem("chess_board_theme") || "tournament-green";
let currentPieceSet   = localStorage.getItem("chess_piece_set") || "staunton-svg";
let rightPieceStyle   = localStorage.getItem("chess_right_style") || "fairy";

// Initialize Board Theme attribute on document root
document.documentElement.setAttribute("data-board-theme", currentBoardTheme);

// ── DOM References ────────────────────────────────────────────────
const boardEl          = document.getElementById("board");
const statusEl         = document.getElementById("status-text");
const historyEl        = document.getElementById("move-history");
const moveCountBadge   = document.getElementById("move-count-badge");
const logEl            = document.getElementById("log-panel");
const agentSelect      = document.getElementById("agent-select");
const headerAgentName  = document.getElementById("header-agent-name");
const boardSelect      = document.getElementById("board-select");
const boardThemeSelect = document.getElementById("board-theme-select");
const pieceSetSelect   = document.getElementById("piece-set-select");
const rightStyleSelect = document.getElementById("right-style-select");
const tcSelect         = document.getElementById("tc-select");
const oppSelect        = document.getElementById("opp-select");
const sidePicker       = document.getElementById("side-picker");
const speedRange       = document.getElementById("speed-range");
const speedVal         = document.getElementById("speed-val");
const btnNewGame       = document.getElementById("btn-new-game");
const btnResign        = document.getElementById("btn-resign");
const btnResignLedger  = document.getElementById("btn-resign-ledger");
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
const whiteTitleBadge  = document.getElementById("white-title-badge");
const blackTitleBadge  = document.getElementById("black-title-badge");
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

// Initialize Select Dropdowns
if (boardThemeSelect) boardThemeSelect.value = currentBoardTheme;
if (pieceSetSelect)   pieceSetSelect.value   = currentPieceSet;
if (rightStyleSelect) rightStyleSelect.value = rightPieceStyle;

// ── Toast Banner Notification ─────────────────────────────────────
function showToast(msg, duration = 2800) {
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
    showToast(`✓ Loaded engine: ${name}`);
  } else {
    showToast(`✗ Failed to load engine: ${error || "error"}`);
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

// ── Piece Visual Resolvers (Vector SVG vs Unicode) ────────────────
function getPieceSvg(name, color) {
  const colSet = SVG_PIECES[color] || SVG_PIECES.white;
  if (name === "right") {
    const rSet = colSet.right || SVG_PIECES.white.right;
    return rSet[rightPieceStyle] || rSet.fairy;
  }
  return colSet[name] || colSet.pawn;
}

function getPieceUnicode(name, color) {
  if (name === "right") {
    if (rightPieceStyle === "fairy") return "ℝ";
    if (rightPieceStyle === "hybrid") return "♜ᴷ";
    return PIECE_SYMBOLS.right[color] || "♜";
  }
  return PIECE_SYMBOLS[name]?.[color] ?? "?";
}

// ── Clocks Ticking (High-Precision Server Epoch Synchronized) ─────
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
  if (reviewIndex > 0 && state.move_history && state.move_history[reviewIndex - 1]) {
    const snap = state.move_history[reviewIndex - 1];
    if (snap.white_time !== undefined && snap.black_time !== undefined) {
      return { white: snap.white_time, black: snap.black_time };
    }
  }

  if (!state.active || state.result || state.time_control === 0) {
    return {
      white: state.white_time_left ?? 300,
      black: state.black_time_left ?? 300,
    };
  }

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
      <div style="grid-column: 1/-1; grid-row: 1/-1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.6rem; color:#52b788; font-size:0.85rem; text-align:center;">
        <span style="font-size:2.4rem; color:#52b788; opacity:0.6;">♔</span>
        Click <strong>▶ Start Match</strong><br/>to begin match
      </div>`;
    whiteSpinner.style.display = "none";
    blackSpinner.style.display = "none";
    return;
  }

  const isReviewing = reviewIndex >= 0;
  const legalSet = isReviewing ? new Set() : new Set((state.legal_targets || []).map(([x, y]) => `${x},${y}`));
  const highlights = getActiveMoveHighlights();

  // Perspective:
  // When isFlipped is false (White perspective): White (y=4) at bottom, Black (y=0) at top
  // When isFlipped is true (Black perspective): Black (y=0) at bottom, White (y=4) at top
  const yCoords = isFlipped ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
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

      // Chess.com style embedded corner coordinates
      if (c === 0) {
        const rankSpan = document.createElement("span");
        rankSpan.className = `sq-coord sq-coord-rank ${isLight ? "coord-dark" : "coord-light"}`;
        rankSpan.textContent = y;
        sq.appendChild(rankSpan);
      }
      if (r === 4) {
        const fileSpan = document.createElement("span");
        fileSpan.className = `sq-coord sq-coord-file ${isLight ? "coord-dark" : "coord-light"}`;
        fileSpan.textContent = x;
        sq.appendChild(fileSpan);
      }

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
        const pieceEl = document.createElement("div");
        pieceEl.className = `piece ${cell.color}-piece`;

        if (currentPieceSet === "staunton-svg") {
          pieceEl.innerHTML = getPieceSvg(cell.piece, cell.color);
        } else {
          pieceEl.classList.add("piece-unicode");
          pieceEl.textContent = getPieceUnicode(cell.piece, cell.color);
          if (cell.piece === "right") {
            if (rightPieceStyle === "fairy") pieceEl.classList.add("piece-right-fairy");
            else if (rightPieceStyle === "standard") pieceEl.classList.add("piece-right-badge");
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
    showToast("Viewing move history. Click '⚡ Return to Live' to play.");
    return;
  }
  if (!state.active || state.result) return;
  const human = state.human_side;
  if (human && state.current_player !== human) return;
  sounds.init();
  socket.emit("select_square", { x, y });
}

// ── Chess.com Paired-Turn Move Ledger Table ────────────────────────
function renderHistory() {
  const hist = state.move_history || [];
  moveCountBadge.textContent = `${hist.length} plies`;

  if (hist.length === 0) {
    historyEl.innerHTML = '<div class="history-empty">No moves recorded yet</div>';
    return;
  }

  historyEl.innerHTML = "";
  const totalTurns = Math.ceil(hist.length / 2);

  for (let t = 0; t < totalTurns; t++) {
    const whiteIdx = t * 2;
    const blackIdx = t * 2 + 1;
    const whiteMove = hist[whiteIdx];
    const blackMove = hist[blackIdx];

    const turnRow = document.createElement("div");
    turnRow.className = "turn-row";

    // Turn Number
    const numCol = document.createElement("span");
    numCol.className = "turn-num";
    numCol.textContent = `${t + 1}.`;
    turnRow.appendChild(numCol);

    // White Move Cell
    const whiteCell = createMoveCell(whiteMove, whiteIdx, hist.length);
    turnRow.appendChild(whiteCell);

    // Black Move Cell
    if (blackMove) {
      const blackCell = createMoveCell(blackMove, blackIdx, hist.length);
      turnRow.appendChild(blackCell);
    } else {
      const emptyCell = document.createElement("div");
      emptyCell.className = "turn-cell empty-cell";
      turnRow.appendChild(emptyCell);
    }

    historyEl.appendChild(turnRow);
  }

  // Scroll active move into view
  const activeCell = historyEl.querySelector(".active-review-move") || historyEl.querySelector(".active-live-move");
  if (activeCell) {
    activeCell.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } else if (reviewIndex === -1) {
    historyEl.scrollTop = historyEl.scrollHeight;
  }
}

function createMoveCell(m, idx, totalHistLen) {
  const cell = document.createElement("div");
  cell.className = "turn-cell";

  const plyNum = idx + 1;
  const isReviewed = (reviewIndex === plyNum);
  const isLiveLatest = (reviewIndex === -1 && idx === totalHistLen - 1);

  if (isReviewed) {
    cell.classList.add("active-review-move");
  } else if (isLiveLatest) {
    cell.classList.add("active-live-move");
  }

  const pSymbol = getPieceUnicode(m.piece, m.player);
  const isCap = Boolean(m.captured);
  const notation = `${pSymbol} (${m.from[0]},${m.from[1]})${isCap ? '×' : '→'}(${m.to[0]},${m.to[1]})`;
  const timeTag = m.agent_time ? `<span class="move-time-tag">${m.agent_time}s</span>` : '';

  cell.innerHTML = `
    <span class="move-notation ${isCap ? 'is-cap-move' : ''}">${notation}</span>
    ${timeTag}
  `;

  cell.addEventListener("click", () => {
    setReviewIndex(plyNum);
  });

  return cell;
}

function renderStats() {
  const s = state.agent_stats || {};
  document.getElementById("stat-time").textContent = s.time ? `${s.time}s` : "—";
  document.getElementById("stat-depth").textContent = s.depth ? `${s.depth} plies` : "—";
  document.getElementById("stat-nodes").textContent = s.nodes ? s.nodes.toLocaleString() : "—";
  document.getElementById("stat-ply").textContent = reviewIndex >= 0 ? `${reviewIndex} (Rev)` : (state.ply || "—");
}

function renderPlayerBars() {
  const human = (state.active || state.result) ? state.human_side : (myChoice === "watch" ? null : myChoice);
  if (human === "white") {
    whiteTitleBadge.textContent = "YOU";
    whiteTitleBadge.className = "player-title-badge white-title";
    blackTitleBadge.textContent = "BOT";
    blackTitleBadge.className = "player-title-badge";
    whiteRole.textContent = "Human";
    blackRole.textContent = `AI (${state.agent_name || "Agent"})`;
  } else if (human === "black") {
    blackTitleBadge.textContent = "YOU";
    blackTitleBadge.className = "player-title-badge white-title";
    whiteTitleBadge.textContent = "BOT";
    whiteTitleBadge.className = "player-title-badge";
    blackRole.textContent = "Human";
    whiteRole.textContent = `AI (${state.agent_name || "Agent"})`;
  } else {
    whiteTitleBadge.textContent = "AI";
    whiteTitleBadge.className = "player-title-badge white-title";
    blackTitleBadge.textContent = "BOT";
    blackTitleBadge.className = "player-title-badge";
    whiteRole.textContent = `AI (${state.agent_name || "Agent"})`;
    blackRole.textContent = `Opponent (${state.opponent_type || "AI"})`;
  }

  // Perspective bar ordering: player's side always sits at the bottom
  if (isFlipped) {
    whiteBar.style.order = "1";
    blackBar.style.order = "3";
  } else {
    blackBar.style.order = "1";
    whiteBar.style.order = "3";
  }

  // Captured pieces tray
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
    .map((p) => `<span class="cap-chip" title="Captured Black ${p}">${getPieceUnicode(p, "black")}</span>`)
    .join("");

  blackCaptured.innerHTML = capBlack
    .map((p) => `<span class="cap-chip" title="Captured White ${p}">${getPieceUnicode(p, "white")}</span>`)
    .join("");

  // Material Advantage badges (+1, +3)
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
    statusEl.textContent = `Review Mode — Viewing Ply ${reviewIndex}. (Keys: [←/→] step, [End] live)`;
    btnResign.style.display = "none";
    if (btnResignLedger) btnResignLedger.style.display = "none";
    return;
  }

  if (!state.active) {
    if (state.result) {
      statusEl.textContent = `Game Over — ${state.result}`;
    } else {
      statusEl.textContent = "Configure match parameters and click Start Match";
    }
    btnResign.style.display = "none";
    if (btnResignLedger) btnResignLedger.style.display = "none";
    return;
  }

  const showResign = state.human_side ? "inline-flex" : "none";
  btnResign.style.display = showResign;
  if (btnResignLedger) btnResignLedger.style.display = showResign;
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
    resultTitle.style.color = "#e5c158";
  } else if (res.includes("white") && (res.includes("wins") || !res.includes("loses"))) {
    resultIcon.textContent = "♔";
    resultTitle.textContent = "White Wins!";
    resultTitle.style.color = "#74c69d";
    sounds.playVictory();
  } else if (res.includes("black") && (res.includes("wins") || !res.includes("loses"))) {
    resultIcon.textContent = "♚";
    resultTitle.textContent = "Black Wins!";
    resultTitle.style.color = "#52b788";
    sounds.playVictory();
  } else {
    resultIcon.textContent = "🏁";
    resultTitle.textContent = "Match Concluded";
    resultTitle.style.color = "#e5c158";
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
  if (idx > total) idx = -1;

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
    btnNavFirst.disabled = false;
    btnNavPrev.disabled = false;
    btnNavNext.disabled = true;
    btnNavLast.disabled = true;
    navStatusDot.className = "nav-status-dot live-dot";
    navPlyText.textContent = state.active ? `Live • Ply ${state.ply}` : (state.result ? "Game Over" : "Live Game");
    reviewBanner.style.display = "none";
  } else {
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

// ── Event Handlers & Theme Switching ──────────────────────────────

// Board Theme Switcher
if (boardThemeSelect) {
  boardThemeSelect.addEventListener("change", (e) => {
    currentBoardTheme = e.target.value;
    document.documentElement.setAttribute("data-board-theme", currentBoardTheme);
    localStorage.setItem("chess_board_theme", currentBoardTheme);
    showToast(`Board theme: ${boardThemeSelect.options[boardThemeSelect.selectedIndex].text}`);
  });
}

// Piece Set Switcher (SVG vs Unicode)
if (pieceSetSelect) {
  pieceSetSelect.addEventListener("change", (e) => {
    currentPieceSet = e.target.value;
    localStorage.setItem("chess_piece_set", currentPieceSet);
    renderAll();
    showToast(`Piece set: ${pieceSetSelect.options[pieceSetSelect.selectedIndex].text}`);
  });
}

// Right Piece Style Selector
if (rightStyleSelect) {
  rightStyleSelect.addEventListener("change", (e) => {
    rightPieceStyle = e.target.value;
    localStorage.setItem("chess_right_style", rightPieceStyle);
    renderAll();
    showToast(`Right piece style: ${rightStyleSelect.options[rightStyleSelect.selectedIndex].text}`);
  });
}

// Side Picker (with Auto-Flip)
sidePicker.querySelectorAll(".side-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    sidePicker.querySelectorAll(".side-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    myChoice = btn.dataset.side;

    if (myChoice === "black") {
      isFlipped = true;
    } else if (myChoice === "white" || myChoice === "watch") {
      isFlipped = false;
    }

    renderAll();
    showToast(isFlipped ? "Perspective: Black (Auto-Flipped to bottom)" : "Perspective: White (Bottom)");
  });
});

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
function triggerResign() {
  if (confirm("Are you sure you want to resign this game?")) {
    socket.emit("resign");
  }
}
btnResign.addEventListener("click", triggerResign);
if (btnResignLedger) btnResignLedger.addEventListener("click", triggerResign);

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

// Stop Hosting (2-Stage Confirmation with HTTP POST + SocketIO — No native popup blocker issues)
let stopConfirmActive = false;
let stopConfirmTimer = null;

btnStopHosting.addEventListener("click", async () => {
  if (!stopConfirmActive) {
    stopConfirmActive = true;
    btnStopHosting.classList.add("confirm-stop");
    btnStopHosting.innerHTML = "⚠️ Confirm Stop?";
    showToast("Click again to confirm server shutdown");
    clearTimeout(stopConfirmTimer);
    stopConfirmTimer = setTimeout(() => {
      stopConfirmActive = false;
      btnStopHosting.classList.remove("confirm-stop");
      btnStopHosting.innerHTML = "🛑 Stop Hosting";
    }, 4500);
    return;
  }

  // Second click = verified immediate shutdown
  clearTimeout(stopConfirmTimer);
  btnStopHosting.disabled = true;
  btnStopHosting.innerHTML = "⏳ Stopping…";
  showToast("🛑 Terminating Chess Fragments server process...");

  // Send through both SocketIO and HTTP POST route for 100% guarantee
  try {
    socket.emit("shutdown_server");
  } catch(e) {}

  try {
    await fetch("/api/shutdown", { method: "POST" });
  } catch(e) {}

  setTimeout(() => {
    document.body.innerHTML = `
      <div style="height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:'Plus Jakarta Sans',sans-serif;color:#a3b899;background:#0d1611;gap:1.2rem;text-align:center;padding:2rem;">
        <div style="font-size:3.5rem;">🛑</div>
        <h2 style="color:#ffffff;font-size:1.8rem;font-weight:800;letter-spacing:-0.02em;">Chess Fragments Server Stopped</h2>
        <p style="color:#92a498;max-width:440px;line-height:1.6;font-size:0.95rem;">
          The Python UI server process on port 5000 has been safely shut down. You can close this browser tab.
        </p>
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(82,183,136,0.3);padding:0.75rem 1.4rem;border-radius:8px;font-size:0.85rem;color:#e8f5e9;">
          To restart hosting anytime: double-click <code style="color:#52b788;font-weight:700;">start_ui.bat</code> in the project folder.
        </div>
      </div>`;
  }, 400);
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
addLog("Chess Fragments Royal English Grandmaster Arena ready", "info");
