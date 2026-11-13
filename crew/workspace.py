"""The generated project on disk: confined file access, file-block parsing, test runs."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import venv
from pathlib import Path

_SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache"}

# ### FILE: path
# ```python
# ...
# ```
_FILE_BLOCK = re.compile(
    r"^###\s*FILE:\s*`?(?P<path>[^\n`]+?)`?[ \t]*\n```[\w+-]*[ \t]*\n(?P<body>.*?)\n```[ \t]*(?=\n+###\s*FILE:|\s*\Z)",
    re.DOTALL | re.MULTILINE,
)


class UnsafePath(ValueError):
    pass


def parse_file_blocks(text: str) -> dict[str, str]:
    """Extracts {path: content} from an agent reply."""
    return {
        m.group("path").strip(): m.group("body").rstrip() + "\n"
        for m in _FILE_BLOCK.finditer(text.strip())
    }


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, rel: str) -> Path:
        """Maps an agent-supplied path into the project; rejects anything that escapes it."""
        rel = rel.strip().replace("\\", "/")
        p = Path(rel)
        if not rel or p.is_absolute() or ".." in p.parts or p.parts[0] in _SKIP_DIRS:
            raise UnsafePath(rel)
        full = (self.root / p).resolve()
        if not full.is_relative_to(self.root):
            raise UnsafePath(rel)
        return full

    def write(self, rel: str, content: str) -> None:
        full = self.resolve(rel)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def read(self, rel: str) -> str:
        return self.resolve(rel).read_text(encoding="utf-8")

    def exists(self, rel: str) -> bool:
        return self.resolve(rel).is_file()

    def files(self, suffix: str = ".py") -> list[str]:
        out = []
        for p in sorted(self.root.rglob(f"*{suffix}")):
            if not _SKIP_DIRS.intersection(p.relative_to(self.root).parts):
                out.append(p.relative_to(self.root).as_posix())
        return out

    def render(self, paths: list[str], budget: int) -> str:
        """Files as prompt text, stopping before `budget` characters."""
        chunks, used = [], 0
        for rel in paths:
            body = self.read(rel)
            if used + len(body) > budget and chunks:
                chunks.append(f"### FILE: {rel}\n(omitted: prompt size limit)")
                continue
            used += len(body)
            chunks.append(f"### FILE: {rel}\n```python\n{body.rstrip()}\n```")
        return "\n\n".join(chunks)


def make_venv(venv_dir: Path, packages: list[str]) -> Path:
    """Creates a virtualenv with pytest and the plan's dependencies; returns its python."""
    python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        venv.create(venv_dir, with_pip=True)
    proc = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "pytest", *packages],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pip install failed:\n{proc.stderr[-2000:]}")
    return python


def run_tests(ws: Workspace, python: Path | None, timeout_s: int) -> tuple[bool, str]:
    """Runs pytest in the project. Returns (passed, output)."""
    env = {**os.environ, "PYTHONPATH": str(ws.root), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [str(python or sys.executable), "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", "tests"]
    try:
        proc = subprocess.run(cmd, cwd=ws.root, env=env, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        return False, f"{partial}\n\nTIMEOUT: the test run exceeded {timeout_s}s. Something hangs or loops forever."
    output = (proc.stdout + "\n" + proc.stderr).strip()
    if proc.returncode == 5:
        return False, output + "\n\nNo tests were collected."
    return proc.returncode == 0, output
