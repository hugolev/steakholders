# Tuning and troubleshooting

## First stop: the logs

`runs/<name>/logs/` holds one numbered file per model call, with the exact prompt and the reply. When an agent does something odd, read its log before changing anything: the cause is usually visible there (missing context, a truncated reply, an instruction the model ignored).

## Symptoms

| Symptom | Likely cause | Fix |
|---|---|---|
| `No model set for 'analyst'` | `model` is empty in `crew.toml` | `python -m crew models`, paste an id into `[defaults]` |
| Connection refused | LM Studio server not started, or a different port | Start it in the Developer tab; match `base_url` |
| `reply hit max_tokens` | File too long for the cap, or a reasoning model spending tokens on thinking | Raise `max_tokens` for that role; check the context length in LM Studio |
| Replies ignore half the prompt | Context length in LM Studio smaller than the prompt, so it was truncated | Raise context length to 16k-32k, or lower `context_chars` |
| `coder failed three times: no file block...` | Model not following the output format | Read the log; try a stronger model or lower temperature |
| `architect could not produce a valid plan` | Paths outside the project, tests in the file list, or circular imports | Read the rejection reason; tighten `prompts/architect.md` |
| `pip install failed` | Architect named a package that does not exist, or no network | Fix `dependencies` in `plan.json`, re-run `build` |
| Tests fail every round with the same error | Debugger is stuck on the wrong cause | Read `REPORT.md` fix history; fix the one file by hand or simplify the spec |
| Tests pass but the tool is wrong | Acceptance criteria missed the behaviour, or the Debugger weakened a test | Check the "test files the Debugger edited" line in `REPORT.md`; add the missing rule to the spec |
| Imports of names that do not exist | The Architect's `interface` was vague | Make interfaces exact in `plan.json`, or add an example to `prompts/architect.md` |

## Tuning prompts

Each file in `prompts/` is one agent's system prompt, re-read on every run. Guidelines that hold for local models:

- Change one prompt at a time and re-run the same spec to compare.
- Add a rule only for a failure you have actually seen in a log.
- Keep prompts short. Every line competes with the task for the model's attention.
- Do not change the output-format section of `coder.md`, `tester.md` or `debugger.md` without also changing `parse_file_blocks` in `crew/workspace.py`.
- Do not rename the JSON fields in the planning prompts without also changing the schemas in `crew/orchestrator.py`.

## Re-running part of a run

- `python -m crew build runs/<name>` can be repeated on the same folder. It rewrites the code and tests from `plan.json`.
- To retry with a different model or prompt, edit `crew.toml` or `prompts/` and run `build` again on the same folder; planning is not repeated.

## Testing the pipeline itself

```
python -m pytest tests
```

This uses a scripted stand-in for the model, so it needs neither LM Studio nor the `openai` package. Run it after changing anything in `crew/`.
