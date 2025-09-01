#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Crossword (Flask single-file app)
====================================
- Run:  python app.py
- Open: http://127.0.0.1:5000
- UI in Spanish; code/comments in English.
- Accepts answers ignoring accents, spaces and case.
- No external assets; everything is embedded.
"""

import json
import unicodedata
from typing import List, Tuple, Dict, Optional

from flask import Flask, render_template_string, request, session, jsonify, redirect, url_for

# -------------------------
# Data: clues and answers
# -------------------------
RAW_ENTRIES = [
    ("Organismo mexicano encargado de proteger los recursos agrícolas, acuícolas y pecuarios contra plagas y enfermedades de importancia cuarentenaria.", "SENASICA"),
    ("Organismo internacional que da seguimiento al desarrollo de enfermedades animales terrestres y acuáticas para proteger la sanidad animal.", "WOAH"),
    ("Clasificación de zoonosis en la cual el patógeno necesita un huésped vertebrado y un reservorio inanimado (comida, suelo, planta) para completar su ciclo de vida.", "SAPROZOONOSIS"),
    ("Clasificación de zoonosis en la que el patógeno puede transmitirse en ambas direcciones: animal-humano y humano-animal.", "ANFIXENOSIS"),
    ("Concepto que reconoce la interconexión entre salud humana, salud animal y medio ambiente.", "UNA SOLA SALUD"),
    ("Biólogo alemán con ideología parecida al concepto de Una Sola Salud.", "VIRCHOW"),
    ("Zoonosis en la que el agente se transmite de animal a humano (ejemplo: rabia).", "ANTROPOZOONOSIS"),
    ("Enfermedades que los animales pueden transmitir a los humanos (más de 200 tipos).", "ZOONOSIS"),
    ("Se requiere una dosis mínima para generar una infección en el paciente.", "AGENTE"),
    ("Estado en que el animal o ser humano se encuentra en equilibrio fisiológico a nivel celular, tejido, órgano y sistema.", "SALUD"),
    ("Pérdida parcial o total del equilibrio fisiológico que produce signos.", "ENFERMEDAD"),
    ("Estado físico y mental de un animal en relación con las condiciones en las que vive y muere.", "BIENESTAR ANIMAL"),
    ("Comportamiento de los animales en su entorno natural que brinda información útil sobre el bienestar animal.", "ETIOLOGÍA"),
    ("Interacción entre agente, huésped y ambiente en la aparición de enfermedades.", "TRIADA EPIDEMIOLÓGICA"),
    ("Secuencia de eventos que describe cómo se propaga un patógeno.", "CADENA EPIDEMIOLÓGICA"),
    ("Ciencia encargada de estudiar las relaciones entre los organismos vivos y su entorno.", "ECOLOGÍA"),
    ("Amenaza global para casi todos los sistemas biológicos por cambios en temperatura, precipitaciones, humedad, calidad del aire y agua.", "CAMBIO CLIMÁTICO"),
    ("Reducción y aislamiento de un hábitat natural continuo en fragmentos más pequeños, con pérdida de biodiversidad y conflictos humano-fauna.", "FRAGMENTACIÓN DEL HÁBITAT"),
]

GRID_SIZE = 27

# -------------------------
# Normalization helpers
# -------------------------

def strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')

def normalize_answer(s: str) -> str:
    s = strip_accents(s).upper()
    return ''.join(ch for ch in s if 'A' <= ch <= 'Z')

# -------------------------
# Crossword structures
# -------------------------
class Placement:
    def __init__(self, word_id: int, row: int, col: int, orientation: str, length: int):
        self.word_id = word_id
        self.row = row
        self.col = col
        self.orientation = orientation  # 'H' or 'V'
        self.length = length
        self.number: Optional[int] = None

    def cells(self) -> List[Tuple[int, int]]:
        if self.orientation == 'H':
            return [(self.row, self.col + i) for i in range(self.length)]
        return [(self.row + i, self.col) for i in range(self.length)]

class Crossword:
    def __init__(self, entries: List[Tuple[str, str]]):
        self.entries = [
            {
                'clue': clue,
                'answer_original': ans,
                'answer_norm': normalize_answer(ans),
            }
            for clue, ans in entries
        ]
        self.order = sorted(range(len(self.entries)), key=lambda i: len(self.entries[i]['answer_norm']), reverse=True)
        self.grid: List[List[Optional[str]]] = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.used_mask: List[List[bool]] = [[False for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.placements: List[Placement] = []

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE

    def can_place(self, word: str, r: int, c: int, ori: str) -> Tuple[bool, int]:
        L = len(word)
        if ori == 'H':
            if c < 0 or c + L > GRID_SIZE or r < 0 or r >= GRID_SIZE:
                return (False, 0)
            if c - 1 >= 0 and self.grid[r][c - 1] is not None:
                return (False, 0)
            if c + L < GRID_SIZE and self.grid[r][c + L] is not None:
                return (False, 0)
            overlaps = 0
            for i in range(L):
                rr, cc = r, c + i
                cell = self.grid[rr][cc]
                if cell is not None and cell != word[i]:
                    return (False, 0)
                if cell == word[i]:
                    overlaps += 1
            return (True, overlaps)
        else:
            if r < 0 or r + L > GRID_SIZE or c < 0 or c >= GRID_SIZE:
                return (False, 0)
            if r - 1 >= 0 and self.grid[r - 1][c] is not None:
                return (False, 0)
            if r + L < GRID_SIZE and self.grid[r + L][c] is not None:
                return (False, 0)
            overlaps = 0
            for i in range(L):
                rr, cc = r + i, c
                cell = self.grid[rr][cc]
                if cell is not None and cell != word[i]:
                    return (False, 0)
                if cell == word[i]:
                    overlaps += 1
            return (True, overlaps)

    def place(self, word_id: int, r: int, c: int, ori: str):
        word = self.entries[word_id]['answer_norm']
        L = len(word)
        for i in range(L):
            rr, cc = (r, c + i) if ori == 'H' else (r + i, c)
            self.grid[rr][cc] = word[i]
            self.used_mask[rr][cc] = True
        self.placements.append(Placement(word_id, r, c, ori, L))

    def generate(self):
        for idx, word_id in enumerate(self.order):
            word = self.entries[word_id]['answer_norm']
            placed = False
            if idx == 0:
                r = GRID_SIZE // 2
                c = max(0, (GRID_SIZE - len(word)) // 2)
                self.place(word_id, r, c, 'H')
                placed = True
            else:
                best = None  # (overlaps, score_center, r, c, ori)
                for r in range(GRID_SIZE):
                    for c in range(GRID_SIZE):
                        cell = self.grid[r][c]
                        if cell is None:
                            continue
                        for j, ch in enumerate(word):
                            if ch != cell:
                                continue
                            # Horizontal
                            start_c = c - j
                            ok, ov = self.can_place(word, r, start_c, 'H')
                            if ok:
                                score = (ov, -abs(r - GRID_SIZE // 2) - abs(start_c - GRID_SIZE // 2))
                                cand = (score, r, start_c, 'H')
                                if best is None or cand[0] > best[0]:
                                    best = cand
                            # Vertical
                            start_r = r - j
                            ok, ov = self.can_place(word, start_r, c, 'V')
                            if ok:
                                score = (ov, -abs(start_r - GRID_SIZE // 2) - abs(c - GRID_SIZE // 2))
                                cand = (score, start_r, c, 'V')
                                if best is None or cand[0] > best[0]:
                                    best = cand
                if best is not None and best[0][0] > 0:
                    _, rr, cc, oo = best
                    self.place(word_id, rr, cc, oo)
                    placed = True
                if not placed:
                    for oo in ('H', 'V'):
                        done = False
                        for r in range(GRID_SIZE):
                            for c in range(GRID_SIZE):
                                ok, _ = self.can_place(word, r, c, oo)
                                if ok:
                                    self.place(word_id, r, c, oo)
                                    done = placed = True
                                    break
                            if done:
                                break
                        if placed:
                            break
        # Number placements by reading order
        self.placements.sort(key=lambda p: (p.row, p.col))
        for i, p in enumerate(self.placements, start=1):
            p.number = i

    def to_state(self) -> Dict:
        return {
            'grid': self.grid,
            'used_mask': self.used_mask,
            'placements': [
                {
                    'number': p.number,
                    'row': p.row,
                    'col': p.col,
                    'orientation': p.orientation,
                    'length': p.length,
                    'clue': self.entries[p.word_id]['clue'],
                    'answer_original': self.entries[p.word_id]['answer_original'],
                    'answer_norm': self.entries[p.word_id]['answer_norm'],
                }
                for p in self.placements
            ],
        }

# -------------------------
# Flask app
# -------------------------
app = Flask(__name__)
app.secret_key = 'crossword-secret-key'  # for demo only

def new_game():
    cw = Crossword(RAW_ENTRIES)
    cw.generate()
    state = cw.to_state()
    # revealed grid mirrors used_mask but with None for hidden cells
    revealed = [[None if state['used_mask'][r][c] else '#' for c in range(GRID_SIZE)] for r in range(GRID_SIZE)]
    session['state'] = state
    session['revealed'] = revealed


def get_game():
    if 'state' not in session or 'revealed' not in session:
        new_game()
    return session['state'], session['revealed']


def set_revealed(revealed):
    session['revealed'] = revealed


def all_solved(state, revealed) -> bool:
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if state['used_mask'][r][c] and revealed[r][c] in (None, '#'):
                return False
    return True

HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Crucigrama · Una Sola Salud</title>
  <style>
    :root { --bg:#0b1020; --card:#11172a; --ink:#e7eefc; --muted:#a9b2c7; --accent:#58a6ff; --ok:#2ecc71; --bad:#ff6b6b; }
    *{ box-sizing:border-box; font-family: system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial; }
    body{ margin:0; background:linear-gradient(120deg,#0b1020,#131a2e); color:var(--ink); }
    .wrap{ max-width:1200px; margin:24px auto; padding:16px; }
    .grid-card, .side-card { background:var(--card); border:1px solid #1f2842; border-radius:16px; padding:16px; box-shadow:0 10px 30px rgba(0,0,0,.25); }
    .layout{ display:grid; grid-template-columns: 1fr 420px; gap:16px; }
    @media (max-width: 980px){ .layout{ grid-template-columns: 1fr; } }
    h1{ font-size:24px; margin:0 0 12px; letter-spacing:.3px; }
    .toolbar{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
    button, input[type="text"], select{ background:#0f1628; color:var(--ink); border:1px solid #243055; border-radius:12px; padding:10px 12px; font-size:14px; }
    button{ cursor:pointer; }
    button.ok{ border-color:#29583a; }
    button.warn{ border-color:#5a2730; }
    .status{ min-height:24px; margin:6px 0 12px; color:var(--muted); }
    table.cg{ border-collapse: collapse; margin:auto; }
    table.cg td{ width:28px; height:28px; text-align:center; vertical-align:middle; border:1px solid #1e2744; font-weight:700; font-size:15px; }
    table.cg td.block{ background:#0a0f1d; }
    table.cg td.cell{ background:#10182c; }
    .clues{ display:flex; flex-direction:column; gap:8px; max-height:70vh; overflow:auto; }
    .clue{ background:#0e162b; border:1px solid #202b4a; border-radius:12px; padding:10px; }
    .clue h4{ margin:0 0 6px; font-size:14px; color:var(--accent); }
    .clue p{ margin:0; font-size:14px; color:#cbd6ef; }
    .solved{ opacity:.55; }
    .num-badge{ display:inline-block; min-width:26px; text-align:center; background:#172140; border:1px solid #253157; border-radius:8px; padding:2px 6px; margin-right:6px; }
    .pill{ font-size:12px; padding:2px 6px; border:1px solid #2a355e; border-radius:999px; color:#a9b8e9; }
    .row{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Crucigrama · <span class="pill">Una Sola Salud & Epidemiología</span></h1>
    <div class="layout">
      <section class="grid-card">
        <div class="toolbar">
          <input id="answerNumber" type="text" placeholder="Número" style="width:90px" />
          <input id="answerText" type="text" placeholder="Respuesta (ignora acentos/espacios)" style="flex:1" />
          <button id="sendBtn">Enviar</button>
          <button id="revealBtn" class="warn">Mostrar solución</button>
          <button id="resetBtn">Reiniciar</button>
        </div>
        <div class="status" id="status"></div>
        <div id="grid"></div>
      </section>

      <aside class="side-card">
        <div class="row" style="justify-content:space-between;">
          <strong>Pistas</strong>
          <span id="progress" class="pill"></span>
        </div>
        <div class="clues" id="clues"></div>
      </aside>
    </div>
  </div>

  <script>
    const gridEl = document.getElementById('grid');
    const cluesEl = document.getElementById('clues');
    const statusEl = document.getElementById('status');
    const progressEl = document.getElementById('progress');
    const numEl = document.getElementById('answerNumber');
    const ansEl = document.getElementById('answerText');

    function renderGrid(state, revealed){
      const N = state.grid.length;
      let html = '<table class="cg">';
      for(let r=0;r<N;r++){
        html += '<tr>';
        for(let c=0;c<N;c++){
          const used = state.used_mask[r][c];
          if(!used){ html += '<td class="block"></td>'; continue; }
          const ch = revealed[r][c];
          html += `<td class="cell">${ch && ch !== '#' ? ch : ''}</td>`;
        }
        html += '</tr>';
      }
      html += '</table>';
      gridEl.innerHTML = html;
    }

    function renderClues(state, revealed){
      const entries = state.placements;
      cluesEl.innerHTML = '';
      let solvedCount = 0;
      for(const e of entries){
        let isSolved = true;
        if(e.orientation === 'H'){
          for(let i=0;i<e.length;i++) if(!revealed[e.row][e.col+i] || revealed[e.row][e.col+i] === '#') { isSolved = false; break; }
        } else {
          for(let i=0;i<e.length;i++) if(!revealed[e.row+i][e.col] || revealed[e.row+i][e.col] === '#') { isSolved = false; break; }
        }
        if(isSolved) solvedCount++;
        const cls = isSolved ? 'clue solved' : 'clue';
        const len = e.answer_norm.length;
        const pos = `(${String(e.row).padStart(2,'0')},${String(e.col).padStart(2,'0')})`;
        const ori = e.orientation;
        const title = `<span class="num-badge">${String(e.number).padStart(2,'0')}${ori}</span> ${pos} · ${len} letras`;
        const div = document.createElement('div');
        div.className = cls;
        div.innerHTML = `<h4>${title}</h4><p>${e.clue}</p>`;
        div.onclick = () => { numEl.value = e.number; ansEl.focus(); };
        cluesEl.appendChild(div);
      }
      progressEl.textContent = `${solvedCount}/${entries.length} resueltas`;
    }

    async function fetchState(){
      const r = await fetch('/state');
      const data = await r.json();
      renderGrid(data.state, data.revealed);
      renderClues(data.state, data.revealed);
      if(data.solved){ statusEl.textContent = '🎉 ¡Completado!'; }
    }

    async function submitAnswer(){
      const number = numEl.value.trim();
      const guess = ansEl.value.trim();
      if(!number || !guess){ statusEl.textContent = 'Ingresa número y respuesta.'; return; }
      const r = await fetch('/answer', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ number, guess }) });
      const data = await r.json();
      statusEl.textContent = data.message;
      renderGrid(data.state, data.revealed);
      renderClues(data.state, data.revealed);
      if(data.solved){ statusEl.textContent += ' · 🎉 ¡Completado!'; }
      ansEl.value='';
    }

    document.getElementById('sendBtn').onclick = submitAnswer;
    document.getElementById('revealBtn').onclick = async ()=>{
      const r = await fetch('/reveal', { method:'POST' });
      const data = await r.json();
      statusEl.textContent = 'Solución mostrada.';
      renderGrid(data.state, data.revealed);
      renderClues(data.state, data.revealed);
    };
    document.getElementById('resetBtn').onclick = async ()=>{
      await fetch('/reset', { method:'POST' });
      statusEl.textContent = 'Juego reiniciado.';
      fetchState();
    };
    ansEl.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ submitAnswer(); }});

    fetchState();
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    get_game()
    return render_template_string(HTML)

@app.route('/state')
def state():
    state, revealed = get_game()
    return jsonify({ 'state': state, 'revealed': revealed, 'solved': all_solved(state, revealed) })

@app.route('/answer', methods=['POST'])
def answer():
    payload = request.get_json(force=True)
    try:
        number = int(str(payload.get('number', '')).strip())
    except ValueError:
        return jsonify({'ok': False, 'message': 'Número inválido.', **_payload_state()} )
    guess = str(payload.get('guess', '')).strip()

    state, revealed = get_game()
    placement = next((p for p in state['placements'] if p['number'] == number), None)
    if not placement:
        return jsonify({'ok': False, 'message': 'No existe una pista con ese número.', **_payload_state()})

    norm_guess = normalize_answer(guess)
    if norm_guess == placement['answer_norm']:
        # reveal letters
        if placement['orientation'] == 'H':
            for i in range(placement['length']):
                r, c = placement['row'], placement['col'] + i
                revealed[r][c] = state['grid'][r][c]
        else:
            for i in range(placement['length']):
                r, c = placement['row'] + i, placement['col']
                revealed[r][c] = state['grid'][r][c]
        set_revealed(revealed)
        msg = f"✅ Correcto: {placement['answer_original']}"
        ok = True
    else:
        msg = "❌ Incorrecto. Revisa ortografía (se ignoran acentos/espacios)."
        ok = False
    s, rv = get_game()
    return jsonify({ 'ok': ok, 'message': msg, 'state': s, 'revealed': rv, 'solved': all_solved(s, rv) })

@app.route('/reveal', methods=['POST'])
def reveal():
    state, revealed = get_game()
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if state['used_mask'][r][c]:
                revealed[r][c] = state['grid'][r][c]
    set_revealed(revealed)
    s, rv = get_game()
    return jsonify({ 'state': s, 'revealed': rv, 'solved': True })

@app.route('/reset', methods=['POST'])
def reset():
    new_game()
    s, rv = get_game()
    return jsonify({ 'state': s, 'revealed': rv, 'solved': False })


def _payload_state():
    s, rv = get_game()
    return { 'state': s, 'revealed': rv, 'solved': all_solved(s, rv) }

if __name__ == '__main__':
    # Dev server
    app.run(debug=True)
