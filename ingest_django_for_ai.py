#!/usr/bin/env python3
"""
ingest_django_for_ai.py

Generate a compact Django project snapshot for AI assistance.

Outputs:
- filtered directory tree
- dependency signals
- django settings summary
- url patterns
- view function/class names
- AI helper instructions + clarifying questions

Designed to paste into ChatGPT to generate README / analysis.
Stdlib only.
"""

from __future__ import annotations
import argparse
import ast
import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# ------------------------------------------------------------
# ignore patterns
# ------------------------------------------------------------

IGNORE_DIRS = {
    ".git",".venv","venv","env","node_modules","dist","build",
    "__pycache__",".pytest_cache",".mypy_cache",".ruff_cache",
    "media","staticfiles","uploads",".idea",".vscode"
}

IGNORE_GLOBS = [
    "*.pyc","*.pyo","*.pyd","*.so","*.dll","*.exe",
    "*.png","*.jpg","*.jpeg","*.gif","*.webp","*.svg",
    "*.mp4","*.mov","*.mp3","*.wav","*.zip","*.tar","*.gz",
    "*.db","*.sqlite3","*.log"
]


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

SECRET_RE = re.compile(
    r"(?i)\b(secret|token|password|api[_-]?key|private[_-]?key)\b"
)

def redact_line(line: str) -> str:
    if "=" not in line:
        return line
    left = line.split("=",1)[0]
    if SECRET_RE.search(left):
        return f"{left}=<REDACTED>"
    return line


def safe_read_text(path: Path, max_bytes: int = 60000) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
        txt = data.decode("utf-8", errors="replace")
        return "\n".join(redact_line(l) for l in txt.splitlines())
    except:
        return ""


def relpath(p: Path, root: Path) -> str:
    return str(p.relative_to(root)).replace("\\","/")


def matches_glob(name: str) -> bool:
    return any(fnmatch.fnmatch(name,g) for g in IGNORE_GLOBS)


# ------------------------------------------------------------
# directory tree
# ------------------------------------------------------------

def walk_tree(root: Path, depth_limit=6) -> List[str]:
    lines=[]

    def rec(cur: Path, depth: int):
        if depth>depth_limit:
            return
        try:
            items=sorted(cur.iterdir(),key=lambda x:(x.is_file(),x.name))
        except:
            return

        for p in items:
            if p.name in IGNORE_DIRS:
                continue
            if p.is_file() and matches_glob(p.name):
                continue

            lines.append("  "*depth+f"- {p.name}/" if p.is_dir() else "  "*depth+f"- {p.name}")

            if p.is_dir():
                rec(p,depth+1)

    lines.append(f"- {root.name}/")
    rec(root,1)
    return lines


# ------------------------------------------------------------
# django discovery
# ------------------------------------------------------------

def find_settings(root: Path)->Optional[Path]:
    for p in root.rglob("settings.py"):
        if not any(x in p.parts for x in IGNORE_DIRS):
            return p
    return None


def parse_settings(settings: Path, root: Path)->Dict[str,Any]:
    txt=safe_read_text(settings)
    out={"path":relpath(settings,root),"INSTALLED_APPS":[],"MIDDLEWARE":[]}

    try:
        tree=ast.parse(txt)
    except:
        return out

    def lit(node):
        try: return ast.literal_eval(node)
        except: return None

    for n in tree.body:
        if isinstance(n,ast.Assign) and n.targets:
            if isinstance(n.targets[0],ast.Name):
                k=n.targets[0].id
                if k in ("INSTALLED_APPS","MIDDLEWARE"):
                    v=lit(n.value)
                    if isinstance(v,(list,tuple)):
                        out[k]=[str(x) for x in v]
    return out


def extract_urls(root: Path)->Dict[str,Any]:
    results=[]

    for p in root.rglob("urls.py"):
        if any(x in p.parts for x in IGNORE_DIRS):
            continue

        txt=safe_read_text(p)
        patterns=[]
        includes=[]

        try:
            tree=ast.parse(txt)
        except:
            continue

        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                if node.func.id in ("path","re_path") and node.args:
                    try:
                        v=ast.literal_eval(node.args[0])
                        if isinstance(v,str):
                            patterns.append(v)
                    except: pass

                if node.func.id=="include" and node.args:
                    try:
                        v=ast.literal_eval(node.args[0])
                        if isinstance(v,str):
                            includes.append(v)
                    except: pass

        results.append({
            "path":relpath(p,root),
            "patterns":sorted(set(patterns)),
            "includes":sorted(set(includes))
        })

    return {"urls":results}


def format_func(fn)->str:
    args=[a.arg for a in fn.args.args]
    return f"{fn.name}({', '.join(args)})"


def extract_views(root: Path)->Dict[str,Any]:
    out=[]

    for p in root.rglob("views.py"):
        if any(x in p.parts for x in IGNORE_DIRS):
            continue

        txt=safe_read_text(p)

        try:
            tree=ast.parse(txt)
        except:
            continue

        funcs=[]
        classes=[]

        for n in tree.body:
            if isinstance(n,ast.FunctionDef):
                funcs.append(format_func(n))
            elif isinstance(n,ast.ClassDef):
                methods=[format_func(x) for x in n.body if isinstance(x,ast.FunctionDef)]
                classes.append({"name":n.name,"methods":methods})

        out.append({"path":relpath(p,root),"functions":funcs,"classes":classes})

    return {"views":out}


# ------------------------------------------------------------
# AI helper header
# ------------------------------------------------------------

def ai_header(domain:str="",about:str="")->str:
    lines=[
"# AI Helper Instructions",
"",
"Use this snapshot to help with docs or analysis.",
"",
"Rules:",
"- think first, then ask for missing info",
"- ask under 10 questions",
"- avoid listing directories in README",
"- prefer standard README structure",
"- infer carefully from app names and routes",
""
]

    if about:
        lines.append(f"- use {about} for canonical project description")
    if domain:
        lines.append(f"- production domain: {domain}")

    return "\n".join(lines)


# ------------------------------------------------------------
# markdown output
# ------------------------------------------------------------

def to_markdown(report:Dict[str,Any])->str:
    lines=[]

    if report.get("ai_header"):
        lines.append(report["ai_header"])
        lines.append("\n---\n")

    lines.append("# AI Context Snapshot\n")
    lines.append(f"- root: `{report['root']}`\n")

    lines.append("## Directory Tree\n")
    lines.append("```text")
    lines.extend(report["tree"])
    lines.append("```\n")

    lines.append("## Dependency Signals\n")
    lines.append("```text")
    for d in report["deps"]:
        lines.append(f"- {d}")
    lines.append("```\n")

    if report.get("settings"):
        lines.append("## Django Settings Summary\n")
        lines.append(f"- settings.py: `{report['settings']['path']}`\n")

        lines.append("### INSTALLED_APPS")
        lines.append("```text")
        lines.extend(report["settings"]["INSTALLED_APPS"])
        lines.append("```\n")

        lines.append("### MIDDLEWARE")
        lines.append("```text")
        lines.extend(report["settings"]["MIDDLEWARE"])
        lines.append("```\n")

    if report.get("urls"):
        lines.append("## URL Patterns\n")
        for u in report["urls"]["urls"]:
            lines.append(f"### `{u['path']}`")
            if u["patterns"]:
                lines.append("```text")
                lines.extend(u["patterns"])
                lines.append("```")

    if report.get("views"):
        lines.append("\n## Views\n")
        for v in report["views"]["views"]:
            lines.append(f"### `{v['path']}`")
            if v["functions"]:
                lines.append("```text")
                lines.extend(v["functions"])
                lines.append("```")

    return "\n".join(lines)


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=".")
    ap.add_argument("--out",default="ai_context.md")
    ap.add_argument("--domain",default="")
    ap.add_argument("--about-url",default="")
    args=ap.parse_args()

    root=Path(args.root).resolve()

    report={
        "root":str(root),
        "tree":walk_tree(root),
        "deps":[f.name for f in root.iterdir() if f.name in ("Pipfile","pyproject.toml","requirements.txt","uv.lock","Procfile","runtime.txt")],
        "settings":None,
        "urls":extract_urls(root),
        "views":extract_views(root),
        "ai_header":ai_header(args.domain,args.about_url)
    }

    s=find_settings(root)
    if s:
        report["settings"]=parse_settings(s,root)

    md=to_markdown(report)
    Path(args.out).write_text(md,encoding="utf-8")
    print("Wrote",args.out)


if __name__=="__main__":
    main()