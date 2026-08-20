"""Panel de control web en vivo (SSE + HTTP estándar, sin dependencias).

Muestra en tiempo real el bucle autónomo: rondas de plan, pasos, evaluaciones,
reintentos, estancamientos superados, divisiones fractales y verificación del
objetivo. Permite lanzar objetivos propios o la misión demo.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .config import Config
from .goals import DEMO_GOAL, build_demo_step_verifiers, forensic_report_goal_verifier, prepare_demo_workspace
from .loop import AgentLoop

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A²S — Consola de misión</title>
<style>
:root{--bg:#0b0e14;--panel:#12161f;--line:#1f2633;--fg:#d7e0ea;--dim:#7d8aa0;
--ok:#3ddc84;--bad:#ff5c5c;--warn:#ffb454;--acc:#4da3ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;
gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;letter-spacing:2px}
h1 b{color:var(--acc)}.status{font-size:12px;color:var(--dim)}
.badge{padding:2px 10px;border-radius:10px;font-size:12px;border:1px solid var(--line)}
.badge.run{color:var(--warn)}.badge.ok{color:var(--ok)}.badge.partial{color:var(--bad)}
main{display:grid;grid-template-columns:320px 1fr;gap:0;min-height:calc(100vh - 53px)}
aside{border-right:1px solid var(--line);padding:16px;background:var(--panel)}
aside h2{font-size:12px;letter-spacing:1px;color:var(--dim);margin:0 0 8px}
#goal{width:100%;background:#0b0e14;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:8px;min-height:70px;font:inherit;resize:vertical}
button{display:block;width:100%;margin-top:8px;padding:9px;border-radius:6px;border:1px
solid var(--line);background:#182031;color:var(--fg);font:inherit;cursor:pointer}
button:hover{border-color:var(--acc)}button:disabled{opacity:.4;cursor:default}
.stats{margin-top:16px}.stat{display:flex;justify-content:space-between;padding:5px 0;
border-bottom:1px dashed var(--line);font-size:12px}
.stat b{color:var(--acc)}
#feed{list-style:none;margin:0;padding:16px;max-height:calc(100vh - 53px);
overflow-y:auto;display:flex;flex-direction:column;gap:6px}
#feed li{border:1px solid var(--line);border-left:3px solid var(--dim);border-radius:6px;
padding:7px 10px;background:var(--panel);font-size:12.5px;animation:in .25s}
@keyframes in{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
#feed li.step_start{border-left-color:var(--acc)}
#feed li.evaluation{border-left-color:var(--dim)}
#feed li.evaluation.verdict_success{border-left-color:var(--ok)}
#feed li.evaluation.verdict_failed{border-left-color:var(--warn)}
#feed li.evaluation.verdict_blocked{border-left-color:var(--bad)}
#feed li.retry{border-left-color:var(--warn)}
#feed li.split{border-left-color:#c678dd}
#feed li.stagnation{border-left-color:var(--bad)}
#feed li.goal_check{border-left-color:var(--ok)}
#feed li.run_end{border-left-color:var(--ok);background:#10231a}
#feed li.replan{border-left-color:#c678dd}
#feed .t{color:var(--dim);font-size:11px}
</style></head><body>
<header><h1>A²<b>S</b></h1><span class="status">agente autónomo · loops auto-optimizados</span>
<div style="flex:1"></div><span id="badge" class="badge">IDLE</span></header>
<main><aside>
  <h2>OBJETIVO DE LA MISIÓN</h2>
  <textarea id="goal">Produce un informe forense completo del workspace en 'informe_forense.md' con inventario, hashes SHA-256, cadena de custodia y conclusiones (datos reales).</textarea>
  <button id="start">▶ Lanzar misión</button>
  <button id="demo" style="margin-top:4px">▶ Misión demo (con obstáculo)</button>
  <div class="stats">
    <h2>TELEMETRÍA</h2>
    <div class="stat"><span>Estado</span><b id="s_state">—</b></div>
    <div class="stat"><span>Iteraciones</span><b id="s_iter">0</b></div>
    <div class="stat"><span>Rondas de plan</span><b id="s_round">0</b></div>
    <div class="stat"><span>Estancamientos superados</span><b id="s_stag">0</b></div>
    <div class="stat"><span>Divisiones fractales</span><b id="s_split">0</b></div>
    <div class="stat"><span>Proveedor</span><b id="s_prov">—</b></div>
  </div>
</aside>
<ul id="feed"><li class="t">Esperando misión… (lanza la demo o escribe tu objetivo)</li></ul>
</main>
<script>
const feed=document.getElementById('feed');
const els={state:document.getElementById('s_state'),iter:document.getElementById('s_iter'),
round:document.getElementById('s_round'),stag:document.getElementById('s_stag'),
split:document.getElementById('s_split'),prov:document.getElementById('s_prov'),
badge:document.getElementById('badge')};
let n=0, running=false;
function add(e){
  if(!e||!e.event) return;
  if(n===0) feed.innerHTML='';
  n++;
  const li=document.createElement('li');
  let cls=e.event, extra='';
  if(e.event==='evaluation'){cls+=' verdict_'+e.verdict;extra=` · ${e.goal} · intento ${e.attempt} · ${e.reason||''}`;}
  else if(e.event==='step_start'){extra=` · ${e.goal} (${e.approach||''})`;}
  else if(e.event==='step_done'){extra=` · estado: ${e.status}`;}
  else if(e.event==='retry'){extra=` · acción: ${e.action} (siguiente intento ${e.attempt})`;}
  else if(e.event==='split'){extra=` · ${e.goal} → [${(e.children||[]).join(' | ')}]`;}
  else if(e.event==='failure_handled'){extra=` · ${e.countermeasure||''}`;}
  else if(e.event==='replan'){extra=` · ${e.kind||''} · [${(e.steps||[]).join(' → ')}]`;}
  else if(e.event==='goal_check'){extra=` · ${e.achieved?'CUMPLIDO':'todavía no'} — ${e.reason||''}`;}
  else if(e.event==='run_start'){extra=` · ${e.goal} · proveedor ${e.provider}`;}
  else if(e.event==='run_end'){extra=` · ${e.note||''}`;}
  li.className=cls;
  li.innerHTML=`<div class="t">${e.at} · ${e.event}</div><div>${escapeHtml(extra||'-')}</div>`;
  feed.appendChild(li); while(feed.children.length>300) feed.removeChild(feed.firstChild);
  feed.scrollTop=feed.scrollHeight;
  if(e.event==='run_start'){els.state.textContent='EJECUTANDO';els.badge.className='badge run';els.badge.textContent='RUNNING';running=true;}
  if(e.event==='evaluation'&&e.verdict==='success'&&e.score!=null){}
  if(e.event==='split'){els.split.textContent=++els.split.dataset.n||1;els.split.dataset.n=els.split.textContent;}
  if(e.event==='failure_handled'&&/estancamiento/.test(e.countermeasure||'')){els.stag.textContent=++els.stag.dataset.n||1;els.stag.dataset.n=els.stag.textContent;}
  if(e.event==='plan_created'||e.event==='replan'){els.round.textContent=(parseInt(els.round.textContent)||0)+1;}
  if(e.event==='run_start'){els.prov.textContent=e.provider||'—';els.iter.textContent='0';}
  if(e.event==='run_end'){els.badge.className=e.success?'badge ok':'badge partial';
    els.badge.textContent=e.success?'OBJETIVO CUMPLIDO':'PARCIAL (reanudable)';
    els.state.textContent=e.success?'CUMPLIDO':'CIERRE';running=false;
    document.getElementById('start').disabled=false;
    document.getElementById('demo').disabled=false;}
  if(e.event==='evaluation'){els.iter.textContent=(parseInt(els.iter.textContent)||0)+1;}
}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function launch(demo){
  if(running) return;
  const goal=demo?null:document.getElementById('goal').value.trim();
  if(!demo&&!goal){add({event:'goal_check',at:new Date().toISOString(),reason:'escribe un objetivo',achieved:false});return;}
  document.getElementById('start').disabled=true;document.getElementById('demo').disabled=true;
  const r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({goal:goal||'',demo:!!demo})});
  if(!r.ok){add({event:'goal_check',at:new Date().toISOString(),reason:'no se pudo iniciar',achieved:false});}
}
document.getElementById('start').onclick=()=>launch(false);
document.getElementById('demo').onclick=()=>launch(true);
const es=new EventSource('/api/events');
es.onmessage=m=>{try{add(JSON.parse(m.data));}catch(e){}};
fetch('/api/state').then(r=>r.json()).then(s=>{
  (s.events||[]).forEach(add);
  els.iter.textContent=s.iterations||0;
  if(s.running){els.badge.className='badge run';els.badge.textContent='RUNNING';els.state.textContent='EJECUTANDO';running=true;
    document.getElementById('start').disabled=true;document.getElementById('demo').disabled=true;}
  if(s.report&&s.report.success){els.badge.className='badge ok';els.badge.textContent='OBJETIVO CUMPLIDO';els.state.textContent='CUMPLIDO';}
});
</script></body></html>"""


class EventHub:
    """Pub/sub de eventos para SSE."""

    def __init__(self, history: int = 400):
        self.subs: set[queue.Queue] = set()
        self.history: list[dict[str, Any]] = []
        self.history_max = history
        self._lock = threading.Lock()

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.history.append(event)
            if len(self.history) > self.history_max:
                self.history = self.history[-self.history_max:]
            for q in list(self.subs):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self.subs.discard(q)


class MissionManager:
    """Ejecuta misiones en hilos de fondo y publica eventos."""

    def __init__(self, hub: EventHub, workspace: str):
        self.hub = hub
        self.workspace = workspace
        self.running = False
        self.current: Optional[AgentLoop] = None
        self.report = None
        self.iterations = 0
        self._lock = threading.Lock()

    def start(self, goal: Optional[str], demo: bool) -> str:
        with self._lock:
            if self.running:
                return "ya hay una misión en curso"
            self.running = True
            self.report = None
        config = Config(workspace=self.workspace, max_wall_seconds=600)

        def worker() -> None:
            if not demo and not goal:
                self.hub.publish({"event": "run_end", "at": "", "success": False,
                                  "note": "sin objetivo que ejecutar"})
                with self._lock:
                    self.running = False
                return
            goal_verifier = None
            step_verifiers = None
            if demo or "informe forense" in (goal or "").lower():
                goal = DEMO_GOAL if demo else goal
                loop = AgentLoop.create(goal, config=config,
                                        goal_verifier=forensic_report_goal_verifier)
                prepare_demo_workspace(loop.memory)
                loop.step_verifiers = build_demo_step_verifiers(loop.memory)
            else:
                loop = AgentLoop.create(goal, config=config)
            loop.on_event = self.hub.publish
            with self._lock:
                self.current = loop
            try:
                self.report = loop.run(goal)
            except Exception as exc:  # noqa: BLE001 — el panel informa, no muere
                self.hub.publish({"event": "run_end", "at": "", "success": False,
                                  "note": f"excepción en la misión: {exc}"})
                self.report = None
            finally:
                with self._lock:
                    self.running = False
                    self.iterations = getattr(self.report, "iterations", 0) if self.report else 0

        threading.Thread(target=worker, daemon=True).start()
        return "misión iniciada"


class DashboardServer:
    def __init__(self, port: int = 8000, workspace: str = "workspace",
                 auto_demo: bool = True, public: bool = False):
        self.port = port
        self.workspace = workspace
        self.public = public
        self.host = "0.0.0.0" if public else "127.0.0.1"
        self.hub = EventHub()
        self.missions = MissionManager(self.hub, workspace)
        self.auto_demo = auto_demo

    def serve_forever(self) -> None:
        server = ThreadingHTTPServer((self.host, self.port), self._handler())
        print(f"[A²S] Panel de control: http://{self.host}:{self.port}/")
        if self.public:
            print("[A²S] ⚠ MODO PÚBLICO: cualquier equipo que alcance este puerto "
                  "puede lanzar misiones que ejecutan código en este host. "
                  "Usa solo en redes de confianza.")
        else:
            print("[A²S] (solo localhost; usa --public para exponerlo en la red)")
        if self.auto_demo:
            self.missions.start(None, demo=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # silencio de acceso
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/":
                    body = PAGE.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    q = outer.hub.subscribe()
                    try:
                        while True:
                            try:
                                event = q.get(timeout=15)
                                data = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                                self.wfile.write(data.encode())
                                self.wfile.flush()
                            except queue.Empty:
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        outer.hub.unsubscribe(q)
                elif self.path == "/api/state":
                    with outer.missions._lock:
                        state = {"running": outer.missions.running,
                                 "iterations": outer.missions.iterations,
                                 "report": (outer.missions.report.to_dict()
                                            if outer.missions.report else None),
                                 "events": list(outer.hub.history)}
                    self._json(state)
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path == "/api/start":
                    length = int(self.headers.get("Content-Length", 0))
                    try:
                        payload = json.loads(self.rfile.read(length) or b"{}")
                    except json.JSONDecodeError:
                        payload = {}
                    msg = outer.missions.start(payload.get("goal"), bool(payload.get("demo")))
                    self._json({"status": msg})
                else:
                    self.send_error(404)

        return Handler
