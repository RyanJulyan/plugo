from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_VENV_HOME = Path(
    os.environ.get("PLUGO_VENV_HOME", os.environ.get("VENV_HOME", "./.plugo/venvs"))
)


@dataclass
class VenvInfo:
    key: str
    path: Path
    python: Path


def build_venv_key(
    plugin_name: str,
    version: str | None,
    requirements: List[str],
) -> str:
    """
    Build a stable, human-readable key so different versions/dep sets get different venvs.

    Key includes:
    - plugin_name (sanitized)
    - version (if provided)
    - hash over normalized requirements

    Format:
        <plugin_name>[-v<version>]-<hash>

    This means:
    - Same plugin + same version + same reqs => same venv
    - Change version or reqs => different venv

    - plugin_name is sanitized for filesystem use.
    - version is included visibly when provided (also sanitized).
    - hash is derived from (version, sorted(requirements)) so changes create new envs.
    """
    norm_reqs = [r.strip() for r in requirements if r and r.strip()]

    sig = {
        "version": (version or "").strip(),
        "requirements": sorted(norm_reqs),
    }
    digest = hashlib.sha1(json.dumps(sig, sort_keys=True).encode("utf-8")).hexdigest()[
        :12
    ]

    safe_name = (
        plugin_name.replace(os.sep, "_").replace(":", "_").replace(" ", "_").strip("_")
        or "plugin"
    )

    ver = (version or "").strip()
    if ver:
        safe_ver = (
            ver.replace(os.sep, "_")
            .replace(":", "_")
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .strip("_")
        )
        # Prefix with v for clarity, but don't duplicate if user already uses 'v'
        if not safe_ver.startswith("v"):
            safe_ver = f"v{safe_ver}"
        key = f"{safe_name}-{safe_ver}-{digest}"
    else:
        key = f"{safe_name}-{digest}"

    return key


class VenvManager:
    """
    Minimal per-plugin venv manager.

    - Venvs live under `base`
    - `ensure(key, requirements)` creates/reuses a venv, installs deps
    - `add_site_packages_to_sys_path(venv)` exposes that venv's packages to current process
    """

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = (base or DEFAULT_VENV_HOME).expanduser()
        self.base.mkdir(parents=True, exist_ok=True)

    def _venv_dir(self, key: str) -> Path:
        # key should already be sanitized by build_venv_key, but harden anyway
        safe_key = (
            key.replace(os.sep, "_").replace(":", "_").replace(" ", "_").strip("_")
        )
        return self.base / safe_key

    def _python_path_for(self, venv_dir: Path) -> Path:
        if os.name == "nt":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def ensure(self, key: str, requirements: Iterable[str]) -> VenvInfo:
        """
        Ensure a venv identified by `key` exists and that `requirements` are installed.

        Returns:
            VenvInfo(key, path, python_path)
        """
        venv_dir = self._venv_dir(key)
        python_bin = self._python_path_for(venv_dir)

        if not python_bin.exists():
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

        reqs: List[str] = [r.strip() for r in requirements if r and r.strip()]
        if reqs:
            subprocess.check_call(
                [
                    str(python_bin),
                    "-m",
                    "pip",
                    "install",
                    "-U",
                    "pip",
                    *reqs,
                ]
            )

        return VenvInfo(key=key, path=venv_dir, python=python_bin)

    def add_site_packages_to_sys_path(self, venv: VenvInfo) -> None:
        """
        Prepend the venv's site-packages directories to sys.path.

        This keeps plugins running in-process while isolating their dependencies
        into their own venvs.
        """
        code = (
            "import site, sys, json, os; "
            "paths = []; "
            "gsp = getattr(site, 'getsitepackages', None); "
            "paths.extend(gsp() if gsp else []); "
            "usp = site.getusersitepackages(); "
            "paths.append(usp); "
            "paths = [p for p in paths if isinstance(p, str) and os.path.isdir(p)]; "
            "print(json.dumps(paths));"
        )
        out = subprocess.check_output(
            [str(venv.python), "-c", code],
            text=True,
        ).strip()

        try:
            paths = json.loads(out)
        except json.JSONDecodeError:
            return

        for p in paths:
            if p and p not in sys.path:
                sys.path.insert(0, p)
