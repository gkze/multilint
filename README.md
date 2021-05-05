# Multilint (for Python)

[![Actions Test Workflow Widget](https://github.com/gkze/multilint/workflows/ci/badge.svg)](https://github.com/gkze/multilint/actions?query=workflow%3Aci)
[![PyPI Version](https://img.shields.io/pypi/v/pymultilint)](https://pypi.org/project/pymultilint/)
[![Pdoc Documentation](https://img.shields.io/badge/pdoc-docs-green)](https://gkze.github.io/multilint/multilint.html)

A utility tying together multiple linting and other code quality tools

## Intro

Multilint allows running several code quality tools under the same interface.
This is convenient as it saves time on writing multiple linter / formatter /
checker invocations every time in a project.

## Installation

Since there is an existing project called
[`multilint`](https://pypi.org/project/multilint/), this Multilint can be
installed as `pymultilint`:

```bash
$ pip3 install multilint
```

## Usage

Multilint exposes a CLI entry point:

```bash
$ multilint [paths ...]
```

It can optionally take a set of starting paths. There are no CLI options,
as Multilint strives to have all of its configuration codified (see
[Configurability](#configurability)).

Alternatively, Multilint is also usable via its API - either the
[`main`](multilint.py#L526) method, or the
[`Multilint`](multilint.py#L447) class

## Supported Tools

Currently, Multilint integrates the following code quality tools:

* [Autoflake](https://github.com/myint/autoflake) - removes unused imports and
  unused variables as identified by [Pyflakes](https://github.com/PyCQA/pyflakes)
* [Isort](https://pycqa.github.io/isort/) - sorts imports according to specified
  orders
* [Black](https://black.readthedocs.io/en/stable/) - the self-proclaimed
  "uncompromising code formatter" - formats Python source with an opinionated
  style
* [Mypy](http://mypy-lang.org) - static type checker for Python
* [Pylint](https://www.pylint.org) - general best practices linter
* [Pydocstyle](http://www.pydocstyle.org/en/stable/) - in-source documentation
  best practices linter
* [Pyupgrade](https://github.com/asottile/pyupgrade) - upgrades Python syntax to
  the latest for the specified version

## Configurability

Additionally, for tools that do not currently support configuration via
`pyproject.toml`([PEP-621](https://www.python.org/dev/peps/pep-0621/)),
Multilint exposes a configuration interface for them. This allows for
centralized codification of configuration of all code quality tools being used
in a project.

Example relevant sections from a `pyproject.toml`:

```toml
[tool.autoflake]
recursive = true
in_place = true
ignore_init_module_imports = true
remove_all_unused_imports = true
remove_unused_variables = true
verbose = true
srcs_paths = ["somepackage"]

[tool.mypy]
src_paths = ["someotherpackage"]

[tool.multilint]
tool_order = [
  "autoflake",
  "isort",
  "pyupgrade",
  "black",
  "mypy",
  "pylint",
  "pydocstyle"
]
src_paths = ["."]
```

At the time of writing of this README (2020-01-31), neither
[Autoflake](https://github.com/myint/autoflake/issues/59) nor
[Mypy](https://github.com/python/mypy/issues/5205https://github.com/python/mypy/issues/5205)
support configuration via `pyproject.toml`. While support for each may or may
not be added at some point in the future, with multilint configuring these tools
is possible **today**.

Currently, the only two supported configuration option for Multilint are:

* `tool_order`, which defines the execution order of supported tools, and
* `src_paths`, which specifies the source paths (can be files and directories)
  for Multilint to operate on.

Each integrated tool additionally supports `src_dirs` as an override, in case
it is desired to target a specific tool at a different set of files
/ directories.

## Extending Multilint

Support for more tools may be added by subclassing the
[`ToolRunner`](multilint.py#L127) class and overriding the
[`.run(...)`](multilint.py#L159) method.

There are some utilities provided, such as:

* A logger that masquerades as a TextIO object to allow capturing tool output
  from within and wrapping it with preferred logging
* A dictionary for tool configuration that is automatically available in the
  `ToolRunner` class, as long as the tool is registered in
  * The [`Tool`](multilint.py#L47) enum,
  * The [`TOOL_RUNNERS`](multilint.py#L446) mapping, and declared
  * The [`DEFAULT_TOOL_ORDER`](multilint.py#L465) class variable of `Multilint`.

Documentation about adding support for more tools to Multilint may be added in
the future.
