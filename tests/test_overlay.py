"""Testes para output/overlay.py — sem display real."""

import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── _has_display ───────────────────────────────────────────────────────

class TestHasDisplay:
    def setup_method(self):
        from output.overlay import _has_display
        self._has = _has_display

    def _clean_env(self, monkeypatch):
        """Remove todas as variáveis de ambiente relacionadas a display."""
        for var in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM",
                    "CI", "GITHUB_ACTIONS", "SESSIONNAME",
                    "XDG_RUNTIME_DIR", "JENKINS_HOME"):
            monkeypatch.delenv(var, raising=False)

    def _linux_env(self, monkeypatch):
        """Exercita a decisão de Linux mesmo no runner Windows."""
        self._clean_env(monkeypatch)
        monkeypatch.setattr("output.overlay.platform.system", lambda: "Linux")
        monkeypatch.setattr(os, "getuid", lambda: 1000, raising=False)

    def test_offscreen_platform_returns_false(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
        assert self._has() is False

    def test_ci_env_returns_false(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("CI", "true")
        assert self._has() is False

    def test_github_actions_returns_false(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert self._has() is False

    def test_no_display_vars_returns_false(self, monkeypatch):
        self._clean_env(monkeypatch)
        assert self._has() is False

    def test_display_without_lock_returns_false(self, monkeypatch, tmp_path):
        """DISPLAY=:99 sem /tmp/.X99-lock deve retornar False."""
        self._linux_env(monkeypatch)
        monkeypatch.setenv("DISPLAY", ":99")
        # não cria o arquivo de lock → deve retornar False
        with patch("os.path.exists", return_value=False):
            assert self._has() is False

    def test_display_with_lock_returns_true(self, monkeypatch):
        """DISPLAY=:0 com /tmp/.X0-lock existindo deve retornar True."""
        self._linux_env(monkeypatch)
        monkeypatch.setenv("DISPLAY", ":0")
        with patch("os.path.exists", return_value=True):
            result = self._has()
        assert result is True

    def test_wayland_with_existing_socket_returns_true(self, monkeypatch, tmp_path):
        """WAYLAND_DISPLAY com socket existente deve retornar True."""
        self._linux_env(monkeypatch)
        socket_file = tmp_path / "wayland-0"
        socket_file.touch()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert self._has() is True

    def test_wayland_without_socket_returns_false(self, monkeypatch, tmp_path):
        """WAYLAND_DISPLAY sem socket existente deve retornar False."""
        self._linux_env(monkeypatch)
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        # socket NÃO existe
        assert self._has() is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_with_session_returns_true(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("SESSIONNAME", "Console")
        assert self._has() is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_windows_ci_returns_false(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("CI", "true")
        assert self._has() is False


# ── init sem display ──────────────────────────────────────────────────

class TestInitNoDisplay:
    def test_init_without_display_does_not_raise(self, monkeypatch, tmp_path):
        """init() sem display disponível deve retornar sem erro e sem criar instância."""
        import yaml
        from core.config import Config
        data = {"overlay": {"enabled": True, "position": "top-right",
                            "duration_ms": 4000, "opacity": 0.92}}
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(data), encoding="utf-8")
        config = Config(str(cfg_path))

        with patch("output.overlay._has_display", return_value=False):
            import output.overlay as ov
            ov._instance = None  # garante estado limpo
            ov.init(config)
            assert ov._instance is None


# ── Interface pública thread-safe ──────────────────────────────────────

class TestPublicInterface:
    def setup_method(self):
        import output.overlay as ov
        ov._instance = None  # sem instância — funções devem silenciosamente não fazer nada

    def test_show_message_no_instance(self):
        from output.overlay import show_message
        show_message("teste")  # não deve lançar exceção

    def test_set_state_no_instance(self):
        from output.overlay import set_state
        set_state("listening")  # não deve lançar exceção

    def test_show_no_instance_returns_str(self):
        from output.overlay import show
        result = show()
        assert isinstance(result, str)

    def test_hide_no_instance_returns_str(self):
        from output.overlay import hide
        result = hide()
        assert isinstance(result, str)

    def test_toggle_no_instance_returns_str(self):
        from output.overlay import toggle
        result = toggle()
        assert isinstance(result, str)

    def test_set_orchestrator_stores_reference(self):
        import output.overlay as ov
        sentinel = object()
        ov.set_orchestrator(sentinel)
        assert ov._orchestrator is sentinel
        ov.set_orchestrator(None)  # não deixa estado vazando entre testes
