"""Interfaz de línea de comandos de A²S."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__
from .config import Config
from .directiva import print_capability_map, scope_note
from .goals import (DEMO_GOAL, build_demo_step_verifiers,
                    forensic_report_goal_verifier, prepare_demo_workspace)
from .loop import AgentLoop, run_goal
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


def cmd_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    if args.resume:
        from .ledger import Ledger
        led = Ledger(os.path.join(os.path.abspath(config.workspace), ".a2s"))
        ok, msg, n = led.verify()
        print(f"[A²S] Reanudando sobre estado previo: {msg} ({n} entradas) — "
              "el workspace y la memoria se conservan.\n")
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
    server = DashboardServer(port=args.port, workspace=args.workspace,
                             auto_demo=not args.no_autodemo, public=args.public,
                             require_auth=args.auth)
    server.serve_forever()
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
        shutil.copytree(source, os.path.join(stage, "a2s"))
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
    if os.environ.get("OPENAI_API_KEY"):
        print("  LLM externo:   OPENAI_API_KEY detectada → se usará API externa")
        base = os.environ.get("A2S_LLM_BASE_URL", "https://api.openai.com/v1")
        print(f"                base_url: {base}")
    else:
        print("  LLM externo:   sin OPENAI_API_KEY → núcleo heurístico determinista")
    try:
        socket.create_connection(("duckduckgo.com", 443), timeout=5).close()
        print("  Red externa:   disponible (búsqueda web y fetch habilitados)")
    except OSError:
        print("  Red externa:   NO disponible (las herramientas de red fallarán y el loop las reparametrizará)")
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

    p_dash = sub.add_parser("dashboard", help="panel de control web en vivo")
    p_dash.add_argument("--port", type=int, default=8000)
    p_dash.add_argument("--workspace", default="workspace")
    p_dash.add_argument("--public", action="store_true",
                        help="escuchar en 0.0.0.0 (⚠ cualquiera en la red puede lanzar misiones)")
    p_dash.add_argument("--auth", action="store_true",
                        help="exigir token de acceso (genéralo con: a2s token)")
    p_dash.add_argument("--no-autodemo", action="store_true",
                        help="no lanzar la misión demo automáticamente")
    p_dash.set_defaults(func=cmd_dashboard)

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

    p_map = sub.add_parser("map", help="mapa de reinterpretación operativa de la directiva")
    p_map.set_defaults(func=lambda _a: (print_capability_map(), 0)[1])

    args = parser.parse_args(argv)
    return args.func(args)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", default="workspace", help="espacio de trabajo (default: workspace)")
    p.add_argument("--provider", choices=["auto", "heuristic", "openai"], default="auto",
                   help="motor de razonamiento (auto: OpenAI si hay clave, si no heurístico)")
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


if __name__ == "__main__":
    sys.exit(main())
