from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def asset_root() -> Path:
    if os.getenv("PACOCA_ASSETS"):
        return Path(os.environ["PACOCA_ASSETS"]).resolve()
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).parent / "assets"
        if external.exists():
            return external
    return bundle_root() / "assets"


def data_root() -> Path:
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return Path(os.getenv("PACOCA_DATA", str(base / "Pacoca"))).resolve()


DEFAULTS = dict(user_name="", assistant_name="Paçoca", voice_enabled=True, voice_speed=1.0,
                speech_device="", microphone_id="", output_id="", wake_enabled=False,
                wake_sensitivity="normal", wake_timeout=20, theme="dark", backend="auto",
                context_size=4096, model_profile="light", cpu_threads=2, idle_seconds=60,
                resource_policy_version=2, game_guard=True, max_steps=8, retention_days=90, onboarding_done=False,
                allowed_roots=[], browser_domains=[], start_with_windows=False,
                alexa_enabled=False, alexa_skill_id="", alexa_user_id="",
                updates_enabled=True, update_install_on_exit=True,
                spotify_device="", application_paths={})


class Settings:
    def __init__(self, directory: Path | None = None):
        self.directory = (directory or data_root()).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.workspace = self.directory / "Workspace"
        self.workspace.mkdir(exist_ok=True)
        self.path = self.directory / "settings.json"
        self.lock = threading.RLock()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            raw = {}
        self.values = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
        if raw.get('resource_policy_version',0)<2:
            # Existing users must receive the safe defaults too, retaining the 8B file.
            self.values.update(model_profile='light',context_size=4096,cpu_threads=2,
                               resource_policy_version=2)

    def get(self, key, default=None):
        with self.lock:
            return self.values.get(key, default)

    def all(self):
        with self.lock:
            return json.loads(json.dumps(self.values))

    def update(self, changes: dict):
        with self.lock:
            self.values.update({k: v for k, v in changes.items() if k in DEFAULTS})
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.values, indent=2, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.path)
        return self.all()

    def roots(self):
        return [self.workspace, *[Path(p).expanduser().resolve() for p in self.get("allowed_roots", [])]]

    def resolve_path(self, value: str, *, must_exist=True) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            if path.parts and path.parts[0].casefold()=='workspace':
                path=Path(*path.parts[1:])
            path = self.workspace / path
        path = path.resolve()
        if not any(path.is_relative_to(root.resolve()) for root in self.roots()):
            raise PermissionError("Essa pasta ainda não foi autorizada. Adicione-a em Conhecimento.")
        if must_exist and not path.exists():
            raise FileNotFoundError("Não encontrei esse arquivo ou pasta.")
        return path
