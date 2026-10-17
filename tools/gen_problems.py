"""
Adds per-language type signatures and starter code to static/problem_details.json.
Run: python3 tools/gen_problems.py  (idempotent)
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "static", "problem_details.json")

# (arg types, return type) per problem. Tags are language-neutral.
TYPES = {
    "1": (["int[]", "int"], "int[]"),
    "2": (["ListNode", "ListNode"], "ListNode"),
    "3": (["string"], "int"),
    "4": (["int[]", "int[]"], "double"),
    "5": (["string"], "string"),
    "7": (["int"], "int"),
    "8": (["string"], "int"),
    "9": (["int"], "bool"),
    "11": (["int[]"], "int"),
    "12": (["int"], "string"),
    "13": (["string"], "int"),
    "14": (["string[]"], "string"),
    "15": (["int[]"], "List<List<int>>"),
    "17": (["string"], "List<string>"),
    "19": (["ListNode", "int"], "ListNode"),
    "20": (["string"], "bool"),
    "21": (["ListNode", "ListNode"], "ListNode"),
    "22": (["int"], "List<string>"),
    "23": (["ListNode[]"], "ListNode"),
    "26": (["int[]"], "int"),
    "33": (["int[]", "int"], "int"),
    "34": (["int[]", "int"], "int[]"),
    "35": (["int[]", "int"], "int"),
    "36": (["char[][]"], "bool"),
    "39": (["int[]", "int"], "List<List<int>>"),
    "41": (["int[]"], "int"),
    "42": (["int[]"], "int"),
    "45": (["int[]"], "int"),
    "46": (["int[]"], "List<List<int>>"),
    "48": (["int[][]"], "void"),
    "49": (["string[]"], "List<List<string>>"),
    "53": (["int[]"], "int"),
    "54": (["int[][]"], "List<int>"),
    "55": (["int[]"], "bool"),
    "56": (["int[][]"], "int[][]"),
}

JAVA = {"int": "int", "double": "double", "bool": "boolean", "string": "String", "int[]": "int[]",
        "int[][]": "int[][]", "string[]": "String[]", "char[][]": "char[][]", "ListNode": "ListNode",
        "ListNode[]": "ListNode[]", "void": "void", "List<int>": "List<Integer>",
        "List<List<int>>": "List<List<Integer>>", "List<string>": "List<String>",
        "List<List<string>>": "List<List<String>>"}
CPP_RET = {"int": "int", "double": "double", "bool": "bool", "string": "string", "int[]": "vector<int>",
           "int[][]": "vector<vector<int>>", "ListNode": "ListNode*", "void": "void",
           "List<int>": "vector<int>", "List<List<int>>": "vector<vector<int>>",
           "List<string>": "vector<string>", "List<List<string>>": "vector<vector<string>>"}
CPP_ARG = {"int": "int", "string": "string", "int[]": "vector<int>&", "int[][]": "vector<vector<int>>&",
           "string[]": "vector<string>&", "char[][]": "vector<vector<char>>&", "ListNode": "ListNode*",
           "ListNode[]": "vector<ListNode*>&"}
JSDOC = {"int": "number", "double": "number", "bool": "boolean", "string": "string", "int[]": "number[]",
         "int[][]": "number[][]", "string[]": "string[]", "char[][]": "character[][]", "ListNode": "ListNode",
         "ListNode[]": "ListNode[]", "void": "void", "List<int>": "number[]", "List<List<int>>": "number[][]",
         "List<string>": "string[]", "List<List<string>>": "string[][]"}

JAVA_NODE = """/**
 * Definition for singly-linked list.
 * class ListNode {
 *     int val;
 *     ListNode next;
 *     ListNode(int val) { this.val = val; }
 *     ListNode(int val, ListNode next) { this.val = val; this.next = next; }
 * }
 */
"""
CPP_NODE = """/**
 * Definition for singly-linked list.
 * struct ListNode {
 *     int val;
 *     ListNode *next;
 *     ListNode(int x) : val(x), next(nullptr) {}
 *     ListNode(int x, ListNode *next) : val(x), next(next) {}
 * };
 */
"""
JS_NODE = """/**
 * Definition for singly-linked list.
 * function ListNode(val, next) {
 *     this.val = (val===undefined ? 0 : val)
 *     this.next = (next===undefined ? null : next)
 * }
 */
"""
PY_NODE = """# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
"""


def uses_list(args, ret):
    return any("ListNode" in t for t in args + [ret])


def starters(fn, params, args, ret):
    node = uses_list(args, ret)
    py = (PY_NODE if node else "") + f"def {fn}({', '.join(params)}):\n    pass"
    doc = "\n".join(f" * @param {{{JSDOC[t]}}} {p}" for p, t in zip(params, args))
    js = (JS_NODE if node else "") + f"/**\n{doc}\n * @return {{{JSDOC[ret]}}}\n */\nvar {fn} = function({', '.join(params)}) {{\n    \n}};"
    jparams = ", ".join(f"{JAVA[t]} {p}" for p, t in zip(params, args))
    java = (JAVA_NODE if node else "") + f"class Solution {{\n    public {JAVA[ret]} {fn}({jparams}) {{\n        \n    }}\n}}"
    cparams = ", ".join(f"{CPP_ARG[t]} {p}" for p, t in zip(params, args))
    cpp = (CPP_NODE if node else "") + f"class Solution {{\npublic:\n    {CPP_RET[ret]} {fn}({cparams}) {{\n        \n    }}\n}};"
    return {"python": py, "javascript": js, "java": java, "cpp": cpp}


def main():
    with open(PATH) as f:
        data = json.load(f)
    for pid, p in data.items():
        args, ret = TYPES[pid]
        assert len(args) == len(p["params"]), pid
        p["types"] = {"args": args, "ret": ret}
        p["starter"] = starters(p["functionName"], p["params"], args, ret)
        p["starterCode"] = p["starter"]["python"]
    with open(PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"updated {len(data)} problems")


if __name__ == "__main__":
    main()
