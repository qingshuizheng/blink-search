#!/usr/bin/env python3
"""The small helpers both halves of blink-search need.

Everything in here talks to Emacs over EPC, runs a command, or reshapes the
data that crosses the boundary.  Nothing in here knows about a backend, so the
module can be imported (and tested) without an Emacs on the other end.

The Python process is started by Emacs and is handed the port of the EPC
server Emacs listens on; `init_epc_client' opens the connection back to it and
every `eval_in_emacs' goes through that one connection.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from typing import Any, List, Optional

import sexpdata
from epc.client import EPCClient

try:
    import orjson as json_parser
except ImportError:
    import json as json_parser

#: The one connection back to the Emacs that started this process.
epc_client: Optional[EPCClient] = None

logger = logging.getLogger("blink-search")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())


def init_epc_client(emacs_server_port: int) -> None:
    """Connect back to the EPC server Emacs listens on at EMACS-SERVER-PORT.

    A refused connection is logged and swallowed: Emacs may already be gone,
    and there is nothing useful the search process can do about it.
    """
    global epc_client  # pylint: disable=global-statement

    if epc_client is None:
        try:
            epc_client = EPCClient(("127.0.0.1", emacs_server_port), log_traceback=True)
        except ConnectionRefusedError:
            import traceback
            logger.error(traceback.format_exc())


def close_epc_client() -> None:
    """Close the connection back to Emacs, if it was ever opened."""
    if epc_client is not None:
        epc_client.close()


def handle_arg_types(arg: Any) -> Any:
    """Return ARG as the value that should appear in an `eval-in-emacs' form.

    The form is `eval'ed on the Emacs side, so the value has to be protected
    from that evaluation when reading it as a value would not give the value
    back:

    * a string that starts with a quote names an Emacs function, and is
      passed as the symbol it names;
    * a list is quoted, because a list whose first element is a keyword (the
      plist of a candidate, or the list of those plists) would otherwise be
      read as a function call and fail with `invalid-function';
    * numbers, strings and symbols evaluate to themselves, so they are
      passed as they are.

    This is the line between a menu that fills and a menu that stays empty:
    the candidate rows are a list of plists, and every one of them needs the
    quote.
    """
    if type(arg) is str and arg.startswith("'"):
        return sexpdata.Symbol(arg.partition("'")[2])

    if isinstance(arg, list):
        return sexpdata.Quoted(arg)

    return arg


def eval_in_emacs(method_name: str, *args: Any) -> None:
    """Call the Elisp METHOD-NAME with ARGS, asynchronously.

    The arguments are printed as a Lisp form and `eval'ed by
    `blink-search--eval-in-emacs-func' on the Emacs side, which is what makes
    a Python list of dictionaries arrive as a list of plists.
    """
    sexp_args = [sexpdata.Symbol(method_name)] + [handle_arg_types(arg) for arg in args]
    sexp = sexpdata.dumps(sexp_args)

    logger.debug("Eval in Emacs: %s", sexp)
    epc_client.call("eval-in-emacs", [sexp])  # type: ignore[union-attr]


def message_emacs(message: str) -> None:
    """Show MESSAGE in the Emacs echo area, prefixed with the package name."""
    eval_in_emacs("message", "[Blink-Search] " + message)


def convert_emacs_bool(symbol_value: Any, symbol_is_boolean: Any) -> Any:
    """Turn one Emacs value into the Python value it stands for.

    SYMBOL-IS-BOOLEAN is the flag Emacs sends next to the value, because EPC
    cannot tell nil from an empty list on its own.
    """
    if symbol_is_boolean == "t":
        return symbol_value is True
    return symbol_value


def get_emacs_vars(args: List[str]) -> List[Any]:
    """Return the values of the Emacs variables named in ARGS, in order."""
    return list(map(lambda result: convert_emacs_bool(result[0], result[1]) if result != [] else False,
                    epc_client.call_sync("get-emacs-vars", args)))  # type: ignore[union-attr]


def get_emacs_var(var_name: str) -> Any:
    """Return the value of the Emacs variable named VAR-NAME."""
    value = epc_client.call_sync("get-emacs-var", [var_name])  # type: ignore[union-attr]
    symbol_value = value[0]
    symbol_is_boolean = value[1]

    return convert_emacs_bool(symbol_value, symbol_is_boolean)


def get_command_result(command_string: str, cwd: Optional[str] = None) -> str:
    """Run COMMAND-STRING in CWD and return its output, or an empty string.

    A command that exits non-zero, or that cannot be started at all, is
    treated as an empty result: every caller of this function is looking for
    an optional piece of information.
    """
    try:
        process = subprocess.Popen(command_string, cwd=cwd, shell=True, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding="utf-8")
    except OSError:
        return ""

    ret = process.wait()
    if ret == 0:
        return "".join(process.stdout.readlines()).strip()  # type: ignore[union-attr]
    return ""


def get_project_path(search_dir: str) -> str:
    """Return the root of the git project SEARCH-DIR is in.

    A directory that is not inside a git project is returned unchanged, so
    the caller can always use the result as the directory to search.
    """
    search_path = os.path.expanduser(search_dir)
    git_project_path = get_command_result("git rev-parse --show-toplevel", search_path)
    if os.path.exists(git_project_path):
        return git_project_path
    return search_path


def get_os_name() -> str:
    """Return the lower case name of the platform this process runs on."""
    return platform.system().lower()


def parse_json_content(content: str) -> Any:
    """Parse the JSON document CONTENT, with orjson when it is installed."""
    return json_parser.loads(content)


def touch(path: str) -> None:
    """Create PATH and its parent directory when they do not exist yet."""
    if not os.path.exists(path):
        basedir = os.path.dirname(path)

        if basedir and not os.path.exists(basedir):
            os.makedirs(basedir)

        with open(path, "a", encoding="utf-8"):
            os.utime(path, None)


def parse_rg_line(line: str, search_path: Optional[str] = None) -> Optional[dict]:
    """Turn one line of ripgrep's `--json' output into a candidate.

    SEARCH-PATH, when given, is the directory the search started from: the
    candidate then starts with the path of the match relative to it, so that
    two files with the same name can be told apart in the menu.  A line that
    is not a match, or that cannot be parsed, returns None.

    The returned dictionary holds the text of the candidate and the byte
    offsets of every submatch inside it, which is what the Elisp half
    highlights.
    """
    try:
        info = json.loads(line)
        if info["type"] == "match":

            if search_path is not None:
                prefix = "{}:{}:{}: ".format(
                    os.path.relpath(info["data"]["path"]["text"], search_path),
                    info["data"]["line_number"],
                    info["data"]["submatches"][0]["start"])
            else:
                prefix = "{}:{}: ".format(
                    info["data"]["line_number"],
                    info["data"]["submatches"][0]["start"])

            lines = info["data"]["lines"]
            text_key = list(lines.keys())[0]
            candidate = "{}{}".format(prefix, info["data"]["lines"][text_key][:-1])
            prefix_len = len(prefix.encode())  # chinese filenames...
            matches = list(map(lambda match: [match["start"] + prefix_len, match["end"] + prefix_len],
                               info["data"]["submatches"]))
            return {"text": candidate, "matches": matches}
    except Exception:  # pylint: disable=broad-except
        return None

    return None


def insert_unique_string_to_file(filepath: str, string: str) -> None:
    """Append STRING to FILEPATH unless a line already holds exactly STRING."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
        content = file.readlines()

    string_exists = any(line == string + "\n" for line in content)

    if not string_exists:
        with open(filepath, "a", encoding="utf-8", errors="ignore") as file:
            file.write(string + "\n")


def windows_get_env_value(var_name: str) -> Optional[str]:
    """Return the Windows environment variable VAR-NAME, or None."""
    if var_name in os.environ.keys():
        return os.environ[var_name]
    return None


def windows_parse_path(path: str) -> str:
    """Expand the %USERPROFILE% placeholder in PATH, on Windows."""
    return path.replace("%USERPROFILE%", windows_get_env_value("USERPROFILE"))


def _make_uri_win32(path) -> str:
    """Return the file URI of PATH on Windows.

    This is a copy of the private helper of `pathlib', because pathlib does
    not expose it and `Path.as_uri' is not enough for the drive-letter form
    Emacs expects.
    """
    from urllib.parse import quote_from_bytes as urlquote_from_bytes
    # Under Windows, file URIs use the UTF-8 encoding.
    drive = path.drive
    if len(drive) == 2 and drive[1] == ':':
        # It's a path on a local drive => 'file:///c:/a/b'
        rest = path.as_posix()[2:].lstrip('/')
        return 'file:///%s%%3A/%s' % (
            drive[0], urlquote_from_bytes(rest.encode('utf-8')))
    # It's a path on a network drive => 'file://host/share/a/b'
    return 'file:' + urlquote_from_bytes(path.as_posix().encode('utf-8'))


def path_to_uri(path: str) -> str:
    """Return the `file:' URI of PATH, with the Windows form Emacs expects."""
    import pathlib
    path_object = pathlib.Path(path)
    if get_os_name() != "windows":
        return path_object.as_uri()

    if not path_object.is_absolute():
        raise ValueError("relative path can't be expressed as a file URI")
    return _make_uri_win32(path_object)


def uri_to_path(uri: str) -> str:
    """Return the file path a `file:' URI names."""
    from urllib.parse import unquote, urlparse
    # parse first, '#' may be part of filepath(encoded)
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if sys.platform == "win32":
        path = path[1:]
    return path
