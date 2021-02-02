# Multilint (for Python)

A utility tying together multiple linting and other code quality tools

Multilint allows running several code quality tools under the same interface.
This is convenient as it saves time on writing multiple linter / formatter /
checker invocations every time in a project.

Additionally, for tools that do
not currently support configuration via `pyproject.toml`
([PEP-621](https://www.python.org/dev/peps/pep-0621/)), Multilint exposes a
configuration interface for them. This allows for centralized codification of
configuration of all code quality tools being used in a project.

Example relevant sections from a `pyproject.toml`:

```toml
[tool.autoflake]
recursive = true
in_place = true
ignore_init_module_imports = true
remove_all_unused_imports = true
remove_unused_variables = true
verbose = true
srcs = ["."]

[tool.mypy]
src = "."

[tool.multilint]
tool_order = ["autoflake", "isort", "black", "mypy"]
```

Currently, the only supported configuration option for Multilint is
`tool_order` which defines the execution order of supported tools.

At the time of writing of this README (2020-01-31), neither
[Autoflake](https://github.com/myint/autoflake/issues/59) nor
[Mypy](https://github.com/python/mypy/issues/5205https://github.com/python/mypy/issues/5205)
support configuration via `pyproject.toml`. While support for each may or may
not be added at some point in the future, with multilint configuring these tools
is possible **today**.

## Supported Tools

* [Autoflake](https://github.com/myint/autoflake) - removes unused imports and
  unused variables as identified by [Pyflakes](https://github.com/PyCQA/pyflakes)
* [Isort](https://pycqa.github.io/isort/) - sorts imports according to specified
  orders
* [Black](https://black.readthedocs.io/en/stable/) - the self-proclaimed
  "uncompromising code formatter" - formats Python source with an opinionated
  style
* [Mypy](http://mypy-lang.org) - static type checker for Python
* [Pylint](https://www.pylint.org) - general best practices linter

Support for more tools may be added by subclassing the
[`ToolRunner`](multilint.py#L130) class and overriding the
[`.run(...)`](multilint.py#L162) method.

There are some utilities provided, such as:

* A logger that masquerades as a TextIO object to allow capturing tool output
  from within and a configuration
* A mapping for tool configuration that is automatically available in the
  `ToolRunner` class (as long as it is registered in the
  [`Tool`](multilint.py#L47)) enum, the [`TOOL_RUNNERS`](multilint.py#L440)
  mapping, and declared in the [`DEFAULT_TOOL_ORDER`](multilint.py#L459) class
  variable of `Multilint`.

Documentation about adding support for more tools to Multilint may be added in
the future.
