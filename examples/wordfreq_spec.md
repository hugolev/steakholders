# Word frequency tool

## Goal
A command-line tool that reports the most common words in a text file, for quickly getting a feel for a document.

## Usage
`python -m wordfreq FILE [--top N] [--min-length L] [--json]`

## Behaviour
- Words are runs of letters and apostrophes; matching is case-insensitive and output is lower case.
- `--top N` limits output to the N most frequent words (default 10).
- `--min-length L` ignores words shorter than L characters (default 1).
- Ties in frequency are ordered alphabetically.
- Default output is one line per word: the word, a tab, then the count.
- `--json` prints a JSON array of `{"word": ..., "count": ...}` objects instead.
- A missing file prints `error: file not found: <path>` to stderr and exits with status 2.
- An empty file prints nothing and exits with status 0.

## Constraints
Standard library only.
