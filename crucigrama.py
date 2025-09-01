#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Crossword (Flask single-file app)
====================================
- Run:  python crucigrama.py
- Open: http://127.0.0.1:5000
- UI in Spanish; code/comments in English.
- Accepts answers ignoring accents, spaces and case.
- No external assets; everything is embedded.
"""

import unicodedata
from typing import List, Tuple, Dict, Optional
from flask import Flask, render_template_string, request, session, jsonify

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
        # Number by reading order
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
app.secret_key = 'crossword-secret-key'  # demo only

def new_game():
    cw = Crossword(RAW_ENTRIES)
    cw.generate()
    state = cw.to_state()
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
    # Check only the cells that belong to placements
    for p in state['placements']:
        if p['orientation'] == 'H':
            for i in range(p['length']):
                r, c = p['row'], p['col'] + i
                if not revealed[r][c] or revealed[r][c] == '#':
                    return False
        else:
            for i in range(p['length']):
                r, c = p['row'] + i, p['col']
                if not revealed[r][c] or revealed[r][c] == '#':
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
      :root{
        --bg1:#fff5f9; --bg2:#ffeaf3;
        --card:#ffffff; --ink:#5a4b57; --muted:#8b6f7a;
        --accent:#e85d8e; --ok:#2ecc71; --bad:#ff6b88;
        --border:#f3c5d5; --border-strong:#f0a7bd;
        --chip:#ffe3ee; --chip-text:#a74b69;
        --block:#fdeaf2; --cell:#ffffff;
        --grid:#f4b6c8;
        --button-bg:#ffffff; --button-border:#f0a7bd; --button-hover:#fff0f6;
        --shadow: 0 12px 28px rgba(232,93,142,0.12);
        --radius:18px;
      }
      *{box-sizing:border-box;font-family: system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial;}
      body{margin:0;background:linear-gradient(120deg,var(--bg1),var(--bg2));color:var(--ink);}
      .wrap{max-width:1180px;margin:28px auto;padding:16px;}
      .layout{display:grid;grid-template-columns:1fr 420px;gap:18px;}
      @media (max-width: 980px){.layout{grid-template-columns:1fr;}}

      h1{font-size:26px;margin:0 0 14px;letter-spacing:.2px;color:#7a3654;}
      .grid-card,.side-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow);}
      .toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
      input[type="text"], button{
        background:var(--button-bg);color:var(--ink);
        border:1.5px solid var(--button-border);
        border-radius:14px;padding:10px 12px;font-size:14px;outline:none;
        transition:background .15s, box-shadow .15s, transform .02s ease-in-out;
      }
      input[type="text"]:focus, button:focus{box-shadow:0 0 0 3px #ffd3e3;}
      button{cursor:pointer}
      button:hover{background:var(--button-hover)}
      button.warn{border-color:#f08aa8}
      .status{min-height:24px;margin:6px 0 12px;color:var(--muted)}

      /* Contenedor del crucigrama */
      .grid-scroll{ overflow: visible; width: 100%; }
      table.cg{ border-collapse:collapse; margin:auto; table-layout:fixed; border-spacing:0; }
      table.cg td{
        width:28px; height:28px; text-align:center; vertical-align:middle;
        border:1px solid var(--grid); font-weight:700; font-size:15px; border-radius:6px;
        white-space:nowrap;
      }
      table.cg td.block{ background:var(--block) }
      table.cg td.cell{ background:var(--cell) }

      /* SOLO móvil: no escalar, permitir scroll horizontal, y casillas ~doble */
      @media (max-width: 768px){
        .grid-scroll{
          overflow-x:auto; overflow-y:hidden;
          -webkit-overflow-scrolling:touch;
          padding-bottom:8px;
        }
        .grid-scroll table.cg{
          display:inline-block;      /* asegura que la tabla mantenga su ancho natural */
          margin:0;                  /* alinea a la izquierda para empezar el scroll desde el inicio */
        }
        table.cg td{
          width:56px; height:56px;   /* ~doble de 28px */
          font-size:22px;            /* más legible */
          border-radius:8px;
        }
        .wrap{ padding:12px; }
      }

      .clues{display:flex;flex-direction:column;gap:10px;max-height:70vh;overflow:auto}
      .clue{background:#fff7fb;border:1px solid var(--border);border-radius:16px;padding:10px}
      .clue h4{margin:0 0 6px;font-size:14px;color:var(--accent)}
      .clue p{margin:0;font-size:14px;color:#6d5965}
      .solved{opacity:.55}
      .num-badge{
        display:inline-block;min-width:28px;text-align:center;
        background:var(--chip);border:1px solid var(--border-strong);
        color:var(--chip-text);border-radius:10px;padding:3px 8px;margin-right:6px;font-weight:700
      }
      .pill{font-size:12px;padding:3px 8px;border:1px solid var(--border-strong);border-radius:999px;background:var(--chip);color:var(--chip-text)}
      .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
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
          <strong style="color:#7a3654;">Pistas</strong>
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
    return jsonify({'state': state, 'revealed': revealed, 'solved': all_solved(state, revealed)})

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
    return jsonify({'ok': ok, 'message': msg, 'state': s, 'revealed': rv, 'solved': all_solved(s, rv)})

@app.route('/reveal', methods=['POST'])
def reveal():
    state, revealed = get_game()
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if state['used_mask'][r][c]:
                revealed[r][c] = state['grid'][r][c]
    set_revealed(revealed)
    s, rv = get_game()
    return jsonify({'state': s, 'revealed': rv, 'solved': True})

@app.route('/reset', methods=['POST'])
def reset():
    new_game()
    s, rv = get_game()
    return jsonify({'state': s, 'revealed': rv, 'solved': False})

def _payload_state():
    s, rv = get_game()
    return {'state': s, 'revealed': rv, 'solved': all_solved(s, rv)}

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
