"""SecOps asistido (v1.27): scope criptográfico, simulación, ejecución
defensiva local con alcance y auditoría en el ledger."""

import hashlib
import http.server
import json
import os
import socketserver
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from a2s.cli import main
from a2s.ledger import Ledger
from a2s.secops import (analizar_local, crear_scope, ejecutar, estado_scope,
                         ejecutar_nuclei, ejecutar_trivy, plan_para,
                         recon_http, verificar_scope)
from a2s.capacidades import seleccionar


class TestScope(unittest.TestCase):
    def test_crear_y_verificar_alcance(self):
        with tempfile.TemporaryDirectory() as ws:
            data = crear_scope(ws, ["127.0.0.1", "10.0.0.0/24"],
                               ["recon", "scan", "analizar"],
                               firma="operador@lab.local")
            self.assertEqual(data["signed_by"], "operador@lab.local")
            estado = estado_scope(ws)
            self.assertTrue(estado["valido"])
            ok = verificar_scope(ws, "127.0.0.1:8080", "recon")
            self.assertTrue(ok["ok"])
            ok = verificar_scope(ws, "10.0.0.42", "scan")
            self.assertTrue(ok["ok"])
            # fuera de la red autorizada
            ok = verificar_scope(ws, "192.168.1.10", "recon")
            self.assertFalse(ok["ok"])
            self.assertIn("fuera del alcance", ok["motivo"])
            # acción no incluida (alcance renovado solo con recon)
            crear_scope(ws, ["127.0.0.1"], ["recon"], firma="x")
            ok = verificar_scope(ws, "127.0.0.1", "scan")
            self.assertFalse(ok["ok"])
            self.assertIn("fuera del alcance", ok["motivo"])

    def test_rechaza_acciones_del_vocabulario_cerrado(self):
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(ValueError) as ctx:
                crear_scope(ws, ["127.0.0.1"], ["exploit", "post-exploit"],
                            firma="x")
            self.assertIn("vocabulario cerrado", str(ctx.exception))

    def test_manipulacion_del_token_rompe_la_firma(self):
        with tempfile.TemporaryDirectory() as ws:
            crear_scope(ws, ["127.0.0.1"], ["recon"], firma="x")
            path = os.path.join(ws, ".a2s", "scope.jwt")
            with open(path, encoding="utf-8") as fh:
                token = json.load(fh)
            # un byte cambiado invalida la firma HMAC
            token["payload"] = token["payload"][:-1] + ("A" if
                                                        token["payload"][-1] != "A" else "B")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(token, fh)
            estado = estado_scope(ws)
            self.assertFalse(estado["valido"])
            self.assertIn("sin scope.jwt válido", estado["motivo"])

    def test_expira_el_alcance(self):
        with tempfile.TemporaryDirectory() as ws:
            vencido = (datetime.now(timezone.utc) - timedelta(days=1)
                       ).strftime("%Y-%m-%dT%H:%M:%SZ")
            crear_scope(ws, ["127.0.0.1"], ["recon"],
                        expires=vencido, firma="x")
            estado = estado_scope(ws)
            self.assertFalse(estado["valido"])
            self.assertIn("vencido", estado["motivo"])
            ok = verificar_scope(ws, "127.0.0.1", "recon")
            self.assertFalse(ok["ok"])

    def test_crear_exige_firma_y_targets(self):
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(ValueError):
                crear_scope(ws, ["127.0.0.1"], ["recon"])
            with self.assertRaises(ValueError):
                crear_scope(ws, [], ["recon"], firma="x")


class TestSimulacion(unittest.TestCase):
    def test_simulacion_no_toca_red_y_cubre_la_cadena(self):
        with tempfile.TemporaryDirectory() as ws:
            report = ejecutar("reconocimiento web", modo="simulacion",
                              workspace=ws, targets=["127.0.0.1"])
            self.assertEqual(report["modo"], "simulacion")
            self.assertFalse(report["ejecutado"])
            tipos = {p["tipo"] for p in report["pasos"]}
            self.assertIn("recon", tipos)
            self.assertIn("scan", tipos)
            for paso in report["pasos"]:
                self.assertEqual(paso["estado"], "simulado")
                self.assertFalse(os.path.isfile(
                    os.path.join(ws, ".a2s", "secops")))

    def test_metasploit_y_sqlmap_son_operador_nunca_motor(self):
        plan = plan_para("explotar con metasploit sqlmap")
        for paso in plan:
            self.assertIn(paso["tipo"], ("operador", "preparar"))
            self.assertIsNone(paso["accion"])
            self.assertIn(paso["id"], ("sqlmap", "metasploit"))


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.end_headers()
        self.wfile.write(b"<html><body>lab</body></html>")

    def log_message(self, *args):  # silencio
        pass


class TestAsistido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_sin_alcance_queda_denegado_y_auditado(self):
        with tempfile.TemporaryDirectory() as ws:
            report = ejecutar("reconocimiento web", modo="asistido",
                              workspace=ws, targets=[f"127.0.0.1:{self.port}"],
                              confirm=True)
            self.assertTrue(report["ejecutado"])
            denegados = [p for p in report["pasos"] if p["estado"] == "denegado"]
            self.assertTrue(denegados)
            for p in denegados:
                self.assertIn("sin scope.jwt", p["motivo"])
            entradas = Ledger(os.path.join(ws, ".a2s")).entries()
            eventos = [e["event"] for e in entradas]
            self.assertIn("secops.denegado", eventos)
            self.assertTrue(os.path.isfile(
                os.path.join(ws, ".a2s", "secops", report["run_id"],
                             "informe.md")))

    def test_recon_sobre_servidor_local_del_lab(self):
        with tempfile.TemporaryDirectory() as ws:
            crear_scope(ws, ["127.0.0.1"], ["recon"], firma="lab")
            report = ejecutar("reconocimiento web", modo="asistido",
                              workspace=ws,
                              targets=[f"http://127.0.0.1:{self.port}"],
                              confirm=True)
            ok_steps = [p for p in report["pasos"] if p["estado"] == "ok"]
            self.assertTrue(ok_steps)
            recon = ok_steps[0]["reporte"]
            self.assertEqual(recon["status"], 200)
            self.assertTrue(recon["security_headers"]["Content-Security-Policy"])
            entradas = Ledger(os.path.join(ws, ".a2s")).entries()
            self.assertIn("secops.ejecucion", [e["event"] for e in entradas])

    def test_scan_sin_confirm_no_ejecuta(self):
        with tempfile.TemporaryDirectory() as ws:
            crear_scope(ws, ["127.0.0.1"], ["recon", "scan"], firma="lab")
            report = ejecutar("reconocimiento web", modo="asistido",
                              workspace=ws, targets=[f"127.0.0.1:{self.port}"],
                              confirm=False)
            omitidos = [p for p in report["pasos"] if p["estado"] == "omitido"]
            self.assertTrue(omitidos)
            for p in omitidos:
                if p["tipo"] in ("recon", "scan"):
                    self.assertIn("--confirm", p["motivo"])


class TestAnalizar(unittest.TestCase):
    def test_escaneo_local_informa_la_frontera_de_sandbox(self):
        from unittest import mock
        fake = {"stdout": "", "stderr": "", "returncode": 0,
                "timed_out": False, "sandbox_level": 1,
                "sandbox": "rlimits"}
        with mock.patch("a2s.secops.shutil.which", return_value="scanner"), \
             mock.patch("a2s.secops._run_scanner", return_value=fake) as run:
            out = ejecutar_nuclei(["127.0.0.1"], workspace="lab")
            run.assert_called_once()
            self.assertEqual(out["sandbox"], "rlimits")

    def test_trivy_usa_la_frontera_para_ruta_local(self):
        from unittest import mock
        fake = {"stdout": '{"Results": []}', "stderr": "", "returncode": 0,
                "timed_out": False, "sandbox_level": 1,
                "sandbox": "rlimits"}
        with tempfile.TemporaryDirectory() as ws:
            ruta = os.path.join(ws, "artifact.txt")
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                fh.write("artifact")
            with mock.patch("a2s.secops.shutil.which", return_value="trivy"), \
                 mock.patch("a2s.secops._run_scanner", return_value=fake) as run:
                out = ejecutar_trivy("artifact.txt", workspace=ws)
                self.assertEqual(out["kind"], "fs")
                self.assertEqual(out["sandbox"], "rlimits")
                self.assertEqual(run.call_args.args[1], ws)

    def test_analisis_local_con_hash_y_strings(self):
        with tempfile.TemporaryDirectory() as ws:
            ruta = os.path.join(ws, "muestra.txt")
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                fh.write("A2S sample artifact\n" * 10)
            out = analizar_local(ws, "muestra.txt", ghidra=False)
            self.assertEqual(len(out["sha256"]), 64)
            self.assertEqual(out["sha256"], hashlib.sha256(
                ("A2S sample artifact\n" * 10).encode()).hexdigest())
            self.assertIn("text", out["magic"].lower())
            self.assertGreater(out["strings_total"], 0)
            self.assertFalse(out["ghidra"]["ok"])

    def test_ruta_fuera_del_workspace_es_rechazada(self):
        with tempfile.TemporaryDirectory() as ws:
            with self.assertRaises(PermissionError):
                analizar_local(ws, "/etc/passwd", ghidra=False)


class TestCLI(unittest.TestCase):
    def test_cli_scope_y_simulacion(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as ws:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["secops", "scope-create", "--targets",
                             "127.0.0.1,10.0.0.0/24", "--acciones",
                             "recon,scan,analizar", "--firma", "clase",
                             "--workspace", ws])
            self.assertEqual(code, 0)
            self.assertIn("firmado", out.getvalue())
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                code = main(["secops", "scope-status", "--workspace", ws])
            self.assertEqual(code, 0)
            self.assertIn("VÁLIDO", out2.getvalue())
            out3 = io.StringIO()
            with contextlib.redirect_stdout(out3):
                code = main(["secops", "ejecutar", "reconocimiento web",
                             "--modo", "simulacion", "--targets", "127.0.0.1",
                             "--workspace", ws])
            self.assertEqual(code, 0)
            self.assertIn("simulación", out3.getvalue())


if __name__ == "__main__":
    unittest.main()
