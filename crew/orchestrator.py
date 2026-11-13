"""The pipeline. Plain Python decides what happens next; the models only produce content.

    spec -> Analyst -> Architect -> [you approve PLAN.md] -> Coder (per file) -> Tester
         -> run pytest <-> Debugger (up to N rounds) -> Reviewer -> REPORT.md
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from .config import Config
from .workspace import UnsafePath, Workspace, make_venv, parse_file_blocks, run_tests


class Completer(Protocol):
    def complete(self, role: str, user: str, schema: dict | None = None) -> Any: ...


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_LIST = {"type": "array", "items": _STR}

REQUIREMENTS_SCHEMA = _obj({
    "summary": _STR, "requirements": _LIST, "acceptance_criteria": _LIST,
    "assumptions": _LIST, "open_questions": _LIST,
})
PLAN_SCHEMA = _obj({
    "overview": _STR,
    "files": {"type": "array", "items": _obj({
        "path": _STR, "purpose": _STR, "interface": _STR, "depends_on": _LIST,
    })},
    "entry_point": _STR,
    "dependencies": _LIST,
})
REVIEW_SCHEMA = _obj({"meets_spec": {"type": "boolean"}, "gaps": _LIST, "notes": _STR})


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) or "- (none)"


def _say(msg: str) -> None:
    print(msg, flush=True)


class PlanError(RuntimeError):
    pass


def _order_files(files: list[dict]) -> list[dict]:
    """Dependencies first, so the Coder can always be shown the files it imports."""
    by_path = {f["path"]: f for f in files}
    ordered: list[dict] = []
    state: dict[str, int] = {}

    def visit(path: str) -> None:
        if state.get(path) == 2:
            return
        if state.get(path) == 1:
            raise PlanError(f"circular dependency involving {path}")
        state[path] = 1
        for dep in by_path[path]["depends_on"]:
            if dep in by_path:
                visit(dep)
        state[path] = 2
        ordered.append(by_path[path])

    for f in files:
        visit(f["path"])
    return ordered


def _check_plan(plan: dict, ws: Workspace) -> dict:
    if not plan["files"]:
        raise PlanError("the plan lists no files")
    seen = set()
    for f in plan["files"]:
        f["path"] = f["path"].strip().replace("\\", "/").removeprefix("./")
        try:
            ws.resolve(f["path"])
        except UnsafePath:
            raise PlanError(f"unsafe path in plan: {f['path']!r}") from None
        if not f["path"].endswith(".py") or f["path"].startswith("tests/"):
            raise PlanError(f"plan files must be non-test .py files: {f['path']!r}")
        if f["path"] in seen:
            raise PlanError(f"duplicate path in plan: {f['path']!r}")
        seen.add(f["path"])
    plan["files"] = _order_files(plan["files"])
    return plan


def _plan_md(req: dict, plan: dict) -> str:
    files = "\n\n".join(
        f"### `{f['path']}`\n{f['purpose']}\n\n```\n{f['interface'].strip()}\n```"
        + (f"\nDepends on: {', '.join(f['depends_on'])}" if f["depends_on"] else "")
        for f in plan["files"]
    )
    return f"""# Plan

{req['summary']}

## Requirements
{_bullets(req['requirements'])}

## Acceptance criteria (these become the tests)
{_bullets(req['acceptance_criteria'])}

## Assumptions made where the spec was silent
{_bullets(req['assumptions'])}

## Open questions
{_bullets(req['open_questions'])}

## Design
{plan['overview']}

Run with: {plan['entry_point']}

Third-party packages to be pip-installed (check each name is a real package you trust):
{_bullets(plan['dependencies'])}

{files}
"""


class Crew:
    def __init__(self, cfg: Config, llm: Completer, run_dir: Path):
        self.cfg = cfg
        self.llm = llm
        self.run_dir = run_dir
        self.ws = Workspace(run_dir / "project")

    # ---- stage 1: spec -> requirements -> plan ---------------------------------------

    def plan(self, spec_text: str) -> Path:
        _say("analyst: reading the spec")
        req = self.llm.complete("analyst", f"# Spec\n\n{spec_text.strip()}", REQUIREMENTS_SCHEMA)

        _say("architect: designing the layout")
        user = (
            f"# Summary\n{req['summary']}\n\n# Requirements\n{_bullets(req['requirements'])}\n\n"
            f"# Acceptance criteria\n{_bullets(req['acceptance_criteria'])}\n\n"
            f"# Assumptions\n{_bullets(req['assumptions'])}"
        )
        error = ""
        for _ in range(3):
            plan = self.llm.complete(
                "architect", user + (f"\n\nYour previous plan was rejected: {error}. Fix that." if error else ""),
                PLAN_SCHEMA,
            )
            try:
                plan = _check_plan(plan, self.ws)
                break
            except PlanError as exc:
                error = str(exc)
                _say(f"architect: plan rejected ({error}), retrying")
        else:
            raise PlanError(f"architect could not produce a valid plan: {error}")

        self._save("requirements.json", req)
        self._save("plan.json", plan)
        plan_md = self.run_dir / "PLAN.md"
        plan_md.write_text(_plan_md(req, plan), encoding="utf-8")
        return plan_md

    # ---- stage 2: plan -> code -> tests -> fix loop -> report ------------------------

    def build(self) -> bool:
        req = self._load("requirements.json")
        plan = _check_plan(self._load("plan.json"), self.ws)  # re-checked: you may have edited it
        brief = self._brief(req, plan)

        for f in plan["files"]:
            _say(f"coder: {f['path']}")
            deps = [d for d in f["depends_on"] if self.ws.exists(d)]
            user = (
                f"{brief}\n\n# Files you depend on (already written)\n"
                f"{self.ws.render(deps, self.cfg.context_chars) or '(none)'}\n\n"
                f"# Your task\nWrite `{f['path']}`.\nPurpose: {f['purpose']}\nInterface:\n{f['interface']}"
            )
            self._write_blocks("coder", user, only={f["path"]})
        self.ws.write("requirements.txt", "".join(f"{d}\n" for d in plan["dependencies"]))

        _say("tester: writing tests")
        source = self.ws.files()
        user = (
            f"# Acceptance criteria\n{_bullets(req['acceptance_criteria'])}\n\n"
            f"# Requirements\n{_bullets(req['requirements'])}\n\n"
            f"# Source files\n{self.ws.render(source, self.cfg.context_chars)}"
        )
        self._write_blocks("tester", user, prefix="tests/")

        python = None
        if self.cfg.use_venv:
            _say("runner: preparing virtualenv")
            python = make_venv(self.run_dir / ".venv", plan["dependencies"])

        history: list[str] = []
        tests_touched: set[str] = set()
        passed, output = run_tests(self.ws, python, self.cfg.test_timeout_s)
        rounds = 0
        while not passed and rounds < self.cfg.max_fix_rounds:
            rounds += 1
            _say(f"debugger: round {rounds}/{self.cfg.max_fix_rounds}")
            user = (
                f"# Acceptance criteria\n{_bullets(req['acceptance_criteria'])}\n\n"
                f"# Plan interfaces\n{self._interfaces(plan)}\n\n"
                f"# Earlier fix attempts that did not work\n{_bullets(history)}\n\n"
                f"# pytest output\n```\n{output[-6000:]}\n```\n\n"
                f"# Project files\n{self.ws.render(self._relevant(output), self.cfg.context_chars)}"
            )
            reply = self.llm.complete("debugger", user)
            m = re.search(r"DIAGNOSIS:\s*(.+)", reply)
            changed = self._apply(parse_file_blocks(reply))
            history.append(f"Round {rounds}: {m.group(1).strip() if m else '(no diagnosis)'} "
                           f"[changed: {', '.join(changed) or 'nothing'}]")
            tests_touched.update(c for c in changed if c.startswith("tests/"))
            passed, output = run_tests(self.ws, python, self.cfg.test_timeout_s)

        _say("reviewer: checking against the spec")
        review = self.llm.complete(
            "reviewer",
            f"# Requirements\n{_bullets(req['requirements'])}\n\n"
            f"# Acceptance criteria\n{_bullets(req['acceptance_criteria'])}\n\n"
            f"# Assumptions\n{_bullets(req['assumptions'])}\n\n"
            f"# Test result\n{'PASSED' if passed else 'FAILED'} after {rounds} fix round(s)\n\n"
            f"# Final files\n{self.ws.render(self.ws.files(), self.cfg.context_chars)}",
            REVIEW_SCHEMA,
        )
        (self.run_dir / "REPORT.md").write_text(
            f"# Report\n\n"
            f"- Tests: **{'passed' if passed else 'FAILED'}** after {rounds} fix round(s)\n"
            f"- Reviewer says the spec is met: **{'yes' if review['meets_spec'] else 'no'}**\n"
            f"- Test files the Debugger edited (read these; a weakened test hides a bug): "
            f"{', '.join(sorted(tests_touched)) or 'none'}\n"
            f"- Run with: {plan['entry_point']}\n\n"
            f"## Gaps\n{_bullets(review['gaps'])}\n\n## Notes\n{review['notes']}\n\n"
            f"## Fix history\n{_bullets(history)}\n\n## Last pytest output\n```\n{output[-4000:]}\n```\n",
            encoding="utf-8",
        )
        return passed

    # ---- helpers ---------------------------------------------------------------------

    def _brief(self, req: dict, plan: dict) -> str:
        return (
            f"# What we are building\n{req['summary']}\n\n# Requirements\n{_bullets(req['requirements'])}\n\n"
            f"# Design\n{plan['overview']}\nThird-party packages allowed: {', '.join(plan['dependencies']) or 'none'}\n\n"
            f"# All files in the plan\n{self._interfaces(plan)}"
        )

    @staticmethod
    def _interfaces(plan: dict) -> str:
        return "\n\n".join(f"`{f['path']}`: {f['purpose']}\n{f['interface'].strip()}" for f in plan["files"])

    def _relevant(self, pytest_output: str) -> list[str]:
        """Everything if it fits; otherwise files named in the failure first."""
        files = self.ws.files()
        if sum(len(self.ws.read(f)) for f in files) <= self.cfg.context_chars:
            return files
        named = [f for f in files if f in pytest_output]
        return named + [f for f in files if f not in named]

    def _write_blocks(self, role: str, user: str, only: set[str] | None = None, prefix: str = "") -> None:
        """Asks a code agent for files and writes them; retries when the reply is unusable."""
        problem = ""
        for _ in range(3):
            reply = self.llm.complete(role, user + (f"\n\nYour last reply was unusable: {problem}" if problem else ""))
            blocks = parse_file_blocks(reply)
            if only is not None:
                blocks = {p: c for p, c in blocks.items() if p in only}
                # a lone unnamed code block is accepted for a single expected file
                if not blocks and len(only) == 1 and (m := re.search(r"```[\w+-]*\n(.*?)\n```", reply, re.DOTALL)):
                    blocks = {next(iter(only)): m.group(1).rstrip() + "\n"}
            blocks = {p: c for p, c in blocks.items() if p.startswith(prefix)}
            bad = next((p for p, c in blocks.items() if self._syntax_error(p, c)), None)
            if blocks and not bad:
                self._apply(blocks)
                return
            problem = (f"{bad} has a syntax error: {self._syntax_error(bad, blocks[bad])}" if bad
                       else "no file block in the required `### FILE: path` + fenced code format")
        raise RuntimeError(f"{role} failed three times: {problem}")

    @staticmethod
    def _syntax_error(path: str, content: str) -> str:
        if not path.endswith(".py"):
            return ""
        try:
            compile(content, path, "exec")
            return ""
        except SyntaxError as exc:
            return f"line {exc.lineno}: {exc.msg}"

    def _apply(self, blocks: dict[str, str]) -> list[str]:
        changed = []
        for path, content in blocks.items():
            try:
                self.ws.write(path, content)
                changed.append(path.strip().replace("\\", "/"))
            except UnsafePath:
                _say(f"  ignored write outside the project: {path!r}")
        return changed

    def _save(self, name: str, data: dict) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self, name: str) -> dict:
        return json.loads((self.run_dir / name).read_text(encoding="utf-8"))
