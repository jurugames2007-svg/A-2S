#!/usr/bin/env python3
"""Guardián de pureza: falla si a2s/ importa algo fuera de stdlib + paquete.

Criterios 12/133 del roadmap: cero dependencias como contrato ejecutable.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAQUETE = "a2s"

try:
    STDLIB = set(sys.stdlib_module_names)          # Python >= 3.10
except AttributeError:                             # 3.9
    STDLIB = set("""abc argparse ast asyncio atexit base64 binascii bisect builtins
    bz2 calendar cmath collections concurrent contextlib copy copylib copyreg cProfile
    csv ctypes dataclasses datetime decimal difflib dis email enum errno faulthandler
    filecmp fileinput fnmatch fractions ftplib functools gc getpass gettext glob gzip
    hashlib heapq hmac html http imaplib importlib inspect io ipaddress itertools json
    keyword linecache locale logging lzma marshal math mimetypes mmap multiprocessing
    netrc numbers operator os pathlib pdb pickle pickletools platform plistlib poplib
    posixpath pprint profile pstats pty pwd py_compile pyclbr queue quopri random re
    readline reprlib resource runpy sched secrets select selectors shelve shlex shutil
    signal site socket socketserver sqlite3 ssl stat statistics string stringprep
    struct subprocess symtable sys sysconfig tarfile tempfile termios textwrap threading
    time timeit tkinter token tokenize trace traceback tracemalloc tty types typing
    unicodedata unittest urllib uuid venv warnings wave weakref webbrowser wsgiref xml
    xmlrpc zipfile zlib zoneinfo""".split())


def imports_de(path: str) -> list[str]:
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append(node.module.split(".")[0])
    return out


def main() -> int:
    violaciones = []
    for name in sorted(os.listdir(os.path.join(ROOT, PAQUETE))):
        if not name.endswith(".py"):
            continue
        path = os.path.join(ROOT, PAQUETE, name)
        for mod in imports_de(path):
            if mod == PAQUETE or mod.startswith("."):
                continue
            if mod not in STDLIB:
                violaciones.append(f"{PAQUETE}/{name}: import externo '{mod}'")
    if violaciones:
        print("✗ PUREZA ROTA (dependencias externas prohibidas en runtime):")
        for v in violaciones:
            print(f"  - {v}")
        return 1
    print(f"✔ pureza stdlib: {PAQUETE}/ sin dependencias externas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
