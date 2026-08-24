"""Puente Python del sidecar OmniRoute: degradación y supervisión segura."""

import os
import unittest
from unittest import mock

from a2s.omniroute import OmniRouteWatchdog, ensure_gateway


class TestOmniRouteBridge(unittest.TestCase):
    def test_interruptor_off_no_invoca_node(self):
        with mock.patch.dict(os.environ, {"A2S_OMNIROUTE": "off"}, clear=False), \
                mock.patch("a2s.omniroute.shutil.which") as which:
            result = ensure_gateway()
        self.assertEqual(result["state"], "disabled")
        which.assert_not_called()

    def test_sin_node_degrada_sin_excepcion(self):
        env = dict(os.environ)
        env.pop("A2S_OMNIROUTE", None)
        env.pop("A2S_OMNIROUTE_URL", None)
        env.pop("A2S_OMNIROUTE_MANAGED", None)
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("a2s.omniroute.shutil.which", return_value=None):
            result = ensure_gateway()
        self.assertEqual(result["state"], "unavailable")
        self.assertFalse(result["usable"])

    def test_no_duplica_watchdog_del_launcher_node(self):
        with mock.patch.dict(os.environ,
                             {"A2S_OMNIROUTE_PARENT_WATCHDOG": "1"}, clear=False), \
                mock.patch("a2s.omniroute.threading.Thread") as thread:
            OmniRouteWatchdog().start()
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
