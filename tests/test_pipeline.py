"""End-to-end test of the pipeline with a scripted stand-in for the model.

Checks the orchestration (ordering, file parsing, fix loop, path confinement), not model quality.
Run from the steakholders folder:  python -m pytest tests
"""
from pathlib import Path

import pytest

from crew.config import load_config
from crew.orchestrator import Crew, PlanError
from crew.workspace import UnsafePath, Workspace, parse_file_blocks

ROOT = Path(__file__).resolve().parent.parent

REQ = {
    "summary": "An adder.", "requirements": ["add(a, b) returns a + b"],
    "acceptance_criteria": ["Given 2 and 3 when added then 5"], "assumptions": [], "open_questions": [],
}
PLAN = {
    "overview": "One package.",
    "files": [  # deliberately listed dependents-first to exercise ordering
        {"path": "adder/cli.py", "purpose": "cli", "interface": "def main(argv=None) -> int", "depends_on": ["adder/core.py"]},
        {"path": "adder/core.py", "purpose": "logic", "interface": "def add(a: int, b: int) -> int", "depends_on": ["adder/__init__.py"]},
        {"path": "adder/__init__.py", "purpose": "package", "interface": "", "depends_on": []},
    ],
    "entry_point": "python -m adder.cli", "dependencies": [],
}


def block(path, body):
    return f"### FILE: {path}\n```python\n{body}\n```"


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete(self, role, user, schema=None):
        self.calls.append((role, user))
        if role == "analyst":
            return REQ
        if role == "architect":
            return PLAN
        if role == "coder":
            if "Write `adder/__init__.py`" in user:
                return block("adder/__init__.py", '"""adder"""')
            if "Write `adder/core.py`" in user:
                return "Sure!\n\n" + block("adder/core.py", "def add(a, b):\n    return a - b  # bug")
            return block("adder/cli.py", "from adder.core import add\n\ndef main(argv=None):\n    print(add(1, 2))\n    return 0")
        if role == "tester":
            return block("tests/test_core.py", "from adder.core import add\n\ndef test_add():\n    assert add(2, 3) == 5")
        if role == "debugger":
            return ("DIAGNOSIS: add subtracts.\n\n"
                    + block("adder/core.py", "def add(a, b):\n    return a + b")
                    + "\n\n" + block("../../evil.py", "x = 1"))
        if role == "reviewer":
            return {"meets_spec": True, "gaps": [], "notes": "ok"}
        raise AssertionError(role)


@pytest.fixture
def cfg():
    from dataclasses import replace
    return replace(load_config(ROOT / "crew.toml", require_model=False), use_venv=False)


def test_full_pipeline_fixes_bug(tmp_path, cfg):
    llm = FakeLLM()
    crew = Crew(cfg, llm, tmp_path / "run")
    crew.plan("Build an adder.")
    assert (tmp_path / "run" / "PLAN.md").exists()
    assert crew.build() is True

    roles = [r for r, _ in llm.calls]
    assert roles == ["analyst", "architect", "coder", "coder", "coder", "tester", "debugger", "reviewer"]
    # dependencies are coded first, and the dependent sees them
    coder_prompts = [u for r, u in llm.calls if r == "coder"]
    assert "Write `adder/__init__.py`" in coder_prompts[0]
    assert "Write `adder/cli.py`" in coder_prompts[2] and "return a - b" in coder_prompts[2]
    assert "a + b" in (tmp_path / "run/project/adder/core.py").read_text()
    assert not (tmp_path / "evil.py").exists()
    report = (tmp_path / "run/REPORT.md").read_text()
    assert "passed" in report and "1 fix round" in report


def test_gives_up_after_max_rounds(tmp_path, cfg):
    class Stuck(FakeLLM):
        def complete(self, role, user, schema=None):
            if role == "debugger":
                self.calls.append((role, user))
                return "DIAGNOSIS: no idea."
            return super().complete(role, user, schema)

    llm = Stuck()
    crew = Crew(cfg, llm, tmp_path / "run")
    crew.plan("x")
    assert crew.build() is False
    assert sum(r == "debugger" for r, _ in llm.calls) == cfg.max_fix_rounds
    assert "Round 1: no idea." in llm.calls[-2][1]  # later rounds see earlier attempts


def test_plan_rejects_bad_paths(tmp_path, cfg):
    class Bad(FakeLLM):
        def complete(self, role, user, schema=None):
            if role == "architect":
                return {**PLAN, "files": [{"path": "../x.py", "purpose": "", "interface": "", "depends_on": []}]}
            return super().complete(role, user, schema)

    with pytest.raises(PlanError):
        Crew(cfg, Bad(), tmp_path / "run").plan("x")


def test_coder_syntax_error_is_retried(tmp_path, cfg):
    class Sloppy(FakeLLM):
        first = True

        def complete(self, role, user, schema=None):
            if role == "coder" and "Write `adder/core.py`" in user and self.first:
                self.first = False
                return block("adder/core.py", "def add(a, b:\n    return a + b")
            if role == "coder" and "Write `adder/core.py`" in user:
                assert "syntax error" in user
                return block("adder/core.py", "def add(a, b):\n    return a + b")
            return super().complete(role, user, schema)

    crew = Crew(cfg, Sloppy(), tmp_path / "run")
    crew.plan("x")
    assert crew.build() is True


def test_parse_blocks_keeps_inner_fences():
    text = block("a.py", 'DOC = """\n```\ninner\n```\n"""') + "\n\n" + block("b.py", "x = 1")
    out = parse_file_blocks(text)
    assert list(out) == ["a.py", "b.py"] and "inner" in out["a.py"]


@pytest.mark.parametrize("path", ["../a.py", "/etc/passwd", "a/../../b.py", ".venv/x.py", ""])
def test_workspace_confinement(tmp_path, path):
    with pytest.raises(UnsafePath):
        Workspace(tmp_path / "p").resolve(path)
