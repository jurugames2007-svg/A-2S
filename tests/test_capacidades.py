"""Capa de capacidades (v1.26): cobertura 65/65, enrutador con puerta de
autorización, ingesta de READMEs a fichas y CLI."""

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest

from a2s.capacidades import (DOMINIOS, DOMINIO_NOMBRE, PERFILES, REQ_NOMBRE,
                             USO_NOMBRE, alcance_info, buscar_capacidad,
                             core_ids, crear_alcance, estado_ingesta, ingesta,
                             mapa_markdown, puerta_autorizacion, resumen,
                             resolver, seleccionar, todas)
from a2s.cli import main
from a2s.learner import GitHubClient, load_cards
from a2s.recursos import ENTRADAS, api_snapshot, validar

META = {
    "full_name": "org/repo", "description": "Herramienta de análisis",
    "stargazers_count": 100, "language": "Python",
    "license": {"spdx_id": "MIT"}, "updated_at": "2026-01-01T00:00:00Z",
    "archived": False, "html_url": "https://github.com/org/repo",
}
README = ("# Repo\n\nHerramienta de análisis de artefactos propios. "
          "Instala con pip. Corre en modo CLI. Documenta los resultados. "
          "No requiere red en el análisis básico.\n")


README_REVISAR = ("# Repo\n\nUsa credenciales y api_key para firmar peticiones. "
                  "El token de acceso se guarda en variable de entorno. "
                  "El resto es documentación de análisis.\n")


def _gh_fake(calls=None, readme=None):
    state = {"n": 0}
    body = (readme or README).encode()

    def transport(url, headers):
        state["n"] += 1
        if "/repos/" in url and "/readme" in url:
            return 200, {}, body
        if "/repos/" in url:
            return 200, {}, json.dumps(META).encode()
        return 404, {}, b"{}"

    gh = GitHubClient(token="fake", transport=transport)
    if calls is not None:
        calls.append(state)
    return gh


class TestCobertura(unittest.TestCase):
    def test_catalogo_completo_sin_links_rotos_estructurales(self):
        # 65 entradas: las 65 URLs del operador (incluye el espejo de
        # Anthropic, Worm-GPT con repo real y gmail-account-creator).
        self.assertGreaterEqual(len(ENTRADAS), 65)
        self.assertEqual(validar(), [])

    def test_todas_las_entradas_tienen_capacidad_resuelta(self):
        caps = todas()
        self.assertEqual(len(caps), len(ENTRADAS))
        by_id = {c.id: c for c in caps}
        for e in ENTRADAS:
            cap = by_id[e["id"]]
            self.assertEqual(cap.id, e["id"])
            self.assertTrue(cap.capacidad.strip())
            self.assertIn(cap.dominio, DOMINIOS)
            self.assertIn(cap.uso, USO_NOMBRE)
            self.assertTrue(cap.receta, f"{cap.id} sin receta")
            self.assertTrue(cap.etico.strip(), f"{cap.id} sin nota ética")
            for req in cap.requiere:
                self.assertIn(req, REQ_NOMBRE)

    def test_resolver_desconocido_lanza_keyerror(self):
        with self.assertRaises(KeyError):
            resolver("no-existe")

    def test_core_son_15_y_del_catalogo(self):
        core = core_ids()
        self.assertEqual(len(core), 15)
        ids = {e["id"] for e in ENTRADAS}
        self.assertTrue(set(core) <= ids)
        self.assertIn("web-check", core)
        self.assertIn("vault", core)

    def test_resumen_cubre_dominios_y_usos(self):
        data = resumen()
        self.assertEqual(data["total"], len(ENTRADAS))
        self.assertEqual(sum(d["count"] for d in data["dominios"]), len(ENTRADAS))
        self.assertEqual(sum(u["count"] for u in data["usos"]), len(ENTRADAS))
        self.assertGreater(data["con_puerta"], 0)

    def test_api_recursos_expone_resumen_de_capacidades(self):
        snap = api_snapshot()
        self.assertEqual(snap["capacidades"]["total"], len(ENTRADAS))


class TestEnrutador(unittest.TestCase):
    def test_reconocimiento_web_con_puerta(self):
        plan = seleccionar("reconocimiento web")
        ids = {p["id"] for p in plan["pasos"]}
        self.assertIn("web-check", ids)
        self.assertIn("osint4all", ids)
        self.assertFalse(plan["autorizacion"]["valida"])
        self.assertIn("nuclei", {b["id"] for b in plan["bloqueados"]})
        self.assertNotIn("nuclei", ids)
        self.assertIn("defensiva", plan["sugerencia_defensiva"].lower())

    def test_alcance_academico_por_perfil_y_hosts(self):
        self.assertEqual(set(PERFILES), {"ctf", "lab", "propio", "universidad"})
        with tempfile.TemporaryDirectory() as ws:
            data = crear_alcance(ws, "ctf",
                                 nota="clase HTB — alcance de la plataforma",
                                 hosts=("127.0.0.1", "localhost"))
            self.assertEqual(data["perfil"], "ctf")
            self.assertTrue(data["autorizado"])
            info = alcance_info(ws)
            self.assertTrue(info["valido"])
            # objetivo sin marca de CTF/lab y sin host: el perfil lo cubre
            gate = puerta_autorizacion("reconocimiento de ejemplo.com", ws,
                                       perfil="ctf")
            self.assertTrue(gate["valida"])

    def test_alcance_exige_nota_y_perfil_valido(self):
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(ValueError):
                crear_alcance(ws, "ctf", nota="")
            with self.assertRaises(ValueError):
                crear_alcance(ws, "inexistente", nota="x")

    def test_reconocimiento_con_alcance_firmado_libera_ruta_ofensiva(self):
        with tempfile.TemporaryDirectory() as ws:
            crear_alcance(ws, "propio", nota="red-team sobre infraestructura propia",
                          hosts=("*",))
            gate = puerta_autorizacion("reconocimiento de ejemplo.com", ws)
            self.assertTrue(gate["valida"])
            plan = seleccionar("reconocimiento de ejemplo.com", workspace=ws)
            ids = {p["id"] for p in plan["pasos"]}
            self.assertIn("nuclei", ids)
            self.assertFalse(any(b["id"] == "nuclei" for b in plan["bloqueados"]))

    def test_perfil_sin_alcance_registrado_no_abre_la_puerta(self):
        with tempfile.TemporaryDirectory() as ws:
            plan = seleccionar("reconocimiento web", workspace=ws, perfil="ctf")
            self.assertIn("nuclei", {b["id"] for b in plan["bloqueados"]})
            info = plan["autorizacion"]
            self.assertFalse(info["valida"])
            self.assertFalse(info["existe"])

    def test_reversing_binario_encadena_pipeline(self):
        plan = seleccionar("reversing binario")
        ids = {p["id"] for p in plan["pasos"]}
        self.assertTrue({"ghidra", "imhex", "cyberchef"} <= ids)

    def test_prompt_engineering_usa_fuentes_cognitivas(self):
        plan = seleccionar("prompt engineering")
        ids = {p["id"] for p in plan["pasos"]}
        self.assertIn("claude-courses", ids)
        self.assertIn("system-prompts-leaks", ids)

    def test_vpn_autoalojada(self):
        plan = seleccionar("vpn propia")
        ids = {p["id"] for p in plan["pasos"]}
        self.assertTrue({"algo", "setup-ipsec-vpn"} & ids)

    def test_ofensiva_queda_retenida(self):
        plan = seleccionar("explotar con metasploit sqlmap")
        retenidos = {b["id"] for b in plan["bloqueados"]}
        self.assertTrue({"metasploit", "sqlmap"} <= retenidos)
        self.assertNotIn("metasploit", {p["id"] for p in plan["pasos"]})

    def test_zona_gris_solo_referencia(self):
        plan = seleccionar("streaming flixer")
        retenidos = {b["id"] for b in plan["bloqueados"]}
        self.assertIn("flixer", retenidos)
        self.assertNotIn("flixer", {p["id"] for p in plan["pasos"]})

    def test_busqueda_bm25_de_capacidades(self):
        rows = buscar_capacidad("análisis de binarios")
        self.assertTrue(rows)
        self.assertIn("score", rows[0])

    def test_objetivo_vacio_es_rechazado(self):
        with self.assertRaises(ValueError):
            seleccionar("   ")


class TestIngesta(unittest.TestCase):
    def test_ingesta_readmes_a_fichas_y_reanudable(self):
        s1, s2, s3 = [], [], []
        with tempfile.TemporaryDirectory() as ws:
            report = ingesta(ws, gh=_gh_fake(s1), solo="web-check,claude-courses")
            self.assertEqual(report["ok"], 1)
            self.assertEqual(report["referencia"], 1)
            cards = load_cards(ws)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].id, "cap-web-check")
            self.assertEqual(cards[0].license, "MIT")
            state = estado_ingesta(ws)
            self.assertEqual(state["ok"], 1)
            self.assertEqual(s1[0]["n"], 2)  # metadata + README
            # segunda pasada: no re-descarga lo ya hecho (reanudable)
            report2 = ingesta(ws, gh=_gh_fake(s2), solo="web-check,claude-courses")
            self.assertEqual(report2["ok"], 1)
            self.assertEqual(s2[0]["n"], 0)
            # refresh re-descarga
            report3 = ingesta(ws, gh=_gh_fake(s3), solo="web-check", refresh=True)
            self.assertEqual(report3["ok"], 1)
            self.assertEqual(s3[0]["n"], 2)

    def test_ingesta_no_ejecuta_codigo_y_registra_estado(self):
        with tempfile.TemporaryDirectory() as ws:
            report = ingesta(ws, gh=_gh_fake(), solo="ghidra,cyberchef")
            self.assertEqual(report["ok"], 2)
            manifest = os.path.join(ws, ".a2s", "capacidades", "ingesta.json")
            self.assertTrue(os.path.isfile(manifest))
            with open(manifest, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(len(data["estados"]), 2)

    def test_readme_con_patron_prohibido_queda_para_revision(self):
        with tempfile.TemporaryDirectory() as ws:
            report = ingesta(ws, gh=_gh_fake(readme=README_REVISAR),
                             solo="ghidra")
            self.assertEqual(report["revisar"], 1)
            self.assertEqual(report["ok"], 0)
            # la ficha se conserva (material público) pero marcada para revisar
            cards = load_cards(ws)
            self.assertEqual(len(cards), 1)
            self.assertIn("credenciales", cards[0].summary.lower() or "")
            state = estado_ingesta(ws)
            self.assertEqual(state["revisar"], 1)


class TestMapaYCLI(unittest.TestCase):
    def test_mapa_markdown_es_completo(self):
        md = mapa_markdown()
        self.assertIn("# Mapa de capacidades", md)
        for d in DOMINIOS:
            self.assertIn(DOMINIO_NOMBRE[d], md)
        for cap in todas():
            self.assertIn(cap.id, md)
        self.assertGreater(md.count("|"), 40)

    def test_cli_resumen_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["capacidades", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["total"], len(ENTRADAS))

    def test_cli_ruta_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["capacidades", "--ruta", "reconocimiento web", "--json"])
        self.assertEqual(code, 0)
        plan = json.loads(out.getvalue())
        self.assertIn("pasos", plan)
        self.assertIn("bloqueados", plan)

    def test_cli_core(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["capacidades", "--core"])
        self.assertEqual(code, 0)
        self.assertIn("web-check", out.getvalue())

    def test_cli_alcance_y_ruta_perfil_academico(self):
        with tempfile.TemporaryDirectory() as ws:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["capacidades", "--alcance", "--perfil", "lab",
                             "--nota", "DVWA en local (clase)", "--workspace", ws])
            self.assertEqual(code, 0)
            self.assertIn("registrado", out.getvalue())
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                code = main(["capacidades", "--alcance", "--json", "--workspace", ws])
            self.assertEqual(code, 0)
            data = json.loads(out2.getvalue())
            self.assertTrue(data["valido"])
            self.assertEqual(data["perfil"], "lab")
            # el perfil registrado abre la ruta ofensiva al enrutar con él
            out3 = io.StringIO()
            with contextlib.redirect_stdout(out3):
                code = main(["capacidades", "--ruta", "reconocimiento web",
                             "--perfil", "lab", "--json", "--workspace", ws])
            self.assertEqual(code, 0)
            plan = json.loads(out3.getvalue())
            self.assertIn("nuclei", {p["id"] for p in plan["pasos"]})
            self.assertTrue(plan["autorizacion"]["valida"])


if __name__ == "__main__":
    unittest.main()
