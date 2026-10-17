"""
Builds test harnesses for Java and C++ submissions and runs them.

The harness embeds every test case as source-code literals, calls the user's
Solution method, and prints one marker line per test:
    @@LC@@<index>\t<json result>
    @@LCERR@@<index>\t<error message>

Where it runs:
- LEETCOACH_LOCAL_RUNNER=1 and javac/g++ installed -> compiled locally (dev/testing)
- otherwise -> Wandbox (https://wandbox.org), a free public compile API
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

WANDBOX = "https://wandbox.org/api"
_compiler_cache = {"at": 0, "list": None}

MARK, ERR = "@@LC@@", "@@LCERR@@"


# ---------------------------------------------------------------- Java

def _jstr(s):
    return json.dumps(s)  # Java accepts JSON string escapes, incl. \uXXXX


def _jchar(c):
    return "'" + c.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _java_lit(v, t):
    if t == "int":
        return str(int(v))
    if t == "string":
        return _jstr(v)
    if t == "int[]":
        return "new int[]{" + ",".join(str(x) for x in v) + "}"
    if t == "int[][]":
        return "new int[][]{" + ",".join("{" + ",".join(str(x) for x in row) + "}" for row in v) + "}"
    if t == "string[]":
        return "new String[]{" + ",".join(_jstr(x) for x in v) + "}"
    if t == "char[][]":
        return "new char[][]{" + ",".join("{" + ",".join(_jchar(c) for c in row) + "}" for row in v) + "}"
    if t == "ListNode":
        return "LC.build(new int[]{" + ",".join(str(x) for x in v) + "})"
    if t == "ListNode[]":
        return "new ListNode[]{" + ",".join(_java_lit(x, "ListNode") for x in v) + "}"
    raise ValueError("unsupported Java arg type " + t)


JAVA_DECL = {"int": "int", "string": "String", "int[]": "int[]", "int[][]": "int[][]", "string[]": "String[]",
             "char[][]": "char[][]", "ListNode": "ListNode", "ListNode[]": "ListNode[]"}

JAVA_SUPPORT = r'''
class ListNode {
    int val; ListNode next;
    ListNode() {}
    ListNode(int val) { this.val = val; }
    ListNode(int val, ListNode next) { this.val = val; this.next = next; }
}

class LC {
    static ListNode build(int[] v) {
        ListNode dummy = new ListNode(0), t = dummy;
        for (int x : v) { t.next = new ListNode(x); t = t.next; }
        return dummy.next;
    }
    static String str(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    static String json(Object o) {
        if (o == null) return "null";
        if (o instanceof String) return str((String) o);
        if (o instanceof Character) return str(String.valueOf(o));
        if (o instanceof Double || o instanceof Float) {
            double d = ((Number) o).doubleValue();
            if (Double.isNaN(d) || Double.isInfinite(d)) return "null";
            return Double.toString(d);
        }
        if (o instanceof Number || o instanceof Boolean) return o.toString();
        if (o instanceof ListNode) {
            StringBuilder b = new StringBuilder("[");
            ListNode n = (ListNode) o; int guard = 0;
            while (n != null) {
                if (guard++ > 0) b.append(',');
                if (guard > 200000) throw new RuntimeException("linked list result looks cyclic");
                b.append(n.val); n = n.next;
            }
            return b.append(']').toString();
        }
        if (o instanceof int[]) { int[] a = (int[]) o; StringBuilder b = new StringBuilder("["); for (int i = 0; i < a.length; i++) { if (i > 0) b.append(','); b.append(a[i]); } return b.append(']').toString(); }
        if (o instanceof char[]) { char[] a = (char[]) o; StringBuilder b = new StringBuilder("["); for (int i = 0; i < a.length; i++) { if (i > 0) b.append(','); b.append(str(String.valueOf(a[i]))); } return b.append(']').toString(); }
        if (o instanceof Object[]) { Object[] a = (Object[]) o; StringBuilder b = new StringBuilder("["); for (int i = 0; i < a.length; i++) { if (i > 0) b.append(','); b.append(json(a[i])); } return b.append(']').toString(); }
        if (o instanceof Iterable) { StringBuilder b = new StringBuilder("["); boolean first = true; for (Object x : (Iterable<?>) o) { if (!first) b.append(','); first = false; b.append(json(x)); } return b.append(']').toString(); }
        return str(o.toString());
    }
    static void ok(int i, Object r) { System.out.println("@@LC@@" + i + "\t" + json(r)); System.out.flush(); }
    static void err(int i, Throwable e) {
        String m = e.getClass().getSimpleName() + (e.getMessage() != null ? ": " + e.getMessage() : "");
        System.out.println("@@LCERR@@" + i + "\t" + m.replace('\n', ' ')); System.out.flush();
    }
}
'''


def build_java(code, p):
    args_t, ret = p["types"]["args"], p["types"]["ret"]
    fn, mode = p["functionName"], p.get("resultMode", "return")
    imports = re.findall(r"^\s*import\s+[\w.*]+\s*;\s*$", code, flags=re.M)
    body = re.sub(r"^\s*import\s+[\w.*]+\s*;\s*$", "", code, flags=re.M)
    body = re.sub(r"\bpublic\s+(final\s+)?class\s+Solution\b", "class Solution", body)
    body = re.sub(r"^\s*public\s+class\s+", "class ", body, flags=re.M)

    tests = []
    for i, t in enumerate(p["tests"]):
        decls = "".join(f"{JAVA_DECL[ty]} a{j} = {_java_lit(v, ty)}; " for j, (v, ty) in enumerate(zip(t["args"], args_t)))
        call = f"new Solution().{fn}({', '.join(f'a{j}' for j in range(len(args_t)))})"
        if mode == "final_arg0" or ret == "void":
            run = f"{call}; LC.ok({i}, a0);"
        elif mode == "prefix_len_of_arg0":
            run = f"int k = {call}; LC.ok({i}, java.util.Arrays.copyOf(a0, Math.max(0, Math.min(k, a0.length))));"
        elif ret == "ListNode":
            run = f"ListNode r = {call}; LC.ok({i}, r == null ? new int[0] : (Object) r);"
        else:
            run = f"Object r = {call}; LC.ok({i}, r);"
        tests.append(f"        try {{ {decls}{run} }} catch (Throwable e) {{ LC.err({i}, e); }}")

    entry = "LCRunner.run();"
    return (
        "import java.util.*;\nimport java.util.stream.*;\n" + "\n".join(imports) + "\n\n"
        f"class Main {{ public static void main(String[] args) {{ {entry} }} }}\n"
        f"class prog {{ public static void main(String[] args) {{ {entry} }} }}\n"
        f"class Prog {{ public static void main(String[] args) {{ {entry} }} }}\n"
        "class LCRunner {\n    static void run() {\n" + "\n".join(tests) + "\n    }\n}\n"
        + JAVA_SUPPORT + "\n// ---- user code ----\n" + body + "\n"
    )


# ---------------------------------------------------------------- C++

def _cstr(s):
    return json.dumps(s)


def _cchar(c):
    return "'" + c.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _cpp_lit(v, t):
    if t == "int":
        return str(int(v))
    if t == "string":
        return "string(" + _cstr(v) + ")"
    if t == "int[]":
        return "vector<int>{" + ",".join(str(x) for x in v) + "}"
    if t == "int[][]":
        return "vector<vector<int>>{" + ",".join("{" + ",".join(str(x) for x in row) + "}" for row in v) + "}"
    if t == "string[]":
        return "vector<string>{" + ",".join(_cstr(x) for x in v) + "}"
    if t == "char[][]":
        return "vector<vector<char>>{" + ",".join("{" + ",".join(_cchar(c) for c in row) + "}" for row in v) + "}"
    if t == "ListNode":
        return "lc_build(vector<int>{" + ",".join(str(x) for x in v) + "})"
    if t == "ListNode[]":
        return "vector<ListNode*>{" + ",".join(_cpp_lit(x, "ListNode") for x in v) + "}"
    raise ValueError("unsupported C++ arg type " + t)


CPP_DECL = {"int": "int", "string": "string", "int[]": "vector<int>", "int[][]": "vector<vector<int>>",
            "string[]": "vector<string>", "char[][]": "vector<vector<char>>", "ListNode": "ListNode*",
            "ListNode[]": "vector<ListNode*>"}

CPP_HEAD = r'''#include <bits/stdc++.h>
using namespace std;

struct ListNode {
    int val; ListNode *next;
    ListNode() : val(0), next(nullptr) {}
    ListNode(int x) : val(x), next(nullptr) {}
    ListNode(int x, ListNode *next) : val(x), next(next) {}
};
'''

CPP_SUPPORT = r'''
static ListNode* lc_build(const vector<int>& v) {
    ListNode dummy(0); ListNode* t = &dummy;
    for (int x : v) { t->next = new ListNode(x); t = t->next; }
    return dummy.next;
}
static string lc_json(const string& s) {
    string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
        else if (c < 0x20) { char buf[8]; snprintf(buf, sizeof buf, "\\u%04x", c); o += buf; }
        else o += (char)c;
    }
    return o + "\"";
}
static string lc_json(const char* s) { return lc_json(string(s)); }
static string lc_json(char c) { return lc_json(string(1, c)); }
static string lc_json(bool b) { return b ? "true" : "false"; }
static string lc_json(int x) { return to_string(x); }
static string lc_json(long x) { return to_string(x); }
static string lc_json(long long x) { return to_string(x); }
static string lc_json(double d) {
    if (std::isnan(d) || std::isinf(d)) return "null";
    ostringstream os; os << setprecision(15) << d; return os.str();
}
static string lc_json(ListNode* n) {
    string o = "["; int guard = 0;
    while (n) {
        if (guard++ > 0) o += ",";
        if (guard > 200000) throw runtime_error("linked list result looks cyclic");
        o += to_string(n->val); n = n->next;
    }
    return o + "]";
}
template <typename T> static string lc_json(const vector<T>& v) {
    string o = "[";
    for (size_t i = 0; i < v.size(); i++) { if (i) o += ","; o += lc_json(v[i]); }
    return o + "]";
}
static string lc_json(const vector<bool>& v) {
    string o = "[";
    for (size_t i = 0; i < v.size(); i++) { if (i) o += ","; o += v[i] ? "true" : "false"; }
    return o + "]";
}
#define LC_OK(i, r) do { cout << "@@LC@@" << (i) << "\t" << lc_json(r) << endl; } while (0)
#define LC_ERR(i, m) do { string _m = (m); replace(_m.begin(), _m.end(), '\n', ' '); cout << "@@LCERR@@" << (i) << "\t" << _m << endl; } while (0)
'''


def build_cpp(code, p):
    args_t, ret = p["types"]["args"], p["types"]["ret"]
    fn, mode = p["functionName"], p.get("resultMode", "return")
    tests = []
    for i, t in enumerate(p["tests"]):
        decls = "".join(f"{CPP_DECL[ty]} a{j} = {_cpp_lit(v, ty)}; " for j, (v, ty) in enumerate(zip(t["args"], args_t)))
        call = f"Solution().{fn}({', '.join(f'a{j}' for j in range(len(args_t)))})"
        if mode == "final_arg0" or ret == "void":
            run = f"{call}; LC_OK({i}, a0);"
        elif mode == "prefix_len_of_arg0":
            run = f"int k = {call}; k = max(0, min(k, (int)a0.size())); LC_OK({i}, vector<int>(a0.begin(), a0.begin() + k));"
        else:
            run = f"auto r = {call}; LC_OK({i}, r);"
        tests.append(
            f"    try {{ {decls}{run} }} catch (const exception& e) {{ LC_ERR({i}, string(\"Exception: \") + e.what()); }}"
            f" catch (...) {{ LC_ERR({i}, \"Exception thrown\"); }}"
        )
    return (CPP_HEAD + "\n// ---- user code ----\n" + code + "\n" + CPP_SUPPORT
            + "\nint main() {\n" + "\n".join(tests) + "\n    return 0;\n}\n")


# ---------------------------------------------------------------- running

def _parse(stdout, n):
    results = [None] * n
    for line in stdout.splitlines():
        for tag, is_err in ((ERR, True), (MARK, False)):
            if line.startswith(tag):
                idx, _, payload = line[len(tag):].partition("\t")
                try:
                    i = int(idx)
                except ValueError:
                    break
                if 0 <= i < n:
                    if is_err:
                        results[i] = {"actual": None, "error": payload or "Runtime error"}
                    else:
                        try:
                            results[i] = {"actual": json.loads(payload), "error": None}
                        except ValueError:
                            results[i] = {"actual": None, "error": "Couldn't read the result"}
                break
    return results


def _local(language, source):
    with tempfile.TemporaryDirectory() as d:
        if language == "java":
            path = os.path.join(d, "prog.java")
            open(path, "w").write(source)
            c = subprocess.run(["javac", "-nowarn", "prog.java"], cwd=d, capture_output=True, text=True, timeout=60)
            if c.returncode:
                return {"compile_error": c.stderr}
            r = subprocess.run(["java", "-Xss64m", "-cp", d, "Main"], capture_output=True, text=True, timeout=15)
        else:
            path = os.path.join(d, "prog.cpp")
            open(path, "w").write(source)
            c = subprocess.run(["g++", "-std=c++17", "-O2", "-o", "prog", "prog.cpp"], cwd=d, capture_output=True, text=True, timeout=90)
            if c.returncode:
                return {"compile_error": c.stderr}
            r = subprocess.run([os.path.join(d, "prog")], capture_output=True, text=True, timeout=15)
        return {"stdout": r.stdout, "stderr": r.stderr, "status": r.returncode}


def _http_json(url, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "LeetCoach"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _pick_compiler(language):
    now = time.time()
    if not _compiler_cache["list"] or now - _compiler_cache["at"] > 3600:
        _compiler_cache["list"] = _http_json(f"{WANDBOX}/list.json", timeout=15)
        _compiler_cache["at"] = now
    entries = _compiler_cache["list"]
    if language == "java":
        cands = [e for e in entries if e.get("language") == "Java"]
    else:
        cands = [e for e in entries if e.get("language") == "C++" and str(e.get("name", "")).startswith("gcc")]
    stable = [e for e in cands if "head" not in str(e.get("name", ""))]
    pick = (stable or cands or [None])[0]
    if not pick:
        raise RuntimeError(f"No {language} compiler available right now")
    return pick["name"]


def _wandbox(language, source):
    body = {"compiler": _pick_compiler(language), "code": source, "save": False}
    if language == "cpp":
        body["compiler-option-raw"] = "-std=c++17\n-O2"
    out = _http_json(f"{WANDBOX}/compile.json", body, timeout=45)
    if out.get("compiler_error") and not out.get("program_output") and str(out.get("status", "0")) != "0":
        return {"compile_error": out["compiler_error"]}
    return {"stdout": out.get("program_output", ""), "stderr": out.get("program_error", ""), "status": out.get("status")}


def run_compiled(language, code, problem):
    """Returns {"results": [...]} or {"compile_error": "..."} or {"error": "..."}."""
    source = build_java(code, problem) if language == "java" else build_cpp(code, problem)
    use_local = os.environ.get("LEETCOACH_LOCAL_RUNNER") == "1" and shutil.which("javac" if language == "java" else "g++")
    try:
        raw = _local(language, source) if use_local else _wandbox(language, source)
    except subprocess.TimeoutExpired:
        return {"error": "Time limit exceeded — your code took too long to run."}
    except Exception as e:
        return {"error": f"Couldn't reach the {('Java' if language == 'java' else 'C++')} runner right now ({type(e).__name__}). Try again in a bit, or use Python/JavaScript."}

    if raw.get("compile_error"):
        # Point line numbers at the user's code, not the harness
        offset = source[: source.index("// ---- user code ----")].count("\n") + 1
        return {"compile_error": _trim_compile_error(raw["compile_error"], offset)}

    n = len(problem["tests"])
    results = _parse(raw.get("stdout", ""), n)
    crash = (raw.get("stderr") or "").strip().splitlines()
    crash_msg = ("Runtime error: " + crash[-1][:300]) if crash else "Runtime error (your program crashed)"
    results = [r if r is not None else {"actual": None, "error": crash_msg} for r in results]
    return {"results": results}


def _trim_compile_error(msg, offset=0):
    def fix(m):
        n = int(m.group(1)) - offset
        return f"Line {n}" if n > 0 else "Line ?"
    lines = [l for l in msg.splitlines() if l.strip()]
    errs = [l for l in lines if "error" in l.lower()]
    out = "\n".join((errs or lines)[:6])
    out = re.sub(r"(?:\S*/)?prog\.(?:java|cpp):(\d+)(?::\d+)?:?", fix, out)
    return "Compile error:\n" + out[:1500]
