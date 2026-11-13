# Writing specs

The spec is the only thing the Analyst sees, and the Analyst's output is the only thing everyone else sees. A good one-pager makes more difference than any setting.

## Shape that works

See `examples/wordfreq_spec.md`. Four short sections are enough:

1. **Goal.** One or two sentences: what it is and who uses it.
2. **Usage.** The exact command line, function signature, or input and output files.
3. **Behaviour.** A bullet per rule. Include defaults, ordering, formats, and what happens on bad input.
4. **Constraints.** Standard library only, Python version, anything that must not be used.

## What makes a spec buildable

- **Say the observable result.** "Prints `error: file not found: <path>` to stderr and exits with status 2" becomes a test. "Handles errors gracefully" becomes a guess.
- **Give one concrete example** of input and expected output when the format matters.
- **State defaults and tie-breaks.** Unstated ones end up in the Analyst's assumptions; read those in `PLAN.md`.
- **Keep it to one page.** The pipeline is sized for roughly 2 to 8 source files. Split bigger ideas into several specs.

## What to avoid

- Anything a test cannot check without the network, a real clock, or a person typing. If the tool needs those, say which part is the pure logic, so the Architect can separate it and the Tester can cover it.
- Vague quality words ("fast", "robust", "user-friendly") with no measurable meaning.
- Design instructions unless you care. The Architect chooses the layout; if you need a particular module or class name, state it.

## Reviewing the plan

After `python -m crew plan`, open `PLAN.md` and check, in this order:

1. **Assumptions** and **open questions**: is this what you meant?
2. **Acceptance criteria**: these become the tests, which become the definition of done.
3. **Third-party packages**: each will be pip-installed. Confirm every name is a real package you trust.
4. **Files and interfaces**: is it bigger than the problem?

To change something, either fix the spec and re-run `plan`, or edit `requirements.json` and `plan.json` in the run folder directly. `build` reads those two files, not `PLAN.md`.
