Module multilint
================
Multilint is a runner for multiple code quality tools.

Multilint enables running various Python linters (and other CQ tools) under the
same interface, making it easier to configure and run all code quality tools
from a centralized location.

Functions
---------

    
`expand_src_paths(src_paths: Seq[Path]) ‑> list[pathlib.Path]`
:   Expand source paths in case they are globs.

    
`find_pyproject_toml(path: Path = PosixPath('.')) ‑> pathlib.Path | None`
:   Discover closest pyproject.toml.
    
    Finds the first pyproject.toml by searching in the current directory,
    traversing upward to the filesystem root if not found.

    
`main(src_paths: Seq[Path] = [PosixPath('multilint.py'), PosixPath('-o'), PosixPath('docs'), PosixPath('--force')], do_exit: bool = True) ‑> int | None`
:   Acts as the default entry point for Multilint.
    
    The main / default entry point to multilint. Runs all tools and logs
    their results.

    
`parse_pyproject_toml(pyproject_toml_path: Path = PosixPath('.')) ‑> Mapping[str, Any]`
:   Parse pyproject.toml into a config map.
    
    Reads in the pyproject.toml file and returns a parsed version of it as a
    Mapping.

Classes
-------

`AutoflakeRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs autoflake.
    
    Autoflake removes unused imports and variables among other
    things. Reads autoflake arguments from pyproject.toml. Arguments are
    specified by their full name, with underscores or dashes - either style is
    accepted.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: AutoflakeRunner) ‑> multilint.ToolResult`
    :   Run autoflake.

`BlackRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs black.
    
    Black is an opinionated code formatter.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: BlackRunner) ‑> multilint.ToolResult`
    :   Run black.

`ISortResult(pyfile: Path, result: ToolResult, errmsg: str = '')`
:   Isort run result.
    
    Encapsulates a result from an isort run: the Python file, the ToolResult,
    and an error message (if and when applicable).

    ### Class variables

    `errmsg: str`
    :

    `pyfile: pathlib.Path`
    :

    `result: multilint.ToolResult`
    :

`ISortRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs isort.
    
    Isort is able to sort imports in a Python source file according to a defined
    rule set (with sensible defaults).
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: ISortRunner) ‑> multilint.ToolResult`
    :   Run isort.

`Multilint(src_paths: Seq[Path] = [PosixPath('.')], pyproject_toml_path: Path = PosixPath('pyproject.toml'))`
:   The core logic of this project.
    
    Multilint ties together multiple linting and other code quality tools
    under a single interface, the ToolRunner base class. By subclassing
    ToolRunner and implementing its .run() method, adding support for linters /
    other tool plugins is easy.
    
    Construct a new Multilint instance.

    ### Class variables

    `DEFAULT_TOOL_ORDER: Sequence[multilint.Tool]`
    :

    ### Methods

    `run_all_tools(self: Multilint, order: Seq[Tool] = None) ‑> Mapping[multilint.Tool, multilint.ToolResult]`
    :   Run tools in specified order.

    `run_tool(self: Multilint, tool: Tool) ‑> multilint.ToolResult`
    :   Run a single CQ tool.
        
        Runs a single specified linter or other code quality tool. Returns
        a ToolResult from the run.

`MypyRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs Mypy.
    
    Mypy is a static type checker for Python.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: MypyRunner) ‑> multilint.ToolResult`
    :   Run mypy.

`PydocstyleRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs pydocstyle.
    
    Pydocstyle checks for best practices for writing Python documentation within
    source code.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: PydocstyleRunner) ‑> multilint.ToolResult`
    :   Run pydocstyle.

`PylintRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs pylint.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: PylintRunner) ‑> multilint.ToolResult`
    :   Run pylint.

`PyupgradeRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Runs Pyupgrade.
    
    Pyupgrade automatically upgrades Python syntax to the latest for the
    specified Python version.
    
    Initialize a ToolRunner object.

    ### Ancestors (in MRO)

    * multilint.ToolRunner

    ### Methods

    `run(self: PyupgradeRunner) ‑> multilint.ToolResult`
    :   Run Pyupgrade.

`TextIOLogger(name: str, level: LogLevel, logfmt: str = '%(asctime)s [%(levelname)s] [%(name)s] %(msg)s')`
:   Logger object that can be written to like a stream-like object.
    
    A logger that masquerades as a TextIO-compatible object, allowing it to be
    passed into code quality tools that write to TextIO interfaces. This way,
    it is possible to wrap the stdout / stderr / other streams with our
    common logging.
    
    Construct a TextIOLogger.

    ### Ancestors (in MRO)

    * io.TextIOBase
    * _io._TextIOBase
    * io.IOBase
    * _io._IOBase
    * multilint.ToolLogger
    * logging.Logger
    * logging.Filterer

    ### Methods

    `write(self: TextIOLogger, msg: str) ‑> int`
    :   Write data to the logger as if it were a stream-like object.
        
        The write() method is implemented to forward data to the logging
        part of this object, allowing capturing logs that would normally be
        written to stdout / stderr.

`Tool(value, names=None, *, module=None, qualname=None, type=None, start=1)`
:   Encapsulates all supported linters, including Multilint itself.

    ### Ancestors (in MRO)

    * enum.Enum

    ### Class variables

    `AUTOFLAKE`
    :

    `BLACK`
    :

    `ISORT`
    :

    `MULTILINT`
    :

    `MYPY`
    :

    `PYDOCSTYLE`
    :

    `PYLINT`
    :

    `PYUPGRADE`
    :

`ToolLogger(name: str, level: LogLevel, logfmt: str = '%(asctime)s [%(levelname)s] [%(name)s] %(msg)s')`
:   ToolLogger allows setting format on itself during instantiation.
    
    Create a ToolLogger with the specified name, level, and format.
    
    Log format gets applied immediately.

    ### Ancestors (in MRO)

    * logging.Logger
    * logging.Filterer

    ### Descendants

    * multilint.TextIOLogger

    ### Methods

    `set_format(self: ToolLogger, fmtstr: str) ‑> None`
    :   Set the specified log message format.
        
        Uses a StreamHandler by setting a formatter on it with the specified
        format string, and adds the StreamHanlder to the logger instance.

`ToolResult(value, names=None, *, module=None, qualname=None, type=None, start=1)`
:   ToolResult describes a generic run result from a code quality tool.

    ### Ancestors (in MRO)

    * enum.Enum

    ### Class variables

    `FAILURE`
    :

    `SUCCESS`
    :

    `SUCCESS_PARTIAL`
    :

`ToolRunner(tool: Tool, src_paths: Seq[Path] = [PosixPath('.')], config: Mapping[str, Any] = {})`
:   Base class for integrating code quality tools.
    
    ToolRunner is a base class for any plugin that integrates a code quality
    tool. Subclasses only have to implement the run() method. There is a
    convenience method available,
    
    Initialize a ToolRunner object.

    ### Descendants

    * multilint.AutoflakeRunner
    * multilint.BlackRunner
    * multilint.ISortRunner
    * multilint.MypyRunner
    * multilint.PydocstyleRunner
    * multilint.PylintRunner
    * multilint.PyupgradeRunner

    ### Methods

    `make_logger(self: ToolRunner, cls: type[ToolLogger] | type[TextIOLogger], level: LogLevel) ‑> multilint.ToolLogger | multilint.TextIOLogger`
    :   Create a logger for the ToolRunner object.
        
        Creates a logger object from the specified logger class (can be
        either a ToolLogger or a TextIOLogger) with the specified default log
        level.

    `run(self: ToolRunner) ‑> multilint.ToolResult`
    :   Is implemented by subclasses to run the CQ (code quality) tool.