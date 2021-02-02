#!/usr/bin/env python3
"""
Multilint is a runner for multiple code quality tools.

Multilint enables running various Python linters (and other CQ tools) under the
same interface, making it easier to configure and run all code quality tools
from a centralized location.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from glob import glob
from io import TextIOBase
from logging import Formatter, Logger, StreamHandler
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from typing import Sequence as Seq
from typing import Set, TextIO, Type, TypeVar, Union, cast
from unittest.mock import patch

import black
import click
import pydocstyle  # type: ignore
import toml
from autoflake import _main as autoflake_main  # type: ignore
from black import main as black_main
from isort import files as isort_files  # type: ignore
from isort.api import sort_file as isort_file  # type: ignore
from isort.settings import DEFAULT_CONFIG  # type: ignore
from mypy.main import main as mypy_main
from pylint.lint import Run as PylintRun  # type: ignore

FILE_DIR: Path = Path(__file__).resolve().parent
ROOT_DIR: Path = FILE_DIR
PYPROJECT_TOML_FILENAME: str = "pyproject.toml"

LogLevel = TypeVar("LogLevel", bound=int)

LOG_FMT: str = "%(asctime)s [%(levelname)s] [%(name)s] %(msg)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
LOGGER: logging.Logger = logging.getLogger("multilint")


class Tool(Enum):
    """The Tool enum.

    Encapsulates all supported linters, including Multilint itself.
    """

    AUTOFLAKE: str = "autoflake"
    BLACK: str = "black"
    ISORT: str = "isort"
    MYPY: str = "mypy"
    MULTILINT: str = "multilint"
    PYLINT: str = "pylint"
    PYDOCSTYLE: str = "pydocstyle"


class ToolResult(Enum):
    """ToolResult describes a generic run result from a code quality tool."""

    SUCCESS: int = auto()
    SUCCESS_PARTIAL: int = auto()
    FAILURE: int = auto()


class ToolLogger(Logger):
    """ToolLogger allows setting the format on itself during instantiation."""

    def __init__(
        self: ToolLogger, name: str, level: LogLevel, logfmt: str = LOG_FMT
    ) -> None:
        """Create a ToolLogger with the specified name, level, and format.

        Format gets applied immediately.
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


# pylint: disable=too-many-ancestors
class TextIOLogger(TextIOBase, ToolLogger):
    """Logger object that can be written to like a stream-like object.

    A logger that masquerades as a TextIO-compatible object, allowing it to be
    passed into code quality tools that write to TextIO interfaces. This way,
    it is possible to wrap the stdout / stderr / other streams with our
    commong logging.
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
        self._src_paths: Seq[Path] = src_paths
        self._config: Mapping[str, Any] = config

    def make_logger(
        self: ToolRunner,
        cls: Union[Type[ToolLogger], Type[TextIOLogger]],
        level: LogLevel,
    ) -> Union[ToolLogger, TextIOLogger]:
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

    def _make_autoflake_args(self: AutoflakeRunner) -> List[str]:
        args: List[str] = []

        for key, val in self._config.items():
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
        autoflake_args: List[str] = self._make_autoflake_args()

        if all([cfgval.startswith("--") for cfgval in autoflake_args]):
            autoflake_args.extend([str(p) for p in self._src_paths])

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

    def run(self: ISortRunner) -> ToolResult:
        """Run isort."""
        logger: Logger = self.make_logger(ToolLogger, logging.INFO)
        results: Set[ISortResult] = set()

        isort_logger: TextIOLogger = cast(
            TextIOLogger, self.make_logger(TextIOLogger, logging.INFO)
        )

        for file in isort_files.find(
            self._src_paths or DEFAULT_CONFIG.src_paths, DEFAULT_CONFIG, [], []
        ):
            try:
                with patch("sys.stdout", isort_logger):
                    isort_file(file)

                results.add(ISortResult(Path(file), ToolResult.SUCCESS))

            # pylint: disable=broad-except
            except Exception as ex:
                results.add(
                    ISortResult(
                        Path(file),
                        ToolResult.FAILURE,
                        getattr(ex, "message") if hasattr(ex, "message") else "",
                    )
                )

        failed: Set[ISortResult] = set()
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
        logger: Logger = self.make_logger(ToolLogger, logging.DEBUG)

        # pylint: disable=unsubscriptable-object
        def secho_shim(message: Optional[str], **_: Mapping[Any, Any]):
            logger.info(message)

        click_secho_orig = click.secho
        black_out_orig = black.out
        black_err_orig = black.err

        try:
            click.secho = secho_shim  # type: ignore
            black.out = logger.info  # type: ignore
            black.err = logger.warn  # type: ignore

            # pylint: disable=no-value-for-parameter
            black_main([str(p) for p in self._src_paths] or ["."])

            return ToolResult.SUCCESS

        except SystemExit as exit:
            return ToolResult.SUCCESS if exit.code == 0 else ToolResult.FAILURE

        finally:
            click.secho = click_secho_orig
            black.out = black_out_orig
            black.err = black_err_orig


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
            mypy_main(
                None,
                logger_as_textio,
                logger_as_textio,
                [str(p) for p in self._src_paths]
                or self._config.get("src_paths", ["."]),
            )

            return ToolResult.SUCCESS

        except SystemExit as exit:
            return ToolResult.SUCCESS if exit.code == 0 else ToolResult.FAILURE


class PylintRunner(ToolRunner):
    """Runs pylint."""

    def run(self: PylintRunner) -> ToolResult:
        """Run pylint."""
        with patch("sys.stdout", self.make_logger(TextIOLogger, logging.INFO)):
            try:
                PylintRun([str(p) for p in self._src_paths] or ["."])

                return ToolResult.SUCCESS

            except SystemExit as exit:
                return ToolResult.SUCCESS if exit.code == 0 else ToolResult.FAILURE


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

            # pylint: disable=unsubscriptable-object
            def setLevel(self: InfoToolLogger, _: Union[int, str]) -> None:
                self.level = logging.INFO

        info_logger: InfoToolLogger = InfoToolLogger(self._tool.value, logging.INFO)
        pydocstyle_log_orig: Logger = pydocstyle.utils.log
        try:
            pydocstyle.utils.log = info_logger
            pydocstyle.checker.log = info_logger

            # Have to import here so the patching above works
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


def find_pyproject_toml(path: Path = Path(".")) -> Path:
    """Discover closest pyproject.toml.

    Finds the first pyproject.toml by searching in the current directory,
    traversing upward to the filesystem root if not found.
    """
    filepath: Path = path / PYPROJECT_TOML_FILENAME

    if filepath.exists() and filepath.is_file():
        return path / PYPROJECT_TOML_FILENAME

    if path == Path("/"):
        raise RuntimeError("No pyproject.toml found!")

    return find_pyproject_toml(path.parent)


def parse_pyproject_toml(pyproject_toml_path: Path = Path(".")) -> Mapping[str, Any]:
    """Parse pyproject.toml into a config map.

    Reads in the pyproject.toml file and returns a parsed version of it as a
    Mapping.
    """
    with find_pyproject_toml(pyproject_toml_path).open("r") as file:
        return toml.load(file)


def expand_src_paths(src_paths: Seq[Path]) -> List[Path]:
    """Expand source paths in case they are globs."""
    return sum([[Path(ge) for ge in glob(p.name)] for p in src_paths], [])


TOOL_RUNNERS: Mapping[Tool, Type[ToolRunner]] = {
    Tool.AUTOFLAKE: AutoflakeRunner,
    Tool.ISORT: ISortRunner,
    Tool.BLACK: BlackRunner,
    Tool.MYPY: MypyRunner,
    Tool.PYLINT: PylintRunner,
    Tool.PYDOCSTYLE: PydocstyleRunner,
}


class Multilint:
    """The core logic of this project.

    Multilint ties together multiple linting and other code quality tools
    under a single interface, the ToolRunner base class. By subclassing
    ToolRunner and implementing its .run() method, adding support for linters /
    other tool plugins is easy.
    """

    DEFAULT_TOOL_ORDER: Seq[Tool] = [
        Tool.AUTOFLAKE,
        Tool.ISORT,
        Tool.BLACK,
        Tool.MYPY,
        Tool.PYLINT,
        Tool.PYDOCSTYLE,
    ]

    def __init__(
        self: Multilint,
        src_paths: Seq[Path] = [],
        pyproject_toml_path: Path = Path(".") / PYPROJECT_TOML_FILENAME,
    ) -> None:
        """Construct a new Multilint instance."""
        self._config: Mapping[str, Any] = parse_pyproject_toml(pyproject_toml_path)
        self._multilint_config = self._get_tool_config(Tool.MULTILINT)
        self._src_paths: Seq[Path] = expand_src_paths(
            src_paths
            if src_paths != []
            else [
                Path(sp) for sp in self._multilint_config.get("src_paths", [Path(".")])
            ],
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

        result: ToolResult = cast(
            ToolRunner,
            TOOL_RUNNERS[tool](tool, self._src_paths, self._get_tool_config(tool)),
        ).run()

        LOGGER.info(f"{tool.value} exited with {result}")

        return result

    def run_all_tools(
        self: Multilint, order: Seq[Tool] = None
    ) -> Mapping[Tool, ToolResult]:
        """Run tools in specified order."""
        results: Dict[Tool, ToolResult] = {}

        if order is None:
            order = self._tool_order

        for tool in order:
            results[tool] = self.run_tool(tool)

        return results


# pylint: disable=unsubscriptable-object
def main(argv: Seq[str] = [], do_exit: bool = True) -> Optional[int]:
    """Acts as the default entry point for Multilint.

    The main / default entry point to multilint. Runs all tools and logs
    their results.
    """
    results: Mapping[Tool, ToolResult] = Multilint(
        [Path(p) for p in argv]
    ).run_all_tools()

    LOGGER.info("Results:")
    for tool, result in results.items():
        LOGGER.info(f"{tool}: {result}")

    retcode: int = 0 if all([r == ToolResult.SUCCESS for r in results.values()]) else 1

    if do_exit:
        sys.exit(retcode)

    return retcode


if __name__ == "__main__":
    main(sys.argv[1:] if len(sys.argv) > 1 else ".")
