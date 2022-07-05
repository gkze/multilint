#!/usr/bin/env python3
"""
Multilint is a runner for multiple code quality tools.

Multilint enables running various Python linters (and other CQ tools) under the
same interface, making it easier to configure and run all code quality tools
from a centralized location.
"""
from __future__ import annotations

import logging
import re
import sys
from argparse import Namespace
from dataclasses import dataclass, field
from enum import Enum, auto
from glob import glob
from io import TextIOBase
from logging import Formatter, Logger, StreamHandler
from pathlib import Path
from typing import Any, Iterable, Mapping
from typing import Sequence as Seq
from typing import TextIO, TypeVar, cast
from unittest.mock import patch

import pydocstyle  # type: ignore
import toml
from autoflake import _main as autoflake_main  # type: ignore
from black import main as black_main
from isort import files as isort_files
from isort.api import sort_file as isort_file
from isort.settings import DEFAULT_CONFIG
from mypy.main import main as mypy_main  # pylint: disable=no-name-in-module
from pylint.lint import Run as PylintRun  # type: ignore
from pyupgrade._main import _fix_file as pyupgrade_fix_file  # type: ignore

FILE_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = FILE_DIR
PYPROJECT_TOML_FILENAME: str = "pyproject.toml"

LogLevel = TypeVar("LogLevel", bound=int)

LOG_FMT: str = "%(asctime)s [%(levelname)s] [%(name)s] %(msg)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
LOGGER: Logger = logging.getLogger("multilint")


class Tool(Enum):
    """Encapsulates all supported linters, including Multilint itself."""

    AUTOFLAKE = "autoflake"
    BLACK = "black"
    ISORT = "isort"
    MULTILINT = "multilint"
    MYPY = "mypy"
    PYDOCSTYLE = "pydocstyle"
    PYLINT = "pylint"
    PYUPGRADE = "pyupgrade"


class ToolResult(Enum):
    """ToolResult describes a generic run result from a code quality tool."""

    SUCCESS = auto()
    SUCCESS_PARTIAL = auto()
    FAILURE = auto()


class ToolLogger(Logger):
    """ToolLogger allows setting format on itself during instantiation."""

    def __init__(
        self: ToolLogger, name: str, level: LogLevel, logfmt: str = LOG_FMT
    ) -> None:
        """Create a ToolLogger with the specified name, level, and format.

        Log format gets applied immediately.
        """
        super().__init__(name, level=level)

        self.set_format(logfmt)

    def set_format(self: ToolLogger, fmtstr: str) -> None:
        """Set the specified log message format.

        Uses a StreamHandler by setting a formatter on it with the specified
        format string, and adds the StreamHanlder to the logger instance.
        """
        handler: StreamHandler = StreamHandler()
        handler.setFormatter(Formatter(fmtstr))
        self.addHandler(handler)


class TextIOLogger(TextIOBase, ToolLogger):
    """Logger object that can be written to like a stream-like object.

    A logger that masquerades as a TextIO-compatible object, allowing it to be
    passed into code quality tools that write to TextIO interfaces. This way,
    it is possible to wrap the stdout / stderr / other streams with our
    common logging.
    """

    def __init__(
        self: TextIOLogger, name: str, level: LogLevel, logfmt: str = LOG_FMT
    ) -> None:
        """Construct a TextIOLogger."""
        self._name: str = name
        self._level: int = level

        super().__init__(self._name, self._level, logfmt)

    def write(self: TextIOLogger, msg: str) -> int:
        """Write data to the logger as if it were a stream-like object.

        The write() method is implemented to forward data to the logging
        part of this object, allowing capturing logs that would normally be
        written to stdout / stderr.
        """
        if msg in ("", "\n"):
            return 0

        for line in filter(None, msg.split("\n")):
            self.log(self._level, line)

        return len(msg)


class ToolRunner:
    """Base class for integrating code quality tools.

    ToolRunner is a base class for any plugin that integrates a code quality
    tool. Subclasses only have to implement the run() method. There is a
    convenience method available,
    """

    def __init__(
        self: ToolRunner,
        tool: Tool,
        src_paths: Seq[Path] = [Path(".")],
        config: Mapping[str, Any] = {},
    ) -> None:
        """Initialize a ToolRunner object."""
        self._tool: Tool = tool
        self.src_paths: Seq[Path] = src_paths
        self.config: Mapping[str, Any] = config

    def make_logger(
        self: ToolRunner,
        cls: type[ToolLogger] | type[TextIOLogger],
        level: LogLevel,
    ) -> ToolLogger | TextIOLogger:
        """Create a logger for the ToolRunner object.

        Creates a logger object from the specified logger class (can be
        either a ToolLogger or a TextIOLogger) with the specified default log
        level.
        """
        return cls(f"tool.{self._tool.value}", level)

    def run(self: ToolRunner) -> ToolResult:
        """Is implemented by subclasses to run the CQ (code quality) tool."""
        raise NotImplementedError("run() needs to be implemented by subclass!")


class AutoflakeRunner(ToolRunner):
    """Runs autoflake.

    Autoflake removes unused imports and variables among other
    things. Reads autoflake arguments from pyproject.toml. Arguments are
    specified by their full name, with underscores or dashes - either style is
    accepted.
    """

    def _make_autoflake_args(self: AutoflakeRunner) -> list[str]:
        args: list[str] = []

        for key, val in self.config.items():
            if key == "src_paths":
                for src in val:
                    args.append(src)

                continue

            opt: str = f"--{key.replace('_', '-')}"

            if isinstance(val, bool):
                args.append(opt)

                continue

            args.append(f"{opt}={val}")

        return args

    def run(self: AutoflakeRunner) -> ToolResult:
        """Run autoflake."""
        logger: Logger = self.make_logger(TextIOLogger, logging.INFO)
        autoflake_args: list[str] = self._make_autoflake_args()
        if all(cfgval.startswith("--") for cfgval in autoflake_args):
            autoflake_args.extend([str(p) for p in self.src_paths])

        retcode: int = autoflake_main(
            [self._tool.value, *autoflake_args], logger, logger
        )

        return ToolResult.SUCCESS if retcode == 0 else ToolResult.FAILURE


@dataclass
class ISortResult:
    """Isort run result.

    Encapsulates a result from an isort run: the Python file, the ToolResult,
    and an error message (if and when applicable).
    """

    pyfile: Path
    result: ToolResult
    errmsg: str = field(default="")

    def __hash__(self) -> int:
        """Hashes all attributes of the dataclass."""
        return hash(f"{self.pyfile}{self.result.value}{self.errmsg}")


class ISortRunner(ToolRunner):
    """Runs isort.

    Isort is able to sort imports in a Python source file according to a defined
    rule set (with sensible defaults).
    """

    # pylint: disable=too-many-branches
    def run(self: ISortRunner) -> ToolResult:
        """Run isort."""
        logger: Logger = self.make_logger(ToolLogger, logging.INFO)
        results: set[ISortResult] = set()

        isort_logger: TextIOLogger = cast(
            TextIOLogger, self.make_logger(TextIOLogger, logging.INFO)
        )

        # fmt: off
        for file in isort_files.find(
            [str(p) for p in self.src_paths]
            or cast(Iterable[str], DEFAULT_CONFIG.src_paths),
            DEFAULT_CONFIG, [], [],
        ):
            try:
                with patch("sys.stdout", isort_logger):
                    isort_file(file)

                results.add(ISortResult(Path(file), ToolResult.SUCCESS))
            # pylint: disable=broad-except
            except Exception as ex:
                results.add(ISortResult(
                    Path(file), ToolResult.FAILURE,
                    getattr(ex, "message") if hasattr(ex, "message") else "",
                ))
        # fmt: on

        failed: set[ISortResult] = set()
        for isort_result in results:
            if isort_result.result == ToolResult.FAILURE:
                failed.add(isort_result)

        if len(failed) > 0:
            logger.error("isort failed on some files:")

            for failed_result in failed:
                logger.error(f"{failed_result.pyfile}: {failed_result.errmsg}")

        if len(failed) == len(results):
            return ToolResult.FAILURE

        if 0 < len(failed) < len(results):
            return ToolResult.SUCCESS_PARTIAL

        return ToolResult.SUCCESS


class BlackRunner(ToolRunner):
    """Runs black.

    Black is an opinionated code formatter.
    """

    def run(self: BlackRunner) -> ToolResult:
        """Run black."""
        iologger: Logger = self.make_logger(TextIOLogger, logging.INFO)
        sys_stdout_orig = sys.stdout
        sys_stderr_orig = sys.stderr

        try:
            sys.stdout = cast(TextIO, iologger)
            sys.stderr = cast(TextIO, iologger)
            # pylint: disable=no-value-for-parameter
            black_main([str(p) for p in self.src_paths])

            return ToolResult.SUCCESS

        except SystemExit as sysexit:
            return ToolResult.SUCCESS if sysexit.code == 0 else ToolResult.FAILURE

        finally:
            sys.stdout = sys_stdout_orig
            sys.stderr = sys_stderr_orig


class MypyRunner(ToolRunner):
    """Runs Mypy.

    Mypy is a static type checker for Python.
    """

    def run(self: MypyRunner) -> ToolResult:
        """Run mypy."""
        logger: TextIOLogger = cast(
            TextIOLogger, self.make_logger(TextIOLogger, logging.INFO)
        )

        logger_as_textio: TextIO = cast(TextIO, logger)

        try:
            mypy_main(None, logger_as_textio, logger_as_textio)

            return ToolResult.SUCCESS

        except SystemExit as sysexit:
            return ToolResult.SUCCESS if sysexit.code == 0 else ToolResult.FAILURE


class PylintRunner(ToolRunner):
    """Runs pylint."""

    def run(self: PylintRunner) -> ToolResult:
        """Run pylint."""
        with patch("sys.stdout", self.make_logger(TextIOLogger, logging.INFO)):
            try:
                PylintRun([str(p) for p in self.src_paths])

                return ToolResult.SUCCESS

            except SystemExit as sysexit:
                return ToolResult.SUCCESS if sysexit.code == 0 else ToolResult.FAILURE


class PydocstyleRunner(ToolRunner):
    """Runs pydocstyle.

    Pydocstyle checks for best practices for writing Python documentation within
    source code.
    """

    def run(self: PydocstyleRunner) -> ToolResult:
        """Run pydocstyle."""

        class InfoToolLogger(ToolLogger):
            """Disobedient logger that stays at the specified level.

            Shim logger to default to a specified level regardless of level
            passed.
            """

            def setLevel(self: InfoToolLogger, _: int | str) -> None:
                self.level = logging.INFO

        info_logger: InfoToolLogger = InfoToolLogger(self._tool.value, logging.INFO)
        pydocstyle_log_orig: Logger = pydocstyle.utils.log
        try:
            pydocstyle.utils.log = info_logger
            pydocstyle.checker.log = info_logger
            # pylint: disable=import-outside-toplevel
            from pydocstyle.cli import run_pydocstyle as pydocstyle_main  # type: ignore

            with patch("sys.stdout", self.make_logger(TextIOLogger, logging.INFO)):
                return [
                    ToolResult.SUCCESS,
                    ToolResult.SUCCESS_PARTIAL,
                    ToolResult.FAILURE,
                ][pydocstyle_main()]

        finally:
            pydocstyle.utils.log = pydocstyle_log_orig
            pydocstyle.checker.log = pydocstyle_log_orig


class PyupgradeRunner(ToolRunner):
    """Runs Pyupgrade.

    Pyupgrade automatically upgrades Python syntax to the latest for the
    specified Python version.
    """

    def _validate_config(self: PyupgradeRunner) -> None:
        if "min_version" in self.config and not re.match(
            r"^[0-9].[0-9]", self.config["min_version"]
        ):
            raise ValueError("min_version must be a valid Python version!")

    def run(self: PyupgradeRunner) -> ToolResult:
        """Run Pyupgrade."""
        self._validate_config()

        logger: ToolLogger = self.make_logger(TextIOLogger, logging.INFO)

        with patch("sys.stdout", logger), patch("sys.stderr", logger):
            retcode: int = 0
            for src_path in [p for p in self.src_paths if p.is_file()]:
                retcode |= pyupgrade_fix_file(
                    src_path,
                    Namespace(
                        exit_zero_even_if_changed=self.config.get(
                            "exit_zero_even_if_changed", None
                        ),
                        keep_mock=self.config.get("keep_mock", None),
                        keep_percent_format=self.config.get(
                            "keep_percent_format", None
                        ),
                        keep_runtime_typing=self.config.get(
                            "keep_runtime_typing", None
                        ),
                        min_version=tuple(
                            int(v)
                            for v in cast(
                                str, self.config.get("min_version", "2.7")
                            ).split(".")
                        ),
                    ),
                )

            return ToolResult.SUCCESS if retcode == 0 else ToolResult.FAILURE


def find_pyproject_toml(path: Path = Path(".")) -> Path | None:
    """Discover closest pyproject.toml.

    Finds the first pyproject.toml by searching in the current directory,
    traversing upward to the filesystem root if not found.
    """
    if path == Path("/"):
        return None

    filepath: Path = path / PYPROJECT_TOML_FILENAME

    if filepath.exists() and filepath.is_file():
        return path / PYPROJECT_TOML_FILENAME

    return find_pyproject_toml(path.resolve().parent)


def parse_pyproject_toml(pyproject_toml_path: Path = Path(".")) -> Mapping[str, Any]:
    """Parse pyproject.toml into a config map.

    Reads in the pyproject.toml file and returns a parsed version of it as a
    Mapping.
    """
    pyproject_toml: Path | None = find_pyproject_toml(pyproject_toml_path)
    if pyproject_toml is None:
        return {}

    with pyproject_toml.open("r") as file:
        return toml.load(file)


def expand_src_paths(src_paths: Seq[Path]) -> list[Path]:
    """Expand source paths in case they are globs."""
    return sum(
        (
            [Path(ge) for ge in glob(p.name)] if "*" in p.name else [p]
            for p in src_paths
        ),
        [],
    )


TOOL_RUNNERS: Mapping[Tool, type[ToolRunner]] = {
    Tool.AUTOFLAKE: AutoflakeRunner,
    Tool.BLACK: BlackRunner,
    Tool.ISORT: ISortRunner,
    Tool.MYPY: MypyRunner,
    Tool.PYDOCSTYLE: PydocstyleRunner,
    Tool.PYLINT: PylintRunner,
    Tool.PYUPGRADE: PyupgradeRunner,
}


class Multilint:
    """The core logic of this project.

    Multilint ties together multiple linting and other code quality tools
    under a single interface, the ToolRunner base class. By subclassing
    ToolRunner and implementing its .run() method, adding support for linters /
    other tool plugins is easy.
    """

    DEFAULT_TOOL_ORDER: Seq[Tool] = [
        Tool.PYUPGRADE,
        Tool.AUTOFLAKE,
        Tool.ISORT,
        Tool.BLACK,
        Tool.MYPY,
        Tool.PYLINT,
        Tool.PYDOCSTYLE,
    ]

    def __init__(
        self: Multilint,
        src_paths: Seq[Path] = [Path(".")],
        pyproject_toml_path: Path = Path(".") / PYPROJECT_TOML_FILENAME,
    ) -> None:
        """Construct a new Multilint instance."""
        self._config: Mapping[str, Any] = {}
        self._config = parse_pyproject_toml(pyproject_toml_path)

        self._multilint_config = self._get_tool_config(Tool.MULTILINT)
        self._src_paths: Seq[Path] = (
            src_paths
            if len(src_paths) > 0
            else self._multilint_config.get("src_paths", ["."])
        )

        self._tool_order: Seq[Tool] = [
            Tool(t) for t in self._multilint_config.get("tool_order", [])
        ]
        if len(self._tool_order) == 0:
            self._tool_order = self.DEFAULT_TOOL_ORDER

    def _get_tool_config(self: Multilint, tool: Tool) -> Mapping[str, Any]:
        return self._config.get("tool", {}).get(tool.value, {})

    def run_tool(self: Multilint, tool: Tool) -> ToolResult:
        """Run a single CQ tool.

        Runs a single specified linter or other code quality tool. Returns
        a ToolResult from the run.
        """
        LOGGER.info(f"Running {tool.value}...")
        tool_config: Mapping[str, Any] = self._get_tool_config(tool)

        # fmt: off
        result: ToolResult = cast(ToolRunner, TOOL_RUNNERS[tool](
            tool,
            expand_src_paths(
                [Path(sp) for sp in tool_config.get("src_paths", self._src_paths)]
            ),
            tool_config,
        )).run()
        # fmt: on

        LOGGER.info(f"{tool.value} exited with {result}")

        return result

    def run_all_tools(
        self: Multilint, order: Seq[Tool] = None
    ) -> Mapping[Tool, ToolResult]:
        """Run tools in specified order."""
        results: dict[Tool, ToolResult] = {}

        if order is None:
            order = self._tool_order

        for tool in order:
            results[tool] = self.run_tool(tool)

        return results


def main(
    src_paths: Seq[Path] = [Path(p) for p in sys.argv[1:]], do_exit: bool = True  # type: ignore
) -> int | None:
    """Acts as the default entry point for Multilint.

    The main / default entry point to multilint. Runs all tools and logs
    their results.
    """
    results: Mapping[Tool, ToolResult] = Multilint(src_paths).run_all_tools()

    LOGGER.info("Results:")
    for tool, result in results.items():
        LOGGER.info(f"{tool}: {result}")

    retcode: int = 0 if all(r == ToolResult.SUCCESS for r in results.values()) else 1

    if do_exit:
        sys.exit(retcode)

    return retcode


if __name__ == "__main__":
    sys.exit(main([Path(arg) for arg in sys.argv[1:]]))
