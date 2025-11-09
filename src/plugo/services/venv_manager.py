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
    Build a stable key so that different versions / dep sets get different venvs.

    Key includes:
    - plugin_name (sanitized)
    - version (if provided)
    - hash over normalized requirements

    This means:
    - Same plugin + same version + same reqs => same venv
    - Change version or reqs => different venv
    """
    norm_reqs = [r.strip() for r in requirements if r and r.strip()]
    sig = {
        "version": version or "",
        "requirements": sorted(norm_reqs),
    }
    digest = hashlib.sha1(json.dumps(sig, sort_keys=True).encode("utf-8")).hexdigest()[
        :12
    ]

    safe_name = (
        plugin_name.replace(os.sep, "_").replace(":", "_").replace(" ", "_").strip("_")
        or "plugin"
    )
    return f"{safe_name}-{digest}"


class VenvManager:
    """
    Minimal per-plugin venv manager.

    - Venvs live under `base` (default from PLUGO_VENV_HOME / VENV_HOME / ./.plugo/venvs)
    - `ensure(key, requirements)` creates or reuses a venv and installs deps
    - `add_site_packages_to_sys_path(venv)` wires that env into current process imports
    """

    def __init__(self, base: Optional[Path] = None) -> None:
        self.base = (base or DEFAULT_VENV_HOME).expanduser()
        self.base.mkdir(parents=True, exist_ok=True)

    def _venv_dir(self, key: str) -> Path:
        # Key is already "semantic", just ensure it's safe as a dir name
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
        Prepend the venv's site-packages dirs to sys.path so its packages are importable.

        This keeps everything in a single process while isolating dependency resolution
        per-plugin via dedicated venvs.
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
