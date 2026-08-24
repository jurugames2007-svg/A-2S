"""Generador de programas pequeños, locales y auditables (stdlib)."""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from .control import StopToken
from .models import now_iso


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:40] or "programa"


def generate_program(workspace: str, topic: str,
                     stop: Optional[StopToken] = None) -> dict[str, Any]:
    if stop:
        stop.raise_if_set()
    from .config import classify_forbidden
    if reason := classify_forbidden(topic):
        raise PermissionError(reason)
    title = " ".join((topic or "utilidad").split())[:120]
    slug = slugify(title)
    root = os.path.join(os.path.abspath(workspace), "programs", slug)
    os.makedirs(root, exist_ok=True)
    main = (
        f'"""Programa generado por A²S: {title}.\n\n'
        "Stdlib only. No red, no secretos, no privilegios.\n"
        f"Creado: {now_iso()}\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "import argparse\n\n\n"
        "def run(text: str) -> str:\n"
        "    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]\n"
        "    return '\\n'.join(f'{i}. {ln}' for i, ln in enumerate(lines, 1))\n\n\n"
        "def main() -> int:\n"
        "    parser = argparse.ArgumentParser(description=__doc__)\n"
        "    parser.add_argument('text', nargs='?', default='hola mundo')\n"
        "    args = parser.parse_args()\n"
        "    print(run(args.text))\n"
        "    return 0\n\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    test = (
        "import unittest\n"
        f"from programs.{slug.replace('-', '_')}_main import run\n\n"
        "class TestGenerated(unittest.TestCase):\n"
        "    def test_numera(self):\n"
        "        self.assertIn('1. hola', run('hola'))\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    # import path: keep a copy as module-friendly name
    module = os.path.join(root, slug.replace("-", "_") + "_main.py")
    readme = (
        f"# {title}\n\nPrograma local generado por A²S el {now_iso()}.\n\n"
        "```\npython programs/" + slug + "/" + os.path.basename(module) + "\n```\n"
        "\nNo es malware. No pide red. Revísalo antes de ejecutarlo.\n"
    )
    with open(os.path.join(root, "main.py"), "w", encoding="utf-8") as fh:
        fh.write(main)
    with open(module, "w", encoding="utf-8") as fh:
        fh.write(main)
    with open(os.path.join(root, "test_main.py"), "w", encoding="utf-8") as fh:
        fh.write("import unittest\n\n\ndef run(text):\n"
                 "    from pathlib import Path\n"
                 "    ns = {}\n"
                 f"    exec(Path(__file__).with_name('main.py').read_text(encoding='utf-8'), ns)\n"
                 "    return ns['run'](text)\n\n\n"
                 "class TestGenerated(unittest.TestCase):\n"
                 "    def test_numera(self):\n"
                 "        self.assertIn('1. hola', run('hola'))\n")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)
    rel = lambda p: os.path.relpath(p, os.path.abspath(workspace)).replace(os.sep, "/")
    return {
        "status": "program_written", "title": title, "slug": slug,
        "artifacts": [rel(os.path.join(root, "main.py")),
                      rel(os.path.join(root, "test_main.py")),
                      rel(os.path.join(root, "README.md"))],
    }
