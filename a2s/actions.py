"""Acciones de un clic: el operador no necesita terminal ni saber programar."""

from __future__ import annotations

from typing import Any, Optional

# Catálogo visible. Cada id se dispara desde un botón.
BUTTONS: tuple[dict[str, Any], ...] = (
    {"id": "analyze", "title": "Revisar mis archivos",
     "blurb": "Mira el workspace y escribe un informe claro.",
     "group": "empezar", "mode": "mission",
     "topic": "Analiza el workspace y produce un informe verificable de mejoras."},
    {"id": "organize", "title": "Ordenar archivos",
     "blurb": "Clasifica fotos, documentos y basura. Se puede deshacer.",
     "group": "archivos", "mode": "studio", "kind": "steward",
     "topic": "Ordena el escritorio del workspace y anima el escritorio virtual."},
    {"id": "clean", "title": "Limpiar basura",
     "blurb": "Borra temporales vacíos. No toca contratos ni libros.",
     "group": "archivos", "mode": "studio", "kind": "steward",
     "topic": "Limpieza segura del workspace: solo basura .tmp y vacíos."},
    {"id": "undo", "title": "Deshacer último orden",
     "blurb": "Devuelve los archivos a donde estaban.",
     "group": "archivos", "mode": "undo"},
    {"id": "book", "title": "Escribir un libro",
     "blurb": "Crea un libro original y lo deja en Archivos (PDF).",
     "group": "crear", "mode": "studio", "kind": "book",
     "ask": "¿De qué tema quieres el libro?",
     "topic": "Crea un libro sobre El Principito."},
    {"id": "slides", "title": "Hacer una presentación",
     "blurb": "Diseña diapositivas y muestra el proceso en vivo.",
     "group": "crear", "mode": "studio", "kind": "slides",
     "ask": "¿De qué es la presentación?",
     "topic": "Diseña una presentación sobre A²S y muestra el proceso."},
    {"id": "program", "title": "Crear un programita",
     "blurb": "Escribe un programa sencillo con instrucciones.",
     "group": "crear", "mode": "studio", "kind": "codegen",
     "ask": "¿Qué debe hacer el programa?",
     "topic": "Genera un programa que numere líneas."},
    {"id": "search", "title": "Buscar en internet",
     "blurb": "Encuentra repositorios y páginas por palabra clave.",
     "group": "descubrir", "mode": "search",
     "ask": "¿Qué quieres buscar?",
     "topic": "agentes autónomos"},
    {"id": "research", "title": "Investigar un tema",
     "blurb": "Junta fuentes abiertas y aprende de ellas.",
     "group": "descubrir", "mode": "mission",
     "ask": "¿Qué tema investigo?",
     "topic": "Investiga repositorios recientes y PDF abiertos sobre agentes autónomos."},
    {"id": "jobs", "title": "Ver oportunidades",
     "blurb": "Prepara un brief de empleo o finanzas públicas.",
     "group": "descubrir", "mode": "studio", "kind": "horizon",
     "topic": "Busca empleo: brief de oportunidades públicas."},
    {"id": "resume", "title": "Seguir donde quedó",
     "blurb": "Si se cortó el trabajo, lo retoma solo.",
     "group": "control", "mode": "resume"},
    {"id": "stop", "title": "Detener todo",
     "blurb": "Para la misión y los trabajos en curso.",
     "group": "control", "mode": "stop"},
    {"id": "results", "title": "Ver lo creado",
     "blurb": "Abre la carpeta de archivos, PDFs y presentaciones.",
     "group": "control", "mode": "view", "view": "results"},
    {"id": "status", "title": "¿Qué está haciendo?",
     "blurb": "Estado de las colas y de la misión, en cristiano.",
     "group": "control", "mode": "status"},
)


def catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in BUTTONS]


def get_action(action_id: str) -> Optional[dict[str, Any]]:
    for item in BUTTONS:
        if item["id"] == action_id:
            return dict(item)
    return None


def run_local(workspace: str, action_id: str, topic: str = "") -> dict[str, Any]:
    """Acciones instantáneas (sin hilo). El dashboard encola las demás."""
    spec = get_action(action_id)
    if spec is None:
        return {"ok": False, "error": "acción desconocida"}
    mode = spec["mode"]
    if mode == "undo":
        from .steward import undo_last
        result = undo_last(workspace)
        return {"ok": True, "mode": mode, "result": result,
                "message": f"Deshecho: {result.get('restored', 0)} archivo(s).",
                "view": "results"}
    if mode == "resume":
        from .kernel import Kernel
        kernel = Kernel.open(workspace)
        restored = kernel.resume_all()
        return {"ok": True, "mode": mode, "restored": len(restored),
                "pcb": kernel.snapshot(),
                "message": f"Retomé {len(restored)} trabajo(s) pendiente(s)."}
    if mode == "status":
        from .kernel import Kernel
        snap = Kernel.open(workspace).snapshot()
        return {"ok": True, "mode": mode, "pcb": snap,
                "message": (f"Listo. Colas: {snap['ready']} en espera, "
                            f"{snap['running']} en curso, "
                            f"{snap['parked']} pausados. "
                            f"{snap['applied']} mejoras activas.")}
    if mode == "view":
        return {"ok": True, "mode": mode, "view": spec.get("view") or "results",
                "message": "Abriendo Archivos."}
    topic = (topic or spec.get("topic") or "").strip()
    return {"ok": True, "mode": mode, "queued": True, "spec": spec,
            "topic": topic, "kind": spec.get("kind") or "",
            "message": spec["title"]}
