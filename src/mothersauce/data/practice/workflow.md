# The local and CI workflow

Your machine and CI run the same commands from the same Makefile, so a pull request fails for the same reason in both
places. This repository started from [python-package-template](https://github.com/jpsanders/python-package-template)
and keeps its workflow: the template's first commit and its rename are the first two commits of this history.

## One Python per project: pyenv and pyenv-virtualenv

```sh
pyenv install 3.15.2                  # once per machine; update pyenv first if `pyenv install --list` lacks it
pyenv virtualenv 3.15.2 mothersauce   # a virtual environment that belongs to this project
pyenv local mothersauce               # writes .python-version, so the environment is active in this folder
python -V                             # Python 3.15.2
```

Activation on `cd` needs `eval "$(pyenv virtualenv-init -)"` in your shell's start up file. `.python-version` belongs
to you, not to the repository: list it in your global ignore file, `~/.gitignore`. Without pyenv,
`python3.15 -m venv .venv && . .venv/bin/activate` does the same job, and so does `uv venv --python 3.15`.

## The pass: make checks

```sh
make init-dev    # the package in editable mode, with every development tool
make format      # black and isort rewrite the code in place
make checks      # every check CI runs, in CI's order; it reports and never edits
make help        # every target
```

`make checks` runs isort, black, editorconfig-checker, darglint, flake8, mypy, bandit, the docs and man page
freshness checks, and pytest with coverage. Run it before you say a change is done. A kitchen calls the counter where
plates leave for the dining room "the pass": nothing broken leaves it.

## CI: the same commands on every push

`.github/workflows/dev.yml` is built from reusable workflows. `python-checks.yml` runs the static checks once;
`python-tests.yml` runs pytest on Python 3.15 on Linux and macOS; the `package` job builds the wheel, installs it in a
clean environment with no source tree around it, and runs the command. That last job catches a data file left out of
the package, which every other test misses because the tests run from the source tree.

## Releases: the tag is the version

There is no version number in the code. setuptools_scm reads it from git, so untagged commits build as development
versions such as `1.0.1.dev3+g1a2b3c4`. To release:

```sh
git tag -s 1.0.0 -m 1.0.0        # the bare version, never v1.0.0; signed
git push origin 1.0.0
gh release create 1.0.0 --title 1.0.0 --notes-file notes.md
```

`release.yml` then checks that the README's release badge names the same version, builds the wheel and the sdist, and
attaches them to the release. Release only when every CI job of the tagged commit is green.

## Main is protected

The branch protection mirrors the pass: the CI jobs are required checks, commits must be signed, history stays linear,
and nobody can force push to main or delete it. A change reaches main through a green pull request.
