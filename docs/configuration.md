# Configuration

All settings are in `crew.toml`. Pass a different file with `python -m crew --config path/to/file.toml ...`; prompts are read from the `prompts/` folder beside that file.

## `[server]`

| Key | Default | Meaning |
|---|---|---|
| `base_url` | `http://localhost:1234/v1` | LM Studio's OpenAI-compatible server. Change the host to use a model on another machine. |
| `api_key` | `lm-studio` | Required by the client; LM Studio does not check it. |
| `timeout_s` | `900` | Per-request timeout. Whole-file generations on a local model can take minutes. |

## `[defaults]`

Applied to every agent unless overridden.

| Key | Default | Meaning |
|---|---|---|
| `model` | `""` (must be set) | Model id exactly as `python -m crew models` prints it. |
| `temperature` | `0.2` | Low values keep code and plans consistent. |
| `max_tokens` | `8192` | Cap on one reply. The largest file an agent writes must fit in this. |

## `[agents.<role>]`

Roles: `analyst`, `architect`, `coder`, `tester`, `debugger`, `reviewer`. Any `[defaults]` key can be overridden per role.

```toml
[agents.architect]
model = "some-general-reasoning-model"   # only if you can keep two models loaded
temperature = 0.2
max_tokens = 4000
```

Shipped overrides: the Coder runs coldest (`0.1`), the Debugger slightly warmer (`0.3`) so that successive rounds do not produce the identical fix, and the JSON agents have smaller `max_tokens` because their output is short.

### One model or several

On a single GPU, use one model for all roles. When two roles name different models, LM Studio has to swap them in and out of memory between calls, which costs more time than a specialist saves. If you have room to keep two loaded, the useful split is a general reasoning model for `analyst`, `architect` and `reviewer`, and a coding model for `coder`, `tester` and `debugger`.

## `[pipeline]`

| Key | Default | Meaning |
|---|---|---|
| `max_fix_rounds` | `5` | Test/debug cycles before the run is reported as failing. |
| `test_timeout_s` | `120` | Kills a test run that hangs. |
| `use_venv` | `true` | Create `<run>/.venv`, install pytest and the plan's dependencies there, and run tests with it. With `false`, tests run in the interpreter you launched and nothing is installed. |
| `context_chars` | `60000` | Cap on source text pasted into one prompt, roughly 15k tokens. Files beyond the cap are listed as omitted. |

## LM Studio settings that matter

- **Context length.** Set it in the model's load settings to at least 16k tokens, ideally 32k. If you raise `context_chars`, raise this too: prompt plus `max_tokens` must fit.
- **Server.** Developer tab, Start Server. The port shown there goes in `base_url`.
- **Reasoning models.** `<think>...</think>` blocks are stripped from replies automatically. Thinking tokens still count against `max_tokens`, so raise it for those models.
