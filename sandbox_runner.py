"""
Runs inside an isolated subprocess (python -I -S) with no environment
variables and OS resource limits already applied by the parent process.
Reads a JSON payload from stdin: {"code", "function_name", "tests": [{"args": [...]}]}.
Writes a single JSON line to stdout: {"results": [{"actual", "error"}, ...]}
or {"compile_error": "..."} if the submitted code itself fails to define
the target function.

Only a small allowlist of standard-library modules can be imported from
submitted code, and only a safe subset of builtins is exposed. This is a
best-effort sandbox appropriate for a small personal project, not a
guarantee against a determined attacker — the real security boundary is
process isolation (separate OS process, empty environment, resource
limits), not this restricted-builtins layer.
"""
import sys
import json
import builtins

ALLOWED_MODULES = {
    "math", "collections", "itertools", "functools", "re", "heapq",
    "bisect", "string", "random", "operator", "copy",
}


def _restricted_import(name, g=None, l=None, fromlist=(), level=0):
    top = name.split(".")[0]
    if top not in ALLOWED_MODULES:
        raise ImportError("import of %r is not allowed in this sandbox" % name)
    return builtins.__import__(name, g, l, fromlist, level)


_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "chr", "complex", "dict", "divmod",
    "enumerate", "filter", "float", "frozenset", "hash", "hex", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min",
    "next", "object", "oct", "ord", "pow", "print", "property", "range",
    "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "type", "zip",
    "Exception", "ValueError", "TypeError", "IndexError", "KeyError",
    "StopIteration", "ZeroDivisionError", "RuntimeError", "ArithmeticError",
    "AttributeError", "NotImplementedError", "OverflowError",
    "RecursionError", "AssertionError", "GeneratorExit", "StopAsyncIteration",
]

_safe_builtins = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)}
_safe_builtins["__import__"] = _restricted_import


def main():
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    function_name = payload["function_name"]
    tests = payload["tests"]

    exec_globals = {"__builtins__": _safe_builtins}
    try:
        exec(code, exec_globals)
    except Exception as e:
        print(json.dumps({"compile_error": "%s: %s" % (type(e).__name__, e)}))
        return

    fn = exec_globals.get(function_name)
    if fn is None or not callable(fn):
        print(json.dumps({"compile_error": "Function '%s' is not defined." % function_name}))
        return

    results = []
    for t in tests:
        try:
            actual = fn(*t["args"])
            results.append({"actual": actual, "error": None})
        except Exception as e:
            results.append({"actual": None, "error": "%s: %s" % (type(e).__name__, e)})

    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main()
