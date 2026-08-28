#!/usr/bin/env python3
"""Ingesta segura de repositorios del catálogo A²S.

- NO ejecuta binarios ni instala dependencias.
- Descarga metadatos públicos de GitHub cuando es posible.
- Clona solo si el repositorio no es peligroso o si `--allow-dangerous` está activo.
- Guarda un resumen JSON adaptado para A²S.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib import request


def run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def parse_repo_slug(url: str) -> tuple[str, str] | None:
    cleaned = url.strip().rstrip('/')
    if 'github.com/' not in cleaned.lower():
        return None
    tail = cleaned.split('github.com/', 1)[1]
    parts = [p for p in tail.split('/') if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def fetch_github_metadata(url: str) -> dict:
    slug = parse_repo_slug(url)
    if slug is None:
        return {'source': 'external', 'fetched': False, 'reason': 'not-github'}

    owner, repo = slug
    api_url = f'https://api.github.com/repos/{owner}/{repo}'
    req = request.Request(api_url, headers={'User-Agent': 'A2S-Repo-Ingestor/1.0'})
    try:
        with request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except Exception as exc:
        return {'source': 'github', 'fetched': False, 'reason': str(exc)}

    license_data = payload.get('license')
    return {
        'source': 'github',
        'fetched': True,
        'owner': owner,
        'repo': repo,
        'full_name': payload.get('full_name'),
        'description': payload.get('description'),
        'default_branch': payload.get('default_branch'),
        'stargazers_count': payload.get('stargazers_count', 0),
        'language': payload.get('language'),
        'license': license_data.get('spdx_id') if isinstance(license_data, dict) else license_data,
        'homepage': payload.get('homepage'),
        'html_url': payload.get('html_url'),
        'updated_at': payload.get('updated_at'),
        'archived': bool(payload.get('archived')),
    }


def analyze_repo(path: Path):
    files = [f for f in path.rglob('*') if f.is_file()]
    stats = {
        'file_count': len(files),
        'total_size_bytes': sum(f.stat().st_size for f in files),
        'top_extensions': Counter((f.suffix.lower() or 'noext') for f in files).most_common(10),
        'has_readme': any(f.name.lower().startswith('readme') for f in files),
        'has_license': any('license' in f.name.lower() for f in files),
    }
    lang_map = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.c': 'c', '.cpp': 'cpp',
        '.java': 'java', '.go': 'go', '.rs': 'rust', '.sh': 'sh', '.ps1': 'powershell',
        '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml'
    }
    langs = Counter()
    for f in files:
        key = lang_map.get(f.suffix.lower())
        if key:
            langs[key] += 1
    stats['languages'] = langs.most_common(8)
    return stats


def clone_and_analyze(entry: dict, out_dir: Path, allow_dangerous: bool = False, dry_run: bool = False) -> dict:
    url = entry['url']
    dangerous = bool(entry.get('dangerous', False))
    name = url.rstrip('/').split('/')[-1]
    repo_dir = out_dir / name
    result = {
        'url': url,
        'dangerous': dangerous,
        'cloned': False,
        'analysis': None,
        'error': None,
        'metadata': fetch_github_metadata(url),
    }

    if dangerous and not allow_dangerous:
        result['error'] = 'skipped: dangerous repo requires --allow-dangerous'
        return result
    if dry_run:
        result['error'] = 'dry-run'
        return result

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    cmd = ['git', 'clone', '--depth', '1', url, str(repo_dir)]
    try:
        print(f'Cloning {url} -> {repo_dir}')
        proc = run(cmd)
        if proc.returncode != 0:
            result['error'] = proc.stderr.strip() or proc.stdout.strip() or 'git clone failed'
            return result
        result['cloned'] = True
        result['analysis'] = analyze_repo(repo_dir)
        return result
    except Exception as exc:
        result['error'] = str(exc)
        return result


def main() -> int:
    p = argparse.ArgumentParser(description='Ingesta segura del catálogo de repositorios A²S')
    p.add_argument('--catalog', required=True, help='Ruta al archivo catalog.json')
    p.add_argument('--out', required=True, help='Directorio de salida para resultados y clones')
    p.add_argument('--allow-dangerous', action='store_true', help='Permite clonar repos marcados como peligrosos')
    p.add_argument('--dry-run', action='store_true', help='Sin clonar; solo recibe metadata y plan de trabajo')
    args = p.parse_args()

    catalog_path = Path(args.catalog)
    out_path = Path(args.out)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'No pude leer {catalog_path}: {exc}', file=sys.stderr)
        return 2

    results = []
    for entry in catalog:
        res = clone_and_analyze(entry, out_path, allow_dangerous=args.allow_dangerous, dry_run=args.dry_run)
        results.append(res)
        (out_path / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'Done. {len(results)} repos procesados. Results saved to {out_path / "results.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
