# Contributing

Issues and pull requests are welcome, new recipes most of all.

## Set up

```sh
git clone https://github.com/jpsanders/mothersauce && cd mothersauce
pyenv install 3.15.2 && pyenv virtualenv 3.15.2 mothersauce && pyenv local mothersauce
make init-dev
```

Without pyenv: `python3.15 -m venv .venv && . .venv/bin/activate && make init-dev`.

## Before a pull request

```sh
make format      # black and isort
make checks      # every check CI runs, in the same order
```

`make checks` runs isort, black, editorconfig-checker, darglint, flake8, mypy in strict mode, bandit, the docs and man
page freshness checks, and pytest with doctests, the pytest-bdd scenarios and a 95% coverage floor. CI runs the same
on Linux and macOS, then installs the built wheel in a clean environment and uses every command.

## A good recipe

- **One pattern, one module.** If it needs a second idea, that is a second recipe.
- **Production shaped.** The way the pattern looks in a codebase that runs every day: typed, validated, logged where
  it matters, with the edge cases handled.
- **Its notes say when not to.** The module docstring explains the pattern; the catalogue entry lists when to use it
  and when to avoid it.
- **A demo that tells a story** in a few deterministic lines, and tests that pin the behaviour, the edges included.
- **The ticket feed as its domain,** so the recipes read as one system.

AGENTS.md has the file by file steps. Commits are signed; tags carry the bare version, `1.2.0`, never `v1.2.0`.
