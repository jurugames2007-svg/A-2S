"""Interfaz de línea de comandos de A²S."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
from typing import Optional

from . import __version__
from ._platform import force_utf8
from .aegis_protocol import analyze_request
from .config import Config

force_utf8()
from .directiva import print_capability_map, scope_note
from .goals import (DEMO_GOAL, build_demo_step_verifiers,
                    forensic_report_goal_verifier, prepare_demo_workspace)
from .loop import AgentLoop, run_goal
from .notify import notify
from .report import render_text, save_report


def _swarm_worker(task: tuple) -> tuple[str, bool]:
    """Worker de proceso: réplica autónoma con workspace y memoria propios."""
    workspace, goal, index = task
    cfg = Config(workspace=workspace, quiet=True, max_wall_seconds=600)
    try:
        report = run_goal(goal, config=cfg)
        out_dir = os.path.join(workspace, ".a2s", "swarm")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"worker_{index}.json"), "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, ensure_ascii=False)
        return goal, report.success
    except Exception as exc:  # noqa: BLE001 — el padre agrega y registra
        with open(os.path.join(workspace, ".a2s", "swarm", f"worker_{index}.error"),
                  "w", encoding="utf-8") as fh:
            fh.write(str(exc))
        return goal, False


def _config_from_args(args: argparse.Namespace) -> Config:
    cfg = Config(
        workspace=args.workspace,
        provider=args.provider,
        max_iterations=args.max_iterations,
        max_rounds=args.max_rounds,
        max_wall_seconds=args.max_time,
        allow_network=not args.no_network,
        allow_shell=not args.no_shell,
        shell_unsafe=args.unsafe,
        quiet=args.quiet,
    )
    if getattr(args, "speculative", None):
        cfg.speculative_candidates = args.speculative
    if getattr(args, "max_depth", None) is not None:
        cfg.max_fractal_depth = args.max_depth
    if getattr(args, "allow_host", None):
        cfg.network_allowlist = list(args.allow_host)
    if getattr(args, "no_sandbox", False):
        cfg.sandbox = False
    if getattr(args, "evolve", None):
        cfg.evolve_generations = args.evolve
    if getattr(args, "pool_config", None):
        cfg.pool_config = args.pool_config
    if getattr(args, "pool_strategy", None):
        cfg.pool_strategy = args.pool_strategy
    if getattr(args, "ram", False):
        cfg.workspace = ram_workspace()
    return cfg


def ram_workspace() -> str:
    """Workspace volátil en RAM (/dev/shm) si está disponible."""
    import tempfile
    shm = "/dev/shm"
    if os.path.isdir(shm) and os.access(shm, os.W_OK):
        path = os.path.join(shm, f"a2s-{os.getpid()}")
        os.makedirs(path, exist_ok=True)
        print(f"[A²S] ⚡ workspace volátil en RAM: {path} (se pierde al apagar)")
        return path
    print("[A²S] /dev/shm no disponible: usando directorio temporal")
    return tempfile.mkdtemp(prefix="a2s-")


def cmd_protocol(args: argparse.Namespace) -> int:
    """Inspecciona la selección adaptativa antes de ejecutar una misión."""
    decision = analyze_request(args.request)
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print("Protocolo Adaptativo Aegis")
    print(f"Necesidad: {', '.join(decision.need_types)}")
    print(f"Fecha de referencia: {decision.reference_at}")
    print("Capacidades activadas:")
    for capability in decision.capabilities:
        print(f"  ✅ {capability.label} — {capability.purpose}")
    print("Criterios de aceptación:")
    for criterion in decision.acceptance_criteria:
        print(f"  - {criterion}")
    if decision.clarification_questions:
        print("Preguntas aclaratorias:")
        for question in decision.clarification_questions:
            print(f"  - {question}")
    if decision.assumptions:
        print("Supuestos explícitos:")
        for assumption in decision.assumptions:
            print(f"  - {assumption}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    if args.resume:
        from .ledger import Ledger
        from .kernel import Kernel
        led = Ledger(os.path.join(os.path.abspath(config.workspace), ".a2s"))
        ok, msg, n = led.verify()
        kernel = Kernel.open(config.workspace)
        restored = kernel.resume_all()
        print(f"[A²S] Reanudando PCB: {len(restored)} trabajo(s) → ready · "
              f"ledger {msg} ({n} entradas) · {kernel.applied} mejoras.\n")
    print(scope_note())
    print()
    reports = []
    goals = [g.strip() for g in args.goal.split(";") if g.strip()]
    if args.parallel and len(goals) > 1:
        # Despliegue fractal: sub-agentes en paralelo, un informe por sub-objetivo.
        loop = AgentLoop.create(goals[0], config=config)
        subreports = loop.run_fractal(goals)
        reports.extend(subreports.values())
        for goal, rep in subreports.items():
            print(render_text(rep))
            if args.report:
                save_report(rep, os.path.join(config.workspace, args.report))
    else:
        for goal in goals:
            report = run_goal(goal, config=config)
            reports.append(report)
            print()
            print(render_text(report))
            if args.report:
                path = save_report(report, os.path.join(config.workspace, args.report))
                print(f"\nInforme guardado en: {path}")
    if getattr(args, "notify", None):
        exitos = sum(r.success for r in reports)
        notify(args.notify,
               f"A²S: {exitos}/{len(reports)} objetivo(s) verificado(s)",
               "; ".join(f"{'ok' if r.success else 'fallo'}: {r.goal[:60]}"
                         for r in reports),
               nivel="info" if exitos == len(reports) else "warn",
               extra={"exit_code": 0 if exitos == len(reports) else 2})
    return 0 if all(r.success for r in reports) else 2


def cmd_demo(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    print(scope_note())
    print("\n▶ MISIÓN DEMO — informe forense autónomo (diseñada para demostrar")
    print("  la superación de estancamiento: el primer enfoque falla a propósito)\n")
    loop = AgentLoop.create(DEMO_GOAL, config=config,
                            goal_verifier=forensic_report_goal_verifier)
    prepare_demo_workspace(loop.memory)
    loop.step_verifiers = build_demo_step_verifiers(loop.memory)
    report = loop.run(DEMO_GOAL)
    print()
    print(render_text(report))
    if args.report:
        path = save_report(report, os.path.join(config.workspace, args.report))
        print(f"\nInforme guardado en: {path}")
    informe = os.path.join(config.workspace, "informe_forense.md")
    if os.path.exists(informe):
        print(f"\nArtefacto principal de la misión: {informe}")
    return 0 if report.success else 2


def cmd_supervise(args: argparse.Namespace) -> int:
    """Auto-existencia: el agente se relanza hasta cumplir el objetivo
    (la memoria evolutiva y la red de gobernanza persisten entre intentos)."""
    config = _config_from_args(args)
    print(scope_note())
    print()
    goal = args.goal
    for attempt in range(1, args.attempts + 1):
        print(f"[A²S] ⚡ Supervisión activa — intento {attempt}/{args.attempts}")
        report = run_goal(goal, config=config)
        if report.success:
            print()
            print(render_text(report))
            print(f"\n[A²S] ✔ objetivo cumplido en el intento {attempt}")
            return 0
        print(f"[A²S] ◐ intento {attempt} sin verificación completa; "
              f"reanudando sobre estado persistido…")
        if attempt < args.attempts:
            time.sleep(args.sleep)
    print(f"[A²S] ⚠ {args.attempts} intentos supervisados sin verificación completa; "
          "el estado queda persistido (usa --attempts para ampliar)")
    return 2


def cmd_swarm(args: argparse.Namespace) -> int:
    """Réplica en procesos: un worker autónomo por objetivo, en paralelo."""
    from concurrent.futures import ProcessPoolExecutor
    goals = [g.strip() for g in args.goal.split(";") if g.strip()]
    base = os.path.abspath(args.workspace)
    tasks = [(os.path.join(base, "swarm", f"n{i}"), g, i)
             for i, g in enumerate(goals)]
    workers = max(1, min(args.workers, len(tasks)))
    print(f"[A²S] ⑂ enjambre: {len(tasks)} réplicas autónomas, {workers} proceso(s) paralelo(s)")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_swarm_worker, tasks))
    ok = 0
    for goal, success in results:
        ok += int(success)
        print(f"   {'✔' if success else '◐'} {goal[:80]}")
    print(f"[A²S] enjambre completado: {ok}/{len(results)} objetivos verificados "
          f"(informes en {os.path.join(base, 'swarm')}/)")
    return 0 if ok == len(results) else 2


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import DashboardServer
    from .omniroute import OmniRouteWatchdog

    # También cubre ``python -m a2s dashboard``: usa el bundle dist incluido y
    # evita por completo la ruta src/tsx que puede bloquearse.
    gateway_watchdog = OmniRouteWatchdog()
    gateway = gateway_watchdog.ensure_now()
    if gateway.get("usable"):
        print(f"[A²S] ◉ OmniRoute portable: {gateway.get('url')} "
              f"({gateway.get('mode', gateway.get('state', 'conectado'))})")
    elif gateway.get("state") == "disabled":
        print("[A²S] OmniRoute desactivado; Aegis continúa con el núcleo local")
    else:
        print(f"[A²S] ◐ OmniRoute no disponible aún: "
              f"{gateway.get('detail', gateway.get('state', 'desconocido'))}; "
              "Aegis continúa localmente y reintentará")
    gateway_watchdog.start()

    server = DashboardServer(port=args.port, workspace=args.workspace,
                             auto_demo=args.autodemo, public=args.public,
                             require_auth=args.auth)
    # Crecimiento autónomo: al abrirlo, se pone a estudiar (off con
    # A2S_AUTO_LEARN=0; no afecta a tests que construyen DashboardServer directo).
    from .growth import AutoLearner, autolearn_enabled
    if autolearn_enabled():
        server.growth = AutoLearner(server.workspace, hub=server.hub,
                                    interval_seconds=args.learn_interval)
        server.growth.start()
        print("[A²S] 🌱 crecimiento autónomo activo (estudio continuo de "
              f"repos públicos cada {args.learn_interval}s; A2S_AUTO_LEARN=0 "
              "para apagarlo)")
    try:
        server.serve_forever()
    finally:
        gateway_watchdog.stop()
        if server.growth:
            server.growth.stop()
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    from .auth import workspace_token_manager
    tm = workspace_token_manager(args.workspace)
    token = tm.issue(scope="dashboard", hours=args.hours)
    print(token)
    print(f"(válido {args.hours}h para el dashboard de {os.path.abspath(args.workspace)})")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .ledger import Ledger
    from .signing import Signer, report_payload
    ws = os.path.abspath(args.workspace)
    problems: list[str] = []
    ledger = Ledger(os.path.join(ws, ".a2s"))
    ok, msg, n = ledger.verify()
    print(f"Ledger:        {msg} ({n} entradas)")
    if not ok:
        problems.append(msg)
    signer = Signer(ws)
    # Verificar firmas de artefactos registradas en el ledger.
    signed = [e for e in ledger.entries()
              if e.get("event") == "artifact_signed"]
    checked = 0
    for e in signed:
        p = e["payload"]
        path = os.path.join(ws, p.get("path", ""))
        if not os.path.isfile(path):
            problems.append(f"artefacto desaparecido: {p.get('path')}")
            continue
        if not signer.verify_file(path, p.get("hmac", "")):
            problems.append(f"FIRMA INCOHERENTE: {p.get('path')}")
        else:
            checked += 1
    print(f"Artefactos:    {checked} con firma HMAC verificada")
    # Verificar informe de ejecución si existe.
    rep_json = os.path.join(ws, "informe_a2s.md.json")
    if os.path.isfile(rep_json):
        with open(rep_json, encoding="utf-8") as fh:
            rep = json.load(fh)
        sig = rep.get("signature", "")
        if not sig:
            problems.append("informe de ejecución sin firma")
        elif not signer.verify(report_payload(rep), sig):
            problems.append("informe de ejecución: firma inválida")
        else:
            print("Informe:       firma HMAC válida")
    else:
        print("Informe:       (no existe informe_a2s.md.json)")
    if problems:
        print("\nVERIFICACIÓN CON PROBLEMAS:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n✔ verificación completa: cadena íntegra y firmas coherentes")
    return 0


def cmd_evolve(args: argparse.Namespace) -> int:
    from .memory import MemoryHub
    from .neuroevolve import evolve_from_memory
    ws = os.path.abspath(args.workspace)
    memory = MemoryHub(ws, "(evolución)")
    if len(memory.episodes) < 8:
        print(f"[A²S] buffer insuficiente: {len(memory.episodes)} episodios "
              "(mínimo 8). Ejecuta misiones primero.")
        return 1
    try:
        fitness = evolve_from_memory(memory, generations=args.generations,
                                     target=os.path.join(memory.dir, "governance.json"))
    except ValueError as exc:
        print(f"[A²S] {exc}")
        return 1
    print(f"[A²S] neuroevolución completada: fitness={fitness:.3f} "
          f"({args.generations} generaciones, {len(memory.episodes)} episodios)")
    print("[A²S] pesos exportados a .a2s/governance.json")
    return 0


def cmd_build_live(args: argparse.Namespace) -> int:
    import shutil
    import tempfile
    import zipapp
    out = args.output or "dist/a2s.pyz"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    import a2s as pkg
    source = os.path.dirname(pkg.__file__)
    # Staging: __main__.py + paquete a2s, para que el zip mantenga el contexto
    # de paquete (los imports relativos internos siguen funcionando).
    with tempfile.TemporaryDirectory() as stage:
        shutil.copytree(
            source, os.path.join(stage, "a2s"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        with open(os.path.join(stage, "__main__.py"), "w", encoding="utf-8") as fh:
            fh.write("import sys\nfrom a2s.cli import main\nsys.exit(main())\n")
        zipapp.create_archive(stage, target=out, interpreter="/usr/bin/env python3")
    size = os.path.getsize(out)
    print(f"[A²S] LiveCD (zipapp) creado: {out} ({size/1024:.0f} KB)")
    print(f"       Uso: python3 {out} run 'tu objetivo' --ram")
    print("       Requiere python3 en el host destino (sin instalación de A²S).")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    import json
    from .models import RunReport
    with open(args.path, encoding="utf-8") as fh:
        data = json.load(fh)
    report = RunReport(**{k: v for k, v in data.items() if k in RunReport.__dataclass_fields__})
    print(render_text(report))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import socket
    import sys as _sys
    from .ledger import Ledger
    from .plugin_loader import PluginLoader
    from .sandbox import Sandbox
    print("A²S — diagnóstico del entorno")
    print(f"  Python:        {_sys.version.split()[0]}")
    print(f"  A²S:           {__version__}")
    ws = os.path.abspath(args.workspace)
    print(f"  Workspace:     {ws} (existe: {os.path.isdir(ws)})")
    sandbox = Sandbox(ws)
    print(f"  Sandbox:       nivel {sandbox.level} ({sandbox.level_name}) "
          f"— nsjail: {sandbox._nsjail or 'no'}, bwrap: {sandbox._bwrap or 'no'}")
    if os.name == "nt":
        from ._platform import find_posix_shell
        shell = find_posix_shell()
        nota_shell = shell or ("NINGUNO funcional — instala Git-Bash, MSYS2 o "
                               "WSL (la mini-shell quedará deshabilitada)")
        print(f"  Shell POSIX:   {nota_shell}")
    loader = PluginLoader(ws)
    loader.discover()
    plugins = loader.describe()
    print(f"  Plugins:       {len(plugins)} disponibles: "
          f"{', '.join(p['name'] for p in plugins) or 'ninguno'}")
    ledger = Ledger(os.path.join(ws, ".a2s"))
    ok, msg, n = ledger.verify()
    print(f"  Ledger:        {msg} ({n} entradas)")
    if os.path.exists(os.path.join(ws, ".a2s", "secret")):
        print("  Firma HMAC:    secreto del workspace presente (a2s verify)")
    print("  Motor auto:    pool SORL (OmniRoute primero; fallback heurístico siempre disponible)")
    if os.environ.get("OPENAI_API_KEY"):
        base = os.environ.get("A2S_LLM_BASE_URL", "https://api.openai.com/v1")
        print(f"  OpenAI extra:  clave detectada · base_url: {base}")
    from .provider_pool import discover_endpoints_from_env
    pool_eps = discover_endpoints_from_env()
    if pool_eps:
        print(f"  Pool SORL:     {len(pool_eps)} endpoint(s) legítimo(s) detectado(s): "
              f"{', '.join(e.name for e in pool_eps)} (selección automática)")
    else:
        print("  Pool SORL:     sin gateway ni claves detectados → fallback heurístico")
    from .provider_pool import OMNIROUTE_DETECTED
    if OMNIROUTE_DETECTED:
        activo = any(e.name == "omniroute" for e in pool_eps)
        if not activo:
            print("  OmniRoute:     detectado en "
                  f"{OMNIROUTE_DETECTED.get('base_url')} pero pide clave: cópiala "
                  "de su Dashboard → Endpoints y declara A2S_OMNIROUTE_KEY")
        else:
            n = len(OMNIROUTE_DETECTED.get("models", []))
            print(f"  OmniRoute:     ✔ conectado en {OMNIROUTE_DETECTED.get('base_url')} "
                  f"({n} modelos visibles; el modelo 'auto' enruta solo, cero-config)")
    elif os.environ.get("A2S_OMNIROUTE_MANAGED") == "1":
        omni = next((e for e in pool_eps if e.name == "omniroute"), None)
        if omni is not None:
            print(f"  OmniRoute:     ✔ incluido por npm y conectado en {omni.base_url} "
                  "(modelo 'auto'; sin selección manual)")
    try:
        socket.create_connection(("duckduckgo.com", 443), timeout=5).close()
        print("  Red externa:   disponible (búsqueda web y fetch habilitados)")
    except OSError:
        print("  Red externa:   NO disponible (las herramientas de red fallarán y el loop las reparametrizará)")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Auto-actualización en el sitio: fetch + fast-forward, sin volver a
    descargar el repositorio. Apelativo admitido: ``a2s update tkm``."""
    from .updater import update, watch
    if getattr(args, "watch", None):
        return watch(root=getattr(args, "root", None), alias=args.alias,
                     interval=args.watch, branch=args.branch, force=args.force)
    return update(root=getattr(args, "root", None), alias=args.alias,
                  check_only=args.check, branch=args.branch,
                  force=args.force)


def cmd_grow(args: argparse.Namespace) -> int:
    """Crecimiento autónomo en primer plano: A²S estudia repos públicos y
    destila fichas de conocimiento (solo lectura; nunca ejecuta lo estudiado)."""
    from .growth import AutoLearner
    learner = AutoLearner(args.workspace,
                          interval_seconds=args.interval,
                          repos_per_cycle=args.repos)
    if args.forever:
        print(f"[A²S] 🌱 creciendo sin parar (ciclos cada {args.interval}s; "
              "Ctrl+C para parar)")
        learner.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            learner.stop()
            print(f"\n[A²S] crecimiento detenido tras {learner.cycles} ciclo(s)")
            return 0
    ciclos = args.cycles if args.cycles > 0 else 1
    for _ in range(ciclos):
        info = learner.cycle_once(query=args.query)
        nuevas = info.get("new_cards", [])
        print(f"[A²S] 🌱 ciclo {info.get('cycle')} «{info.get('query')}»: "
              f"{len(nuevas)} ficha(s) nueva(s)"
              + (f" — {info.get('error')}" if info.get("error") else "")
              + (f" — {info.get('budget_stop')}" if info.get("budget_stop") else ""))
        for repo in nuevas[:8]:
            print(f"    · {repo}")
    print(f"[A²S] conocimiento persistido en {os.path.abspath(args.workspace)} "
          "(las misiones lo usan automáticamente al planificar)")
    return 0



def cmd_pcb(args: argparse.Namespace) -> int:
    """Colas de planificación persistentes: estado, apply, resume, enqueue."""
    from .catalog import CATALOG_SIZE, apply_all, build_catalog
    from .kernel import Kernel
    kernel = Kernel.open(args.workspace)
    action = getattr(args, "accion", "status") or "status"
    if action == "apply":
        manifest = apply_all(args.workspace, force=True)
        print(f"[A²S] aplicadas {manifest['applied']}/{CATALOG_SIZE} mejoras")
        return 0 if manifest["applied"] == CATALOG_SIZE else 1
    if action == "catalog":
        items = build_catalog()
        print(f"[A²S] catálogo {len(items)} entradas")
        for item in items[:12]:
            print(f"  {item['id']}  {item['title']}")
        print(f"  … {max(0, len(items) - 12)} más (workspace/.a2s/pcb/CATALOG.md)")
        return 0 if len(items) == CATALOG_SIZE else 1
    if action == "enqueue":
        goal = (args.goal or "").strip()
        if not goal:
            print("✗ falta el objetivo a encolar")
            return 1
        pcb = kernel.admit(goal, kind=args.kind or "mission")
        print(f"[A²S] admitido pid={pcb.pid} cola={pcb.queue} kind={pcb.kind}")
        return 0
    if action == "resume":
        got = kernel.resume_all()
        print(f"[A²S] reanudados {len(got)} PCB")
        for pcb in got:
            print(f"  pid={pcb.pid} pc={pcb.pc} {pcb.goal[:70]}")
        return 0
    snap = kernel.snapshot()
    print(f"A²S PCB · pid_last={snap['last_pid']} · aplicados={snap['applied']}")
    print(f"  ready={snap['ready']} running={snap['running']} "
          f"parked={snap['parked']} blocked={snap['blocked']} "
          f"done={snap['completed']} fail={snap['failed']}")
    print(f"  colas: {snap['queues']}")
    if snap.get("deadlocks"):
        print(f"  deadlock: {snap['deadlocks']}")
    for pcb in snap["procs"][-8:]:
        print(f"  #{pcb['pid']:<5} {pcb['state']:<10} pc={pcb['pc']:<4} "
              f"{pcb['kind']:<8} {pcb['goal'][:56]}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Ciclo de Enriquecimiento: estudiar repos públicos hasta ser capaz
    (verificación objetiva) de resolver el objetivo."""
    from .learner import GitHubClient, Learner
    from .provider_pool import ProviderPool
    from .providers import get_provider

    config = _config_from_args(args)
    print(scope_note())
    provider = get_provider(config.provider, config=config)
    pool = provider if isinstance(provider, ProviderPool) else None
    learner = Learner(workspace=config.workspace, pool=pool,
                      github=GitHubClient(),
                      repos_per_cycle=args.repos)

    def attempt(knowledge: str):
        goal = args.goal if not knowledge else \
            f"{args.goal}\n\n{knowledge}"
        return run_goal(goal, config=config)

    print(f"\n[A²S] ⚛ Ciclo de Enriquecimiento: hasta {args.cycles} ciclo(s), "
          f"{args.repos} repo(s)/ciclo, resumen "
          f"{'pool SORL' if pool else 'extractivo (sin LLM)'}")

    def on_cycle(n: int, info: dict) -> None:
        mark = "✔" if info["won"] else "◐"
        print(f"[A²S] ciclo {n}: {mark} "
              f"{'objetivo verificado' if info['won'] else 'no verificado'} · "
              f"{info.get('knowledge_cards', 0)} ficha(s) aplicadas")
        if info.get("new_cards"):
            print(f"        aprendido de: {', '.join(info['new_cards'])}")
        if info.get("gap_query"):
            print(f"        brecha detectada → «{info['gap_query']}»")

    report = learner.enrich_until_capable(
        args.goal, attempt, verifier=lambda r: bool(getattr(r, "success", False)),
        max_cycles=args.cycles, on_cycle=on_cycle,
        failures_of=lambda r: getattr(r, "final_note", ""))

    print()
    if report["capable"]:
        print(f"[A²S] ✔ CAPAZ — {report['confidence']}")
        print(f"     fichas de conocimiento acumuladas: {report['cards_total']} "
              f"(persistidas en {config.workspace}/.a2s/knowledge/)")
        if hasattr(report.get("last_result"), "final_note"):
            print()
            print(render_text(report["last_result"]))
        if getattr(args, "notify", None):
            notify(args.notify, "A²S learn: CAPAZ (verificado)",
                   report["confidence"], nivel="info")
        return 0
    print(f"[A²S] ◐ {report['confidence']}")
    print("     (las fichas persisten: la siguiente ejecución arranca ya "
          "enriquecida; amplía con --cycles)")
    if getattr(args, "notify", None):
        notify(args.notify, "A²S learn: objetivo NO verificado",
               report["confidence"], nivel="warn")
    return 2


def cmd_scout(args: argparse.Namespace) -> int:
    """Amplía el radar de proyectos OSS leyendo solo metadatos públicos."""
    from .ecosystem import EcosystemRadar
    radar = EcosystemRadar(args.workspace)
    report = radar.scan(query=args.query or "", limit_per_query=args.limit)
    if args.json:
        print(json.dumps({"scan": report, **radar.snapshot()}, ensure_ascii=False, indent=2))
    else:
        print("A²S — radar de ecosistema abierto (solo metadatos; código ejecutado: no)")
        print(f"  encontrados={report['found']} · nuevos={len(report['added'])} · "
              f"actualizados={len(report['updated'])} · total={report['total']}")
        for p in radar.list_projects(limit=12):
            print(f"  {p.fit_score:>3}  {p.repo:<38} {p.license:<12} ★{p.stars}")
        for err in report["errors"]:
            print(f"  aviso: {err}")
    return 0 if not report["errors"] else 2


def cmd_research(args: argparse.Namespace) -> int:
    """Investigación reproducible: checkout, repos recientes/destacables y PDF OA."""
    from .publishing import ResearchStudio
    studio = ResearchStudio(args.workspace)
    report = studio.run(
        args.topic, repo_limit=args.repos, pdf_limit=args.pdfs,
        output_dir=args.output, analyze_local=not args.no_local,
        learn=not args.no_learn, download_pdfs=args.download_pdfs)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        counts = report["source_counts"]
        print(f"[A²S] investigación verificable: {counts['repositories']} repo(s), "
              f"{counts['open_pdfs']} PDF OA + {counts.get('public_pdf_candidates', 0)} "
              f"candidato(s) público(s), {len(report['learned_cards'])} ficha(s) nueva(s)")
        for source in report["sources"][:12]:
            signal = f"★{source['stars']}" if source["stars"] else \
                (f"{source['citations']} citas" if source["citations"] else source["kind"])
            print(f"  [{source['id']}] {signal:<12} {source['title'][:72]}")
        for warning in report["errors"]:
            print(f"  aviso: {warning}")
        print("  artefactos: " + ", ".join(report["artifacts"]))
    return 0 if report["sources"] or report.get("local_repository") else 2


def cmd_book(args: argparse.Namespace) -> int:
    """Construye un libro: literario local-first o de investigación."""
    from .literary import is_literary
    if is_literary(args.topic) or getattr(args, "local", False):
        from .creator import create_document
        result = create_document(args.workspace, args.topic, title=args.title,
                                 kind="book")
    else:
        from .publishing import BookBuilder
        result = BookBuilder(args.workspace).build(
            args.topic, title=args.title, chapters=args.chapters,
            target_words=args.words, output_dir=args.output,
            repo_limit=args.repos, pdf_limit=args.pdfs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mark = "✔" if result.get("status") in ("verified_draft", "original_volume") else "◐"
        score = result.get("quality_score", result.get("quality", {}).get("score", 0))
        print(f"[A²S] {mark} libro {result['status']} · calidad {score}/100 · "
              f"{result.get('word_count', 0)} palabras · "
              f"{result.get('sources', result.get('chapters', 0))} "
              f"{'fuentes' if 'sources' in result else 'capítulos'}")
        print("  artefactos: " + ", ".join(result["artifacts"]))
        limits = (result.get("quality") or {}).get("limitations") or []
        if limits:
            print("  pendiente: " + ", ".join(limits))
    return 0


def cmd_pool_preview(args: argparse.Namespace) -> int:
    """Vista explicable y sin llamadas del scheduler SORL."""
    from .provider_pool import build_pool_provider
    cfg = Config(workspace=args.workspace, quiet=True,
                 pool_config=args.pool_config, pool_strategy=args.pool_strategy or "multi_objective")
    pool = build_pool_provider(cfg)
    try:
        preview = pool.route_preview(args.kind)
        if args.json:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
        else:
            print(f"A²S route preview · kind={args.kind} · estrategia={preview['strategy']}")
            print(f"Ruta seleccionada: {preview['selected']} · llamada real ejecutada: no")
            for row in preview["candidates"]:
                mark = "→" if row["selected"] else " "
                why = ",".join(row["reasons"]) or "elegible"
                print(f" {mark} {row['name']:<24} score={row['utility']:.3f} "
                      f"cuota={row['quota_state']:<17} {why}")
        return 0
    finally:
        pool.close()


def cmd_search(args: argparse.Namespace) -> int:
    """Memoria semántica + repos por palabra clave (cualquier idioma)."""
    from .finder import RepoFinder, format_search
    from .search import workspace_search
    if getattr(args, "repos", False):
        report = RepoFinder(args.workspace).search(args.query, limit=args.top)
        print(format_search(report))
        return 0 if report.get("repositories") or report.get("memory") else 1
    hits = workspace_search(args.workspace, args.query, top=args.top,
                            origenes=set(args.origen) if args.origen else None)
    if not hits:
        report = RepoFinder(args.workspace).search(args.query, limit=args.top)
        print(format_search(report))
        return 0 if report.get("repositories") or report.get("memory") else 1
    print(f"[A²S] BM25 · {args.query!r} · {len(hits)} resultado(s):")
    for doc, score in hits:
        print(f"  {score:>6.3f}  [{doc.origen:<8}] {doc.meta[:90]}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Modo SERVICIO experimental: API REST con RBAC y aislamiento por usuario
    (sin TLS: reverse proxy obligatorio si se expone)."""
    from .serve import make_server
    srv, api = make_server(args.workspace, port=args.port,
                           host="0.0.0.0" if args.public else "127.0.0.1",
                           max_time=args.max_time)
    host_real = "0.0.0.0 (publico)" if args.public else "127.0.0.1"
    print(f"[A²S-serve] API experimental en http://{host_real}:{args.port}")
    print("[A²S-serve]   usuarios: 'a2s users add NOMBRE --role admin|operator|viewer'")
    print("[A²S-serve]   endpoints: /health, /api/status, /api/mission, /api/report,")
    print("[A²S-serve]              /api/search, /api/pool, /api/users (solo admin)")
    print("[A²S-serve]   auditoría: workspace/.a2s/serve_audit.jsonl (todo, denegado incluido)")
    if args.public:
        print("[A²S-serve]   ¡ATENCIÓN: sin TLS ni rate-limit: usa reverse proxy!")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[A²S-serve] detenido")
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    """Gestión local de usuarios del servicio (bootstrap físico: solo aquí)."""
    from .serve import ROLE_PERMS, UserStore
    store = UserStore(args.workspace)
    if args.accion == "add":
        try:
            info = store.add(args.nombre, args.role, hours=args.hours)
        except ValueError as exc:
            print(f"✗ {exc}")
            return 1
        print(f"✔ usuario '{info['user']}' creado con rol '{info['role']}'")
        print(f"  permisos: {', '.join(info['perms'])}")
        print(f"  token (guárdalo ahora, no se vuelve a mostrar):\n  {info['token']}")
        return 0
    data = store.list()
    if not data:
        print("(sin usuarios: crea el primero con 'a2s users add NOMBRE --role admin')")
        return 0
    print(f"{'usuario':<16}{'rol':<10}{'creado':<22}token…")
    for name, u in sorted(data.items()):
        print(f"{name:<16}{u['role']:<10}{u['created_at']:<22}…{u.get('token_hint', '')}")
    print("\nroles disponibles: " + ", ".join(
        f"{r} ({', '.join(sorted(p))})" for r, p in ROLE_PERMS.items()))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Puntuación viva: re-mide los criterios objetivamente medibles."""
    from .audit import render, run_audit
    reporte = run_audit()
    if args.json:
        print(json.dumps(reporte, ensure_ascii=False, indent=2))
    else:
        print(render(reporte))
    return 0 if reporte["todos_ok"] else 1


def cmd_fsm(args: argparse.Namespace) -> int:
    """Nivel 0: ejecuta una máquina de estados determinista (sin LLM);
    lo imprevisto escala al nivel 1 (agente)."""
    from .fsm import FSMEngine, escalation_goal, registry_action_fn
    from .tools import ToolRegistry
    config = _config_from_args(args)
    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    registry = ToolRegistry(config.workspace, allow_network=config.allow_network,
                            allow_shell=not args.no_shell if hasattr(args, "no_shell") else True,
                            shell_unsafe=config.shell_unsafe,
                            network_allowlist=config.network_allowlist,
                            sandbox=config.sandbox)
    engine = FSMEngine(spec, action_fn=registry_action_fn(registry))
    errors = engine.validate()
    if errors:
        print(f"✗ especificación inválida ({args.spec}):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"[A²S-fsm] ⚙ máquina «{engine.name}»: {len(engine.states)} estado(s), "
          f"{len(engine.transitions)} transición(es), presupuesto {engine.max_cycles} ciclo(s)")
    result = engine.run(max_cycles=args.max_cycles)
    print(f"[A²S-fsm] traza: {' → '.join(result.states)}")
    if result.escalated:
        print(f"[A²S-fsm] ◐ IMPREVISTO en «{result.escalated['state']}» → escalando al nivel 1")
        report = run_goal(escalation_goal(engine.name, result.escalated), config=config)
        print(f"[A²S-fsm] nivel 1: {'✔ resuelto' if report.success else '◐ no verificado'}")
        return 0 if report.success else 2
    print(f"[A²S-fsm] {result.resolved_by} · ciclos: {result.cycles}")
    ok = result.stopped == "terminal" and result.terminal == "done"
    return 0 if ok else 2


def cmd_watch(args: argparse.Namespace) -> int:
    """Nivel 0 dirigido por eventos: duerme hasta que un disparador
    (interval/file/webhook) corre la máquina; lo imprevisto escala al nivel 1."""
    from .fsm import FSMEngine, Watcher, escalation_goal, registry_action_fn
    from .models import now_iso
    from .tools import ToolRegistry
    config = _config_from_args(args)
    with open(args.spec, encoding="utf-8") as fh:
        wspec = json.load(fh)
    machine = wspec.get("machine", wspec)
    # rutas relativas de los disparadores file → contra el workspace
    for trig in wspec.get("triggers", []):
        if trig.get("type") == "file" and trig.get("path") and \
                not os.path.isabs(trig["path"]):
            trig["path"] = os.path.join(os.path.abspath(config.workspace), trig["path"])
    log_path = os.path.join(os.path.abspath(config.workspace), ".a2s", "watch.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def on_event(event: dict) -> dict:
        registry = ToolRegistry(config.workspace, allow_network=config.allow_network,
                                allow_shell=not args.no_shell if hasattr(args, "no_shell") else True,
                                shell_unsafe=config.shell_unsafe,
                                network_allowlist=config.network_allowlist,
                                sandbox=config.sandbox)
        engine = FSMEngine(machine, action_fn=registry_action_fn(registry))
        result = engine.run()
        entry = {"at": now_iso(), "event": event.get("type"),
                 "machine": engine.name, "stopped": result.stopped,
                 "terminal": result.terminal, "states": result.states,
                 "resolved_by": result.resolved_by}
        mark = {"terminal": "✔", "escalate": "⇗", "budget": "◐"}.get(result.stopped, "?")
        print(f"[A²S-watch] {mark} evento {event.get('type')} → "
              f"{' → '.join(result.states[:6])} ({result.resolved_by})")
        if result.escalated:
            print(f"[A²S-watch] ⇗ imprevisto en «{result.escalated['state']}» → nivel 1 (agente)")
            report = run_goal(escalation_goal(engine.name, result.escalated), config=config)
            entry["escalation_success"] = bool(report.success)
            print(f"[A²S-watch] {'✔' if report.success else '◐'} nivel 1: "
                  f"{'resuelto' if report.success else 'no verificado'}")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    trig = ", ".join(t.get("type", "?") for t in wspec.get("triggers", [])) or "ninguno"
    print(f"[A²S-watch] ⚙ vigía «{wspec.get('name', machine.get('name', 'fsm'))}» "
          f"armado · disparadores: {trig}")
    print(f"[A²S-watch] máquina determinista: {len(machine.get('states', {}))} estado(s) "
          f"· nivel 1 (agente) para lo imprevisto · log: {log_path}")
    watcher = Watcher(wspec, on_event)
    try:
        results = watcher.run(max_events=args.max_events, idle_timeout=args.idle)
    except KeyboardInterrupt:
        print("\n[A²S-watch] detenido por el operador")
        return 0
    print(f"[A²S-watch] {len(results)} evento(s) procesados")
    return 0


def cmd_pool_status(args: argparse.Namespace) -> int:
    """SORL: estado del pool de recursos legítimos (cuotas, salud, coste)."""
    from .provider_pool import build_pool_provider
    cfg = Config(workspace=args.workspace, quiet=True,
                 pool_config=args.pool_config, pool_strategy=args.pool_strategy)
    pool = build_pool_provider(config=cfg)
    try:
        st = pool.status()
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
            return 0
        t = st["totals"]
        print("A²S — pool SORL (recursos legítimos del operador)")
        print(f"  Estrategia:     {st['strategy']}  ·  pesos: "
              f"{ {k: round(v, 2) for k, v in st['weights'].items()} }")
        print(f"  Endpoints:      {t['endpoints_active']} activo(s), "
              f"{t['endpoints_saturated']} saturado(s)/en cuarentena")
        print(f"  Histórico:      {t['total_calls']} llamadas, {t['total_ok']} ok, "
              f"coste estimado ${t['est_cost']}")
        print()
        hdr = f"  {'endpoint':<16}{'tier':<7}{'rpm':>4}{'uso':>5}{'cuarentena':>11}{'p50':>7}{'éxito':>7}  modelo/estado"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for e in st["endpoints"]:
            quar = f"{e['cooldown_remaining_s']:.0f}s" if e["cooldown_remaining_s"] > 0 else "-"
            p50 = f"{e['p50_ms']}ms" if e.get("p50_ms") is not None else "-"
            rate = f"{e['success_rate']*100:.0f}%" if e.get("success_rate") is not None else "-"
            note = e["model"] if e["role"] == "member" else f"({e['role']})"
            if e.get("rpm_learned"):
                note += f" [rpm aprendido: {e['rpm_effective']} (declarado {e['rpm']})]"
            caps = e.get("capability_measured") or {}
            if caps:
                frag = ", ".join(f"{k} {v['score']:.2f} ({v['ok']}/{v['total']})"
                                 for k, v in sorted(caps.items()))
                note += f" [caps medida: {frag}]"
            if e.get("disabled_reason"):
                note = f"DESACTIVADO: {e['disabled_reason']}"
            elif e.get("circuit_open"):
                note += " [circuito abierto]"
            rpm_show = e.get("rpm_effective", e["rpm"])
            print(f"  {e['name']:<16}{e['cost_tier']:<7}{rpm_show or '-':>4}"
                  f"{e['window_used']:>5}{quar:>11}{p50:>7}{rate:>7}  {note}")
        if t["endpoints_active"] == 0:
            print("\n  ⚠ sin endpoints activos: exporta GROQ_API_KEY / GEMINI_API_KEY / "
                  "GITHUB_TOKEN… o crea workspace/.a2s/pool.json (ver examples/pool.example.json)")
        return 0
    finally:
        pool.close()


def cmd_pool_check(args: argparse.Namespace) -> int:
    """SORL: comprobación de salud — 1 petición mínima por endpoint (respeta cuotas)."""
    from .provider_pool import build_pool_provider
    cfg = Config(workspace=args.workspace, quiet=True,
                 pool_config=args.pool_config, pool_strategy=args.pool_strategy)
    pool = build_pool_provider(config=cfg)
    try:
        members = [e for e in pool.endpoints if e.active and e.role == "member"]
        print(f"A²S — comprobación del pool: {len(members)} endpoint(s) "
              "(1 petición pequeña por endpoint)")
        failures = 0
        for ep in members:
            st = pool._states[ep.name]
            if not pool._windows[ep.name].try_acquire():
                print(f"  ◐ {ep.name:<16} sin cuota disponible ahora (rpm={ep.rpm}) — omitido")
                continue
            t0 = time.monotonic()
            try:
                data = pool._send(ep, {"model": ep.model, "max_tokens": 4,
                                       "messages": [{"role": "user", "content": "ping"}]})
                ms = (time.monotonic() - t0) * 1000
                st.record_success()
                pool.telemetry.record(ep.name, ok=True, latency=ms / 1000, kind="health",
                                      tokens=4)
                print(f"  ✔ {ep.name:<16} {ms:6.0f} ms  {ep.model}")
            except Exception as exc:  # noqa: BLE001 — diagnóstico por endpoint
                failures += 1
                reason = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) \
                    else f"{type(exc).__name__}"
                st.record_failure(reason, time.monotonic())
                pool.telemetry.record(ep.name, ok=False,
                                      latency=time.monotonic() - t0, kind="health",
                                      status=getattr(exc, "code", None))
                print(f"  ✗ {ep.name:<16} {reason} — revisa la clave/base_url ({ep.base_url})")
        pool.close()
        if failures:
            print(f"\n{failures} endpoint(s) con fallos — el scheduler los degradará "
                  "hasta que se recuperen (failover automático).")
            return 1
        print("\n✔ pool operativo")
        return 0
    finally:
        pool.telemetry.save_snapshot()


def _recursos_export(args: argparse.Namespace) -> Optional[int]:
    """Exportaciones --html / --pdf / --md (None = seguir con el listado)."""
    from .recursos import como_html, como_markdown
    if args.html is not None:
        os.makedirs(os.path.dirname(args.html) or ".", exist_ok=True)
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(como_html(args.workspace))
        print(f"[A²S] ✔ HTML exportado: {os.path.abspath(args.html)}")
        return 0
    if args.pdf is not None:
        from .recursos import como_pdf
        os.makedirs(os.path.dirname(args.pdf) or ".", exist_ok=True)
        pages = como_pdf(args.pdf, workspace=args.workspace)
        print(f"[A²S] ✔ PDF exportado: {os.path.abspath(args.pdf)} ({pages} pág.)")
        return 0
    if args.ppt is not None:
        from .recursos import como_pptx
        os.makedirs(os.path.dirname(args.ppt) or ".", exist_ok=True)
        n_slides = como_pptx(args.ppt, workspace=args.workspace)
        print(f"[A²S] ✔ PPT exportado: {os.path.abspath(args.ppt)} "
              f"({n_slides} diapositivas)")
        return 0
    if args.md:
        print(como_markdown(args.workspace))
        return 0
    return None


def _recursos_estado(workspace: str) -> int:
    """Muestra el último chequeo de enlaces persistido en el workspace."""
    from .recursos import estado_check
    check = estado_check(workspace)
    if not check:
        print(f"[A²S] (sin chequeo todavía en {workspace} — "
              "ejecuta: a2s recursos --check)")
        return 1
    print(f"A²S — último chequeo de enlaces: {(check.get('at') or '')[:16]} · "
          f"{check.get('ok')}/{check.get('total')} alcanzables · "
          f"timeout {check.get('timeout')}s")
    results = check.get("results") or {}
    falls = [(rid, st) for rid, st in results.items()
             if not st.get("ok") and st.get("estado") != "sin enlace"]
    for rid, st in falls:
        print(f"  ✗ {rid}  {st.get('estado')}  {st.get('ms')} ms")
    if not falls:
        print("  ✔ todos los enlaces con URL fueron alcanzables en ese momento")
    return 0


def _recursos_accion(args: argparse.Namespace) -> Optional[int]:
    """Sub-acciones add / forget / extra (None = seguir con el listado)."""
    from .recursos import extras, extra_add, extra_forget
    accion = args.accion
    if accion not in ("add", "forget", "extra"):
        return None
    ws = args.workspace
    if accion == "extra":
        rows = extras(ws)
        if args.json:
            print(json.dumps({"total": len(rows), "recursos": rows},
                             ensure_ascii=False, indent=2))
            return 0
        if not rows:
            print(f"[A²S] (sin recursos propios en {ws})")
            return 0
        for r in rows:
            print(f"  {r['id']}  {r['nombre']}")
            print(f"      {r['url'] or '(sin enlace)'}")
        return 0
    if accion == "forget":
        if extra_forget(ws, args.nombre or ""):
            print(f"[A²S] ✔ olvidado: {args.nombre}")
            return 0
        print("✗ no encontrado (solo se olvidan los propios del workspace)")
        return 1
    try:
        entry = extra_add(ws, args.nombre or "", args.url or "",
                          args.categoria or "ia", desc=args.desc or "",
                          tags=[t for t in (args.tags or "").split(",")])
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"[A²S] ✔ recurso añadido: {entry['id']} · {entry['nombre']}")
    print(f"      {entry['url'] or '(sin enlace)'} · categoría {entry['cat']} "
          f"· persistido en {ws}/.a2s/recursos.json")
    return 0


def _recursos_check(args: argparse.Namespace, data: dict) -> int:
    """--check: disponibilidad HTTP (CI-friendly, persiste; en paralelo)."""
    from .recursos import comprobar_enlaces, guardar_check
    rows = [r for r in data["recursos"]
            if not args.id or r["id"] in args.id]
    results = comprobar_enlaces(rows, timeout=args.timeout,
                                workers=args.workers)
    con_url = [r for r in results if not r["sin_enlace"]]
    ok = sum(1 for r in con_url if r["ok"])
    modo = f"workers {args.workers}" if args.workers > 1 else "secuencial"
    for r in results:
        mark = "✔" if r["ok"] else ("·" if r["sin_enlace"] else "✗")
        ms = f"{r['ms']} ms" if r["ms"] is not None else "-"
        print(f"  {mark} {r['nombre'][:40]:<40} {r['estado']:<16} {ms}")
    print(f"\n[A²S] {ok}/{len(con_url)} enlaces alcanzables "
          f"(timeout {args.timeout}s, {modo}; "
          f"{len(results) - len(con_url)} sin enlace)")
    if args.id:
        print("[A²S] (subconjunto con --id: estado NO persistido)")
    else:
        guardar_check(args.workspace, results, timeout=args.timeout)
        print("[A²S] estado persistido — a2s recursos --estado para repasar")
    return 0 if con_url and ok == len(con_url) else 1


def _recursos_check_watch(args: argparse.Namespace, data: dict,
                          max_cycles: Optional[int] = None) -> int:
    """Guardián de chequeo periódico: el estado no caduca solo."""
    import time
    print(f"[A²S] 🛰 guardián de chequeo: ciclo cada {args.watch}s "
          "(Ctrl+C para parar)")
    ciclos = 0
    while max_cycles is None or ciclos < max_cycles:
        ciclos += 1
        print(f"\n=== ciclo {ciclos} ===")
        _recursos_check(args, data)
        if max_cycles is None or ciclos < max_cycles:
            time.sleep(args.watch)
    return 0


def _fmt_requiere(requiere: list[str]) -> str:
    from .capacidades import REQ_NOMBRE
    return ", ".join(REQ_NOMBRE.get(r, r) for r in requiere) or "ninguna"


def cmd_promptguard(args: argparse.Namespace) -> int:
    """PromptGuard: detección defensiva de inyección de prompts/jailbreaks."""
    from .promptguard import clasificar, documentar, formato_legible
    texto = args.texto or ""
    if args.archivo:
        path = os.path.abspath(os.path.join(os.path.abspath(args.workspace),
                                            args.archivo))
        root = os.path.abspath(args.workspace or ".")
        if not (path.startswith(root + os.sep) or path == root):
            print("✗ archivo fuera del workspace")
            return 1
        if not os.path.isfile(path):
            print(f"✗ archivo no encontrado: {args.archivo}")
            return 1
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                texto = fh.read(50_000)
        except OSError as exc:
            print(f"✗ no se pudo leer: {exc}")
            return 1
    veredicto = clasificar(texto)
    if args.ledger and veredicto.veredicto != "sin_texto":
        registrado = documentar(args.workspace, veredicto)
        if args.json:
            print(json.dumps({**veredicto.to_dict(),
                              "registrado": registrado["ledger"]["hash"][:16]},
                             ensure_ascii=False, indent=2))
            return 0
        print("[A²S] hallazgo registrado en el ledger (cadena de custodia)")
    elif args.json:
        print(json.dumps(veredicto.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(formato_legible(veredicto))
    return 0


def cmd_secops(args: argparse.Namespace) -> int:
    """SecOps asistido: alcance criptográfico + ejecución defensiva local."""
    from .secops import (crear_scope, estado_scope, ejecutar, resumen_secops)
    if args.accion == "scope-create":
        try:
            data = crear_scope(
                args.workspace,
                targets=[t for t in (args.targets or "").split(",") if t.strip()],
                acciones=[a for a in (args.acciones or "").split(",") if a.strip()],
                expires=args.expires, firma=args.firma)
        except ValueError as exc:
            print(f"✗ {exc}")
            return 1
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        print("[A²S] alcance firmado (HMAC-SHA256, vocabulario cerrado):")
        print(f"  firmante: {data['signed_by']}")
        print(f"  targets:  {', '.join(data['targets'])}")
        print(f"  acciones: {', '.join(data['acciones'])}")
        print(f"  expira:   {data['expires']}")
        print(f"  archivo:  {args.workspace}/.a2s/scope.jwt")
        return 0
    if args.accion == "scope-status":
        estado = estado_scope(args.workspace)
        if args.json:
            print(json.dumps(estado, ensure_ascii=False, indent=2))
            return 0
        if not estado["valido"]:
            print(f"A²S — alcance: INVALIDO · {estado.get('motivo', '')}")
            print("  crea uno con: a2s secops scope-create --targets ... "
                  "--acciones recon,scan,analizar --firma \"...\"")
            return 0
        print(f"A²S — alcance: VÁLIDO · firmante {estado['signed_by']}")
        print(f"  targets:  {', '.join(estado['targets'])}")
        print(f"  acciones: {', '.join(estado['acciones'])}")
        print(f"  expira:   {estado['expires']} · emitido {estado['iat']}")
        return 0
    try:
        report = ejecutar(args.objetivo, modo=args.modo, workspace=args.workspace,
                          targets=[t for t in (args.targets or "").split(",")
                                   if t.strip()] or None,
                          archivo=args.archivo, templates=args.templates,
                          confirm=args.confirm)
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"A²S — SecOps · modo {report['modo']} · «{report['objetivo']}»")
    print(f"  scope: {'VÁLIDO' if report['scope']['valido'] else 'sin alcance'}"
          if report['modo'] == "asistido" else
          "  scope: no necesario en simulación")
    for paso in report["pasos"]:
        marca = {"simulado": "·", "ok": "✔", "denegado": "✗", "omitido": "•",
                 "sin_objetivo": "•", "error": "✗"}.get(paso["estado"], "?")
        print(f"  {marca} {paso['nombre']} ({paso['tipo']})")
        if paso.get("motivo"):
            print(f"        → {paso['motivo']}")
        if paso.get("reporte") and paso["estado"] == "ok":
            r = paso["reporte"]
            detalle = (f"HTTP {r.get('status')} · {r.get('ms')}ms"
                       if "status" in r else
                       f"{r.get('scanner')}: {r.get('total')} hallazgos"
                       if "scanner" in r else
                       f"sha256 {str(r.get('sha256', ''))[:16]}…")
            print(f"        → {detalle}")
    if report["modo"] == "asistido":
        print(f"  run: {report.get('run_id', '')} · informe en "
              f"{args.workspace}/.a2s/secops/")
    else:
        print(f"  nota: {report['nota']}")
    return 0





def cmd_capacidades(args: argparse.Namespace) -> int:
    """Mapa fuente→capacidad→A²S y enrutador con puerta de autorización."""
    if args.ingesta:
        from .capacidades import ingesta
        try:
            report = ingesta(args.workspace, max_calls=args.calls,
                             solo=args.solo, refresh=args.refresh)
        except Exception as exc:  # noqa: BLE001 — presupuesto/cuota de GitHub
            print(f"✗ ingesta detenida: {exc}")
            return 1
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        print(f"[A²S] ingesta de capacidades: {report['total']} procesadas · "
              f"{report['ok']} ok · {report['revisar']} para revisar · "
              f"{report['error']} error · {report['referencia']} referencia")
        print(f"      fichas en workspace/.a2s/knowledge/ y estados en "
              f"workspace/.a2s/capacidades/ingesta.json (reanudable)")
        for rid, st in report["estados"].items():
            if st.get("estado") in ("revisar", "error"):
                print(f"      {'!' if st.get('estado') == 'error' else '~'} "
                      f"{rid}: {st.get('motivo', '')}")
        return 0

    if args.alcance:
        from .capacidades import PERFILES, alcance_info, alcance_path, crear_alcance
        if args.perfil:
            try:
                data = crear_alcance(args.workspace, perfil=args.perfil,
                                     nota=args.nota,
                                     hosts=tuple(args.hosts or ()) or None)
            except ValueError as exc:
                print(f"✗ {exc}")
                return 1
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 0
            print("[A²S] alcance registrado (auditable):")
            print(f"  perfil: {data['perfil']} — {data['perfil_nombre']}")
            print(f"  nota:   {data['nota']}")
            print(f"  hosts:  {', '.join(data['hosts'])}")
            print(f"  archivo: {alcance_path(args.workspace)}")
            return 0
        info = alcance_info(args.workspace)
        if args.json:
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        if not info["existe"]:
            print(f"A²S — sin alcance registrado en {info['path']}")
            print("Registra tu marco académico/ético:")
            print(f"  a2s capacidades --alcance --perfil "
                  f"ctf|lab|propio|universidad --nota \"clase HTB 2026\"")
            return 0
        print(f"A²S — alcance: {'VÁLIDO' if info['valido'] else 'INCOMPLETO'}"
              f" · perfil {info['perfil'] or '—'}")
        print(f"  nota:  {info['nota'] or '—'}")
        print(f"  hosts: {', '.join(info['hosts']) or '—'}")
        print(f"  archivo: {info['path']}")
        return 0

    if args.ruta:
        from .capacidades import seleccionar
        try:
            plan = seleccionar(args.ruta, contexto=args.ctx,
                               workspace=args.workspace, perfil=args.perfil)
        except ValueError as exc:
            print(f"✗ {exc}")
            return 1
        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        print(f"A²S — enrutador de capacidades para «{plan['objetivo']}»")
        print(f"Intención detectada: {plan['intento']}")
        print(f"Autorización: {'válida' if plan['autorizacion']['valida'] else 'NO hay alcance válido'} "
              f"({plan['autorizacion']['path']})")
        print()
        for paso in plan["pasos"]:
            print(f"  {paso['id']} · {paso['nombre']}")
            print(f"      uso: {paso['uso_nombre']}")
            print(f"      por qué: {paso['por_que']}")
            print(f"      requiere: {_fmt_requiere(paso['requiere'])}")
            print(f"      equivalente A²S: {', '.join(paso['mapa_a2s']) or '—'}")
        if plan["bloqueados"]:
            print("\nRetenidos por la puerta de ética:")
            for b in plan["bloqueados"]:
                print(f"  ✗ {b['id']} · {b['nombre']}: {b['motivo']}")
        print(f"\nSugerencia defensiva: {plan['sugerencia_defensiva']}")
        print(f"Resumen: {plan['resumen']}")
        return 0

    if args.mapa is not None:
        from .capacidades import mapa_markdown
        contenido = mapa_markdown(args.workspace)
        if args.mapa == "-":
            print(contenido)
        else:
            with open(args.mapa, "w", encoding="utf-8") as fh:
                fh.write(contenido)
            print(f"[A²S] mapa de capacidades escrito en {args.mapa}")
        return 0

    from .capacidades import core_ids, resumen
    data = resumen(args.workspace)
    if args.core or args.json:
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        print(f"Core ({len(core_ids())}):")
        for ident in core_ids():
            print(f"  - {ident}")
        return 0
    print(f"A²S — mapa de capacidades: {data['total']} recursos mapeados")
    print(f"Puerta de ética: {data['con_puerta']} recursos con alcance escrito; "
          f"{data['autonomas']} de uso autónomo")
    ing = data['ingesta']
    print(f"Ingesta: {ing.get('ok', 0)} ok · {ing.get('revisar', 0)} revisar · "
          f"{ing.get('error', 0)} error · {ing.get('referencia', 0)} referencia\n")
    for dom in data["dominios"]:
        print(f"{dom['nombre']}: {dom['count']}")
    for uso in data["usos"]:
        print(f"  {uso['nombre']}: {uso['count']}")
    print("\nCore:", ", ".join(core_ids()))
    print("Usos: a2s capacidades ruta OBJETIVO · a2s capacidades ingesta "
          "--calls 40 · a2s capacidades --mapa")
    return 0


def cmd_recursos(args: argparse.Namespace) -> int:
    """Catálogo curado de recursos del operador (referencia, sin ejecución)."""
    from .recursos import api_snapshot, validar
    for code in (_recursos_export(args), _recursos_accion(args)):
        if code is not None:
            return code
    if args.estado:
        return _recursos_estado(args.workspace)
    if args.watch and not args.check:
        print("✗ --watch requiere --check (el guardián solo chequea enlaces)")
        return 1
    problemas = validar(args.workspace)
    if problemas:
        print("✗ catálogo con problemas de integridad:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    data = api_snapshot(consulta=args.buscar or "", cat=args.categoria or "",
                        top=args.top, workspace=args.workspace)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    if args.check:
        if args.watch:
            try:
                _recursos_check_watch(args, data)
                return 0
            except KeyboardInterrupt:
                print("\n[A²S] guardián de chequeo detenido por el operador")
                return 0
        return _recursos_check(args, data)
    if data["consulta"]:
        print(f"A²S — catálogo de recursos: {len(data['recursos'])} resultado(s) "
              f"para «{data['consulta']}»")
    else:
        print(f"A²S — catálogo de recursos: {data['total']} entradas en "
              f"{len(data['categorias'])} categorías")
    print(f"filtro ético: {data['aviso']}\n")
    for cat in data["categorias"]:
        rows = [r for r in data["recursos"] if r["cat"] == cat["id"]]
        if not rows:
            continue
        print(f"{cat['nombre']} ({len(rows)})")
        for r in rows:
            marca = "⚠" if "advertido" in r["tags"] else "·"
            print(f"  {marca} {r['nombre']}")
            print(f"      {r['url'] or '(sin enlace oficial)'}")
            print(f"      {r['desc']}")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="a2s",
        description="A²S — Agente Autónomo Supremo con capacidades forenses "
                    "(loops auto-optimizados, superación de estancamiento, "
                    "memoria evolutiva, cadena de custodia).")
    parser.add_argument("--version", action="version", version=f"A²S {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="ejecuta el agente hacia un objetivo")
    p_run.add_argument("goal", help="objetivo (varios separados por ';')")
    p_run.add_argument("--parallel", action="store_true",
                       help="despliega sub-agentes fractales en paralelo")
    _add_common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_sup = sub.add_parser("supervise",
                           help="auto-existencia: se relanza hasta cumplir el objetivo")
    p_sup.add_argument("goal")
    p_sup.add_argument("--attempts", type=int, default=5)
    p_sup.add_argument("--sleep", type=int, default=2)
    _add_common(p_sup)
    p_sup.set_defaults(func=cmd_supervise)

    p_swarm = sub.add_parser("swarm",
                             help="réplicas autónomas en procesos paralelos (un worker por objetivo)")
    p_swarm.add_argument("goal", help="objetivos separados por ';'")
    p_swarm.add_argument("--workers", type=int, default=2)
    p_swarm.add_argument("--workspace", default="workspace")
    p_swarm.set_defaults(func=cmd_swarm)

    p_demo = sub.add_parser("demo", help="misión demo: informe forense autónomo")
    _add_common(p_demo)
    p_demo.set_defaults(func=cmd_demo)

    p_learn = sub.add_parser(
        "learn", help="Ciclo de Enriquecimiento: estudia repos públicos de GitHub "
                      "hasta verificar que sabe resolver el objetivo")
    p_learn.add_argument("goal", help="problema a resolver (la brecha se detecta sola)")
    p_learn.add_argument("--cycles", type=int, default=3,
                         help="máximo de ciclos intentar→aprender→reintentar")
    p_learn.add_argument("--repos", type=int, default=4,
                         help="repositorios estudiados por ciclo")
    _add_common(p_learn)
    p_learn.set_defaults(func=cmd_learn)

    p_scout = sub.add_parser(
        "scout", help="radar OSS: busca nuevos proyectos públicos para aprender "
                      "patrones sin clonar ni ejecutar su código")
    p_scout.add_argument("--workspace", default="workspace")
    p_scout.add_argument("--query", default="",
                         help="consulta GitHub opcional (vacío = radar multidominio)")
    p_scout.add_argument("--limit", type=int, default=6,
                         help="resultados máximos por consulta (default: 6)")
    p_scout.add_argument("--json", action="store_true")
    p_scout.set_defaults(func=cmd_scout)

    p_research = sub.add_parser(
        "research", help="investigación verificable: analiza el checkout y descubre "
                         "repos recientes/destacables y PDF de acceso abierto")
    p_research.add_argument("topic", help="tema o pregunta de investigación")
    p_research.add_argument("--workspace", default="workspace")
    p_research.add_argument("--repos", type=int, default=8)
    p_research.add_argument("--pdfs", type=int, default=8)
    p_research.add_argument("--output", default="research")
    p_research.add_argument("--download-pdfs", action="store_true",
                            help="descargar solo PDF marcados open access (máx 20 MB)")
    p_research.add_argument("--no-local", action="store_true",
                            help="no analizar estáticamente el workspace")
    p_research.add_argument("--no-learn", action="store_true",
                            help="no crear fichas ni añadir el tema al currículo")
    p_research.add_argument("--json", action="store_true")
    p_research.set_defaults(func=cmd_research)

    p_book = sub.add_parser(
        "book", help="crea un libro con investigación, citas, Markdown, HTML, PDF y quality gate")
    p_book.add_argument("topic", help="tema central del libro")
    p_book.add_argument("--title", default="")
    p_book.add_argument("--workspace", default="workspace")
    p_book.add_argument("--chapters", type=int, default=6)
    p_book.add_argument("--words", type=int, default=3000,
                        help="extensión objetivo total")
    p_book.add_argument("--repos", type=int, default=6)
    p_book.add_argument("--pdfs", type=int, default=8)
    p_book.add_argument("--output", default="book")
    p_book.add_argument("--json", action="store_true")
    p_book.add_argument("--local", action="store_true",
                        help="forzar companion original sin investigación de red")
    p_book.set_defaults(func=cmd_book)

    p_bus = sub.add_parser("search", help="memoria semántica: búsqueda BM25 sobre "
                                          "episodios, fichas de conocimiento y pool")
    p_bus.add_argument("query", help="consulta en lenguaje natural")
    p_bus.add_argument("--workspace", default="workspace")
    p_bus.add_argument("--top", type=int, default=5)
    p_bus.add_argument("--origen", action="append", default=None,
                       help="filtrar por origen (episodio|ficha|pool|recurso|"
                            "investigacion, repetible)")
    p_bus.add_argument("--repos", action="store_true",
                       help="buscar también repositorios públicos por palabra clave")
    p_bus.set_defaults(func=cmd_search)

    p_srv = sub.add_parser("serve", help="modo SERVICIO experimental: API REST con "
                                          "RBAC y aislamiento por usuario (§15)")
    p_srv.add_argument("--workspace", default="workspace")
    p_srv.add_argument("--port", type=int, default=8700)
    p_srv.add_argument("--max-time", type=int, default=300,
                       help="timebox por misión en el servicio (segundos)")
    p_srv.add_argument("--public", action="store_true",
                       help="escuchar en 0.0.0.0 (sin TLS: reverse proxy obligatorio)")
    p_srv.set_defaults(func=cmd_serve)

    p_usr = sub.add_parser("users", help="usuarios del servicio (RBAC local)")
    p_usr.add_argument("accion", choices=["add", "list"])
    p_usr.add_argument("nombre", nargs="?", default=None)
    p_usr.add_argument("--role", default="operator",
                       choices=["admin", "operator", "viewer"])
    p_usr.add_argument("--workspace", default="workspace")
    p_usr.add_argument("--hours", type=float, default=24.0,
                       help="validez del token emitido")
    p_usr.set_defaults(func=cmd_users)

    p_aud = sub.add_parser("audit", help="puntuación viva: re-mide los criterios "
                                        "medibles (el 6/5 no existe)")
    p_aud.add_argument("--json", action="store_true")
    p_aud.set_defaults(func=cmd_audit)

    p_fsm = sub.add_parser(
        "fsm", help="nivel 0 determinista: máquina de estados sin LLM "
                    "(lo imprevisto escala al agente)")
    p_fsm.add_argument("spec", help="ruta del JSON de la máquina (ver examples/fsm.example.json)")
    p_fsm.add_argument("--max-cycles", type=int, default=None,
                       help="override del presupuesto de ciclos")
    _add_common(p_fsm)
    p_fsm.set_defaults(func=cmd_fsm)

    p_watch = sub.add_parser(
        "watch", help="nivel 0 dirigido por eventos: interval/file/webhook disparan "
                      "la máquina determinista; lo imprevisto escala al agente")
    p_watch.add_argument("spec", help="ruta del JSON del vigía (ver examples/watch.example.json)")
    p_watch.add_argument("--max-events", type=int, default=None,
                         help="parar tras N eventos (default: hasta timeout de inactividad)")
    p_watch.add_argument("--idle", type=float, default=300.0,
                         help="segundos sin eventos antes de parar (default 300)")
    _add_common(p_watch)
    p_watch.set_defaults(func=cmd_watch)

    p_dash = sub.add_parser("dashboard", help="panel de control web en vivo")
    p_dash.add_argument("--port", type=int, default=8000)
    p_dash.add_argument("--workspace", default="workspace")
    p_dash.add_argument("--public", action="store_true",
                        help="escuchar en 0.0.0.0 (⚠ cualquiera en la red puede lanzar misiones)")
    p_dash.add_argument("--auth", action="store_true",
                        help="exigir token de acceso (genéralo con: a2s token)")
    p_dash.add_argument("--autodemo", action="store_true",
                        help="lanzar la misión demo al iniciar (por defecto espera al operador)")
    p_dash.add_argument("--no-autodemo", action="store_false", dest="autodemo",
                        help=argparse.SUPPRESS)
    p_dash.add_argument("--learn-interval", type=int, default=1800,
                        help="segundos entre ciclos de crecimiento autónomo "
                             "(default 1800; A2S_AUTO_LEARN=0 lo desactiva)")
    p_dash.set_defaults(func=cmd_dashboard, autodemo=False)

    p_tok = sub.add_parser("token", help="genera un token de acceso para el dashboard")
    p_tok.add_argument("--workspace", default="workspace")
    p_tok.add_argument("--hours", type=float, default=1.0)
    p_tok.set_defaults(func=cmd_token)

    p_ver = sub.add_parser("verify", help="verificación criptográfica: cadena de custodia + firmas HMAC")
    p_ver.add_argument("--workspace", default="workspace")
    p_ver.set_defaults(func=cmd_verify)

    p_evo = sub.add_parser("evolve", help="neuroevolución de la red de gobernanza desde los episodios")
    p_evo.add_argument("--workspace", default="workspace")
    p_evo.add_argument("--generations", type=int, default=5)
    p_evo.set_defaults(func=cmd_evolve)

    p_live = sub.add_parser("build-live", help="empaqueta A²S como un solo archivo ejecutable (zipapp)")
    p_live.add_argument("--output", default="dist/a2s.pyz")
    p_live.set_defaults(func=cmd_build_live)

    p_rep = sub.add_parser("report", help="lee un informe JSON previo")
    p_rep.add_argument("path")
    p_rep.set_defaults(func=cmd_report)

    p_doc = sub.add_parser("doctor", help="diagnóstico del entorno")
    p_doc.add_argument("--workspace", default="workspace")
    p_doc.set_defaults(func=cmd_doctor)

    p_ps = sub.add_parser("pool-status",
                          help="SORL: estado del pool de proveedores (cuotas, salud, coste)")
    p_ps.add_argument("--workspace", default="workspace")
    p_ps.add_argument("--pool-config", default=None,
                      help="ruta del JSON del pool (default: workspace/.a2s/pool.json o autodescubrimiento)")
    p_ps.add_argument("--pool-strategy", default=None,
                      help="round_robin | cost_first | speed_first | multi_objective")
    p_ps.add_argument("--json", action="store_true", help="salida JSON")
    p_ps.set_defaults(func=cmd_pool_status)

    p_pc = sub.add_parser("pool-check",
                          help="SORL: comprobación de salud del pool (1 petición por endpoint)")
    p_pc.add_argument("--workspace", default="workspace")
    p_pc.add_argument("--pool-config", default=None)
    p_pc.add_argument("--pool-strategy", default=None)
    p_pc.set_defaults(func=cmd_pool_check)

    p_rec = sub.add_parser(
        "recursos", help="catálogo curado de recursos del operador (referencia: "
                         "uso autorizado, defensivo o académico)")
    p_rec.add_argument("accion", nargs="?", default=None,
                       choices=[None, "add", "forget", "extra"],
                       help="add NOMBRE URL (recursos propios) | forget ID | "
                            "extra (lista los propios) | vacío = catálogo")
    p_rec.add_argument("nombre", nargs="?", default="",
                       help="NOMBRE (en add) o ID (en forget)")
    p_rec.add_argument("url", nargs="?", default="",
                       help="URL en http(s) (solo add; opcional)")
    p_rec.add_argument("--categoria", "--cat", dest="categoria", default="",
                       help="categoría (add) o filtro (listado): ia, ciber, dev, "
                            "directorios, utilidades, empleo — o texto del nombre")
    p_rec.add_argument("--buscar", default="",
                       help="búsqueda BM25 por nombre, descripción, etiquetas o URL")
    p_rec.add_argument("--top", type=int, default=25,
                       help="resultados máximos con --buscar (default 25)")
    p_rec.add_argument("--desc", default="", help="nota descriptiva (solo add)")
    p_rec.add_argument("--tags", default="",
                       help="etiquetas separadas por coma (solo add)")
    p_rec.add_argument("--workspace", default="workspace")
    p_rec.add_argument("--json", action="store_true", help="salida JSON")
    p_rec.add_argument("--md", action="store_true",
                       help="exporta el catálogo completo en Markdown")
    p_rec.add_argument("--html", nargs="?", const="recursos.html", default=None,
                       metavar="RUTA",
                       help="exporta un HTML autocontenido (default: recursos.html)")
    p_rec.add_argument("--pdf", nargs="?", const="recursos.pdf", default=None,
                       metavar="RUTA",
                       help="exporta un PDF impreso (default: recursos.pdf)")
    p_rec.add_argument("--ppt", nargs="?", const="recursos.pptx", default=None,
                       metavar="RUTA",
                       help="exporta una presentación del catálogo "
                            "(default: recursos.pptx)")
    p_rec.add_argument("--watch", nargs="?", const=3600, type=int, default=None,
                       metavar="SEGUNDOS",
                       help="con --check: guardián que re-chequea cada N "
                            "segundos (default 3600) hasta Ctrl+C")
    p_rec.add_argument("--estado", action="store_true",
                       help="muestra el último chequeo de enlaces persistido")
    p_rec.add_argument("--check", action="store_true",
                       help="verifica la disponibilidad HTTP de los enlaces "
                            "(los del filtro actual; --id acota)")
    p_rec.add_argument("--id", action="append", default=None,
                       help="solo estas ids (con --check; repetible)")
    p_rec.add_argument("--timeout", type=float, default=8.0,
                       help="segundos por enlace con --check (default 8)")
    p_rec.add_argument("--workers", type=int, default=8,
                       help="enlaces verificados en paralelo con --check "
                            "(0 = secuencial, reproducible; default 8)")
    p_rec.set_defaults(func=cmd_recursos)

    p_sec = sub.add_parser(
        "secops",
        help="SecOps asistido: alcance criptográfico (scope.jwt) + ejecución "
             "defensiva local (recon/scan/analizar; vocabulario cerrado)")
    p_sec.add_argument("accion", choices=["scope-create", "scope-status", "ejecutar"])
    p_sec.add_argument("objetivo", nargs="?", default="",
                       help="objetivo a enrutar (solo ejecutar)")
    p_sec.add_argument("--targets", default="",
                       help="hosts/CIDR separados por coma (scope-create y "
                            "targets de recon/scan en ejecutar)")
    p_sec.add_argument("--acciones", default="recon,scan,analizar",
                       help="acciones del scope (cerrado: recon|scan|analizar)")
    p_sec.add_argument("--expires", default="",
                       help="YYYY-MM-DDTHH:MM:SSZ (default +30 días)")
    p_sec.add_argument("--firma", default="",
                       help="identidad del firmante (obligatoria en scope-create)")
    p_sec.add_argument("--modo", default="simulacion",
                       choices=["simulacion", "asistido"],
                       help="simulacion = plan sin red (default); asistido = "
                            "ejecuta adaptadores defensivos con alcance")
    p_sec.add_argument("--archivo", default="",
                       help="archivo del workspace para analizar/trivy fs")
    p_sec.add_argument("--templates", default="",
                       help="plantillas extra para nuclei (opcional)")
    p_sec.add_argument("--confirm", action="store_true",
                       help="confirma los pasos de red (recon/scan)")
    p_sec.add_argument("--workspace", default="workspace")
    p_sec.add_argument("--json", action="store_true", help="salida JSON")
    p_sec.set_defaults(func=cmd_secops)

    p_pg = sub.add_parser(
        "promptguard",
        help="detección defensiva de inyección de prompts y jailbreaks "
             "(marca señal; no genera vectores de evasión)")
    p_pg.add_argument("accion", choices=["check"])
    p_pg.add_argument("texto", nargs="?", default="",
                       help="texto a inspeccionar (o usa --file)")
    p_pg.add_argument("--file", dest="archivo", default="",
                       help="ruta (relativa al workspace) del texto a revisar")
    p_pg.add_argument("--ledger", action="store_true",
                       help="registra el hallazgo en el ledger")
    p_pg.add_argument("--workspace", default="workspace")
    p_pg.add_argument("--json", action="store_true", help="salida JSON")
    p_pg.set_defaults(func=cmd_promptguard)

    p_cap = sub.add_parser(
        "capacidades",
        help="mapa fuente→capacidad→A²S y enrutador con puerta de autorización "
             "(qué aporta cada recurso del catálogo y cuándo usarlo)")
    p_cap.add_argument("--ruta", default="", metavar="OBJETIVO",
                       help="enruta un objetivo a una cadena de recursos "
                            "(ej. 'reconocimiento web', 'reversing binario')")
    p_cap.add_argument("--ctx", default="",
                       help="contexto adicional para el enrutador")
    p_cap.add_argument("--ingesta", action="store_true",
                       help="ingiere READMEs públicos a fichas de conocimiento "
                            "(solo lectura; nunca clona ni ejecuta)")
    p_cap.add_argument("--solo", default="",
                       help="ids separadas por coma (con --ingesta)")
    p_cap.add_argument("--calls", type=int, default=40,
                       help="presupuesto de llamadas a la API de GitHub "
                            "(con --ingesta, default 40)")
    p_cap.add_argument("--refresh", action="store_true",
                       help="re-hace la ingesta aunque esté completada")
    p_cap.add_argument("--mapa", nargs="?", const="capacidades.md", default=None,
                       metavar="RUTA",
                       help="informe completo en Markdown (default: "
                            "capacidades.md; '-' = stdout)")
    p_cap.add_argument("--core", action="store_true",
                       help="lista las 15 fuentes core")
    p_cap.add_argument("--alcance", action="store_true",
                       help="consulta el alcance académico registrado "
                            "(con --perfil lo crea/actualiza)")
    p_cap.add_argument("--perfil", default="",
                       choices=["ctf", "lab", "propio", "universidad"],
                       help="marco académico/ético al registrar el alcance "
                            "o al enrutar (ctf | lab | propio | universidad)")
    p_cap.add_argument("--nota", default="",
                       help="caso concreto del alcance (clase, plataforma, "
                            "infraestructura…); obligatoria al crear")
    p_cap.add_argument("--hosts", action="append", default=None,
                       help="hosts/redes cubiertos por el alcance "
                            "(repetible; default 127.0.0.1,localhost)")
    p_cap.add_argument("--workspace", default="workspace")
    p_cap.add_argument("--json", action="store_true", help="salida JSON")
    p_cap.set_defaults(func=cmd_capacidades)

    p_prev = sub.add_parser(
        "route-preview", help="explica qué proveedor elegiría SORL sin ejecutar una llamada")
    p_prev.add_argument("--workspace", default="workspace")
    p_prev.add_argument("--kind", default="general",
                        choices=["general", "plan", "evaluate", "goal_check", "code", "summarize"])
    p_prev.add_argument("--pool-config", default=None)
    p_prev.add_argument("--pool-strategy", default=None,
                        choices=["round_robin", "cost_first", "speed_first", "multi_objective"])
    p_prev.add_argument("--json", action="store_true")
    p_prev.set_defaults(func=cmd_pool_preview)

    p_map = sub.add_parser("map", help="mapa de reinterpretación operativa de la directiva")
    p_map.set_defaults(func=lambda _a: (print_capability_map(), 0)[1])

    p_protocol = sub.add_parser(
        "protocol",
        help="clasifica una necesidad y muestra las capacidades que Aegis activaría")
    p_protocol.add_argument("request", help="petición u objetivo a clasificar")
    p_protocol.add_argument("--json", action="store_true",
                            help="emite el contrato completo como JSON")
    p_protocol.set_defaults(func=cmd_protocol)

    p_upd = sub.add_parser(
        "update",
        help="auto-actualización en el sitio (git fetch + fast-forward, "
             "sin re-descargar el repo); admite apelativo: a2s update tkm")
    p_upd.add_argument("alias", nargs="?", default=None,
                       help="apelativo opcional del operador (p. ej. 'tkm')")
    p_upd.add_argument("--check", action="store_true",
                       help="solo comprobar si hay novedades (sin tocar nada)")
    p_upd.add_argument("--branch", default=None,
                       help="rama remota a seguir (default: la rama actual)")
    p_upd.add_argument("--force", action="store_true",
                       help="sincroniza a origin descartando lo local "
                            "(reset --hard) — úsalo solo si sabes qué pierdes")
    p_upd.add_argument("--root", default=None,
                       help="ruta del checkout (default: la instalación actual)")
    p_upd.add_argument("--watch", nargs="?", const=600, type=int, default=None,
                       metavar="SEGUNDOS",
                       help="modo guardián: sincroniza solo cada N segundos "
                            "(default 600) hasta Ctrl+C — estilo arena.ai")
    p_upd.set_defaults(func=cmd_update)

    p_grow = sub.add_parser(
        "grow",
        help="crecimiento autónomo: estudia repos públicos y destila fichas "
             "de conocimiento (solo lectura; nunca ejecuta lo estudiado)")
    p_grow.add_argument("--workspace", default="workspace")
    p_grow.add_argument("--cycles", type=int, default=1,
                        help="ciclos de estudio a ejecutar (default 1)")
    p_grow.add_argument("--query", default=None,
                        help="estudiar esta brecha concreta en vez del currículo")
    p_grow.add_argument("--repos", type=int, default=3,
                        help="repos estudiados por ciclo (default 3)")
    p_grow.add_argument("--interval", type=int, default=1800,
                        help="segundos entre ciclos con --forever (default 1800)")
    p_grow.add_argument("--forever", action="store_true",
                        help="crecer sin parar en segundo plano (Ctrl+C para parar)")
    p_grow.set_defaults(func=cmd_grow)

    p_pcb = sub.add_parser(
        "pcb", help="colas de planificación persistentes (PCB): estado y reanudación")
    p_pcb.add_argument("accion", nargs="?", default="status",
                       choices=["status", "resume", "enqueue", "apply", "catalog"])
    p_pcb.add_argument("goal", nargs="?", default="")
    p_pcb.add_argument("--workspace", default="workspace")
    p_pcb.add_argument("--kind", default="mission")
    p_pcb.set_defaults(func=cmd_pcb)

    args = parser.parse_args(argv)
    if getattr(args, "seed", None) is not None:
        import random
        random.seed(args.seed)
    return args.func(args)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", default="workspace", help="espacio de trabajo (default: workspace)")
    p.add_argument("--provider", choices=["auto", "heuristic", "openai", "pool"], default="auto",
                   help="override opcional (default auto: OmniRoute/pool SORL con fallback "
                        "heurístico; normalmente no hace falta indicar proveedor)")
    p.add_argument("--max-iterations", type=int, default=60,
                   help="iteraciones por rebanada de presupuesto (se renueva al replanificar)")
    p.add_argument("--max-rounds", type=int, default=6, help="rondas máximas de replanificación")
    p.add_argument("--max-time", type=int, default=900,
                   help="límite duro de tiempo real en segundos (seguridad)")
    p.add_argument("--report", default="informe_a2s.md", help="ruta del informe de ejecución")
    p.add_argument("--unsafe", action="store_true",
                   help="ampliar lista blanca de shell (bajo tu responsabilidad)")
    p.add_argument("--no-network", action="store_true", help="deshabilitar herramientas de red")
    p.add_argument("--no-shell", action="store_true", help="deshabilitar shell")
    p.add_argument("--quiet", action="store_true", help="modo silencioso")
    p.add_argument("--speculative", type=int, default=0,
                   help="nº de planes candidatos evaluados por la red de gobernanza (0 = desactivado)")
    p.add_argument("--max-depth", type=int, default=3,
                   help="profundidad máxima de división fractal")
    p.add_argument("--resume", action="store_true",
                   help="reanuda sobre el estado persistido del workspace (la memoria se conserva)")
    p.add_argument("--ram", action="store_true",
                   help="workspace volátil en RAM (/dev/shm) — nada en disco")
    p.add_argument("--no-sandbox", action="store_true",
                   help="desactivar el sandbox de python_exec (no recomendado)")
    p.add_argument("--allow-host", action="append", default=None,
                   help="permitir solo este host en la red (repetible; vacío = todos)")
    p.add_argument("--evolve", type=int, default=0,
                   help="generaciones de neuroevolución al finalizar la misión")
    p.add_argument("--notify", action="append", default=None, metavar="DESTINO",
                   help="notificar al terminar (repetible): webhook:URL, file:ruta, print:")
    p.add_argument("--seed", type=int, default=None,
                   help="semilla global de aleatoriedad (jitter/fanout reproducibles)")
    p.add_argument("--pool-config", default=None,
                   help="ruta del JSON del pool SORL (con --provider pool)")
    p.add_argument("--pool-strategy", default=None,
                   help="estrategia del pool SORL: round_robin, cost_first, "
                        "speed_first o multi_objective")


if __name__ == "__main__":
    sys.exit(main())
