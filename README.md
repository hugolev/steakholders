# steakholders

A crew of six agents, running on your own LM Studio models, that turns a one-page spec into a tested Python project.

```
spec.md -> Analyst -> Architect -> (you approve PLAN.md) -> Coder -> Tester -> pytest <-> Debugger -> Reviewer -> REPORT.md
```

## Setup

1. `pip install openai pytest` (the only dependencies; Python 3.11+).
2. In LM Studio: load a coding model, open the Developer tab, start the server.
3. In the model's load settings, set **context length to at least 16k, ideally 32k**. LM Studio's default is much smaller, and a truncated prompt is the most common cause of bad output.
4. `python -m crew models`, then paste the id of your model into `model = ""` in `crew.toml`.

## Use

```
python -m crew plan examples/wordfreq_spec.md     # Analyst + Architect, then stops
# read runs/<name>/PLAN.md; edit requirements.json / plan.json beside it if you disagree
python -m crew build runs/<name>                  # Coder, Tester, fix loop, Reviewer
python -m crew run  examples/wordfreq_spec.md     # both stages, no stop
```

Each run folder holds `PLAN.md`, `REPORT.md`, `project/` (the code and its tests) and `logs/` (every prompt and reply, numbered, for when an agent misbehaves).

## The agents

| Agent | Reads | Produces | Output style |
|---|---|---|---|
| Analyst | your spec | requirements, acceptance criteria, assumptions, open questions | JSON (schema-enforced) |
| Architect | requirements | file list with exact interfaces, dependencies | JSON (schema-enforced) |
| Coder | plan + the files it imports | one source file per call | fenced file block |
| Tester | acceptance criteria + source | pytest files | fenced file blocks |
| Debugger | pytest output + files + earlier failed attempts | diagnosis and replaced files | fenced file blocks |
| Reviewer | requirements + final code | whether the spec is met, gaps | JSON (schema-enforced) |

A seventh step, the runner, is plain Python: it runs pytest with a timeout.

## Design choices, and why

- **Code orchestrates, models write.** The order of work is a fixed Python pipeline. No agent decides what to do next or calls tools. Local models are much more reliable at "write this one file" than at steering a tool loop.
- **Small prompts.** Each call sees only what it needs: the Coder gets the plan and the files it imports, not the whole project. This matters more than model size on local hardware.
- **Schema-enforced JSON for planning, plain fenced blocks for code.** LM Studio constrains JSON output to a schema, so plans always parse. Code is not put inside JSON because escaping it degrades what local models write.
- **Tests come from the acceptance criteria, not from the code**, and the Debugger is told the criteria win. `REPORT.md` lists any test file the Debugger edited so you can check it did not weaken a test.
- **One model for all roles by default.** Swapping models between calls on one GPU is slow. Roles differ by prompt and temperature. If you have memory for two loaded models, set `model` under `[agents.analyst]` / `[agents.architect]` to a general reasoning model and keep a coder model for the rest.

## Tuning

- Behaviour: edit `prompts/<agent>.md`. These are the system prompts, read fresh on every run.
- Model, temperature, token limits, fix rounds, timeouts: `crew.toml`.
- "reply hit max_tokens": raise `max_tokens` for that agent and check the context length in LM Studio.
- An agent keeps producing unusable output: open its file in `logs/` to see exactly what it was asked.

## Things to know before you rely on it

- **Generated code runs on your machine** when tests execute. It is confined to a timeout and (with `use_venv = true`) its own virtualenv, but it is not sandboxed. For specs that touch files, the network or the shell, run inside a container or VM.
- **Dependencies the Architect names get pip-installed.** Models sometimes invent package names, and invented names can be squatted by malicious packages. `PLAN.md` lists them; check them before `build`. This is the main reason `plan` and `build` are separate.
- Agents can write only inside `runs/<name>/project/`; other paths are refused.
- Sized for one-page specs: roughly 2 to 8 source files. Larger projects will exceed the prompt budget (`context_chars`).
- `python -m pytest tests` checks the pipeline itself using a scripted stand-in model (no LM Studio needed).

## Documentation

- [Architecture](docs/architecture.md): the pipeline, what each agent sees and returns, guard rails, code map
- [Configuration](docs/configuration.md): every `crew.toml` setting and the LM Studio settings that matter
- [Writing specs](docs/writing-specs.md): what makes a one-pager buildable, and how to review the plan
- [Tuning and troubleshooting](docs/troubleshooting.md): symptoms, fixes, prompt tuning
