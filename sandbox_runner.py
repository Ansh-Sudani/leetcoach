"""
Runs inside an isolated subprocess (python -I -S) with no environment
variables and OS resource limits already applied by the parent process.
Reads a JSON payload from stdin:
  {
    "code": "...",
    "function_name": "...",
    "tests": [{"args": [...]}],
    "arg_types": ["plain" | "linked_list" | "linked_list_array", ...],   # optional
    "return_type": "plain" | "linked_list",                              # optional
    "result_mode": "return" | "final_arg0" | "prefix_len_of_arg0"        # optional
  }
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
    "tuple", "type", "zip", "__build_class__",
    "Exception", "ValueError", "TypeError", "IndexError", "KeyError",
    "StopIteration", "ZeroDivisionError", "RuntimeError", "ArithmeticError",
    "AttributeError", "NotImplementedError", "OverflowError",
    "RecursionError", "AssertionError", "GeneratorExit", "StopAsyncIteration",
]

_safe_builtins = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)}
_safe_builtins["__import__"] = _restricted_import


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


def _build_linked_list(values):
    head = None
    tail = None
    for v in values:
        node = ListNode(v)
        if head is None:
            head = node
        else:
            tail.next = node
        tail = node
    return head


def _linked_list_to_values(node):
    out = []
    guard = 0
    while node is not None:
        out.append(node.val)
        node = node.next
        guard += 1
        if guard > 200000:
            raise RuntimeError("linked list result looks cyclic or unreasonably long")
    return out


def _convert_arg(value, arg_type):
    if arg_type == "linked_list":
        return _build_linked_list(value)
    if arg_type == "linked_list_array":
        return [_build_linked_list(v) for v in value]
    return value


def _convert_result(value, return_type):
    if return_type == "linked_list":
        return _linked_list_to_values(value)
    return value


def main():
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    function_name = payload["function_name"]
    tests = payload["tests"]
    arg_types = payload.get("arg_types") or []
    return_type = payload.get("return_type")
    result_mode = payload.get("result_mode", "return")

    exec_globals = {"__builtins__": _safe_builtins, "ListNode": ListNode}
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
            args = [
                _convert_arg(v, arg_types[i] if i < len(arg_types) else "plain")
                for i, v in enumerate(t["args"])
            ]
            ret = fn(*args)
            if result_mode == "final_arg0":
                actual = args[0]
            elif result_mode == "prefix_len_of_arg0":
                if not isinstance(ret, int):
                    raise TypeError("expected an int return value, got %s" % type(ret).__name__)
                actual = args[0][:ret]
            else:
                actual = _convert_result(ret, return_type)
            json.dumps(actual)  # fail loudly here rather than corrupt the whole stdout payload
            results.append({"actual": actual, "error": None})
        except Exception as e:
            results.append({"actual": None, "error": "%s: %s" % (type(e).__name__, e)})

    print(json.dumps({"results": results}))


if __name__ == "__main__":
    main()
