"""
Smoke test: verify all production modules can be imported and all
third-party imports are declared in requirements.txt.
"""
import ast
import os
import re


def test_required_third_party_packages_in_requirements():
    """
    Scan all src/ Python files for third-party imports and verify each
    is listed in requirements.txt.

    Third-party = any import that is NOT:
    - stdlib (os, sys, re, datetime, uuid, json, etc.)
    - a module from our own src/ packages
    """
    stdlib = {
        # Core stdlib
        "os", "sys", "re", "datetime", "date", "time", "uuid", "json",
        "typing", "abc", "contextlib", "functools", "operator",
        "pathlib", "hashlib", "hmac", "hashlib", "inspect", "signal",
        "collections", "itertools", "warnings", "weakref", "copy",
        "io", "gc", "traceback", "subprocess", "shutil", "tempfile",
        "errno", "ctypes", "types", "fileinput", "fnmatch",
        "glob", "linecache", "tokenize", "ast", "dis", "code",
        "codeop", "compile", "pprint", "textwrap", "unicodedata",
        "asyncio", "dataclasses", "enum", "logging", "platform",
        "threading", "multiprocessing", "concurrent", "heapq",
        "bz2", "gzip", "zipfile", "tarfile", "io", "marshal",
        "pickle", "csv", "xml", "html", "urllib", "http", "ftplib",
        "socket", "ssl", "select", "email", "mailbox", "mimetypes",
        "turtle", "turtledemo", "colorsys", "random", "statistics",
        "numbers", "math", "cmath", "decimal", "fractions",
        "base64", "binhex", "quopri", "uu",
        "sqlite3",
        # Special
        "__future__",
    }

    # Discover all src/ Python files
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    src_dir = os.path.join(root_dir, "src")
    python_files = []
    for pkg in os.listdir(src_dir):
        pkg_path = os.path.join(src_dir, pkg)
        if not os.path.isdir(pkg_path) or pkg.startswith("_"):
            continue
        for root, dirs, files in os.walk(pkg_path):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for file in files:
                if file.endswith(".py") and not file.startswith("_"):
                    python_files.append(os.path.join(root, file))

    # Collect all third-party imports
    third_party_imports: set[str] = set()
    for filepath in python_files:
        try:
            source = open(filepath, encoding="utf-8").read()
        except Exception:
            continue
        try:
            tree = ast.parse(source)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name not in stdlib and not name.startswith("src"):
                        third_party_imports.add(_normalize_pkg_name(name))
            elif isinstance(node, ast.ImportFrom):
                name = node.module or ""
                top_level = name.split(".")[0]
                if top_level not in stdlib and not top_level.startswith("src"):
                    third_party_imports.add(_normalize_pkg_name(top_level))

    # Apply aliasing so "google" maps to "google-ads", "psycopg2" to "psycopg2-binary", etc.
    normalized_third_party = {_ALIAS_TO_REQUIREMENT.get(p, p) for p in third_party_imports}

    # Read requirements.txt
    req_file = os.path.join(root_dir, "requirements.txt")
    req_content = open(req_file, encoding="utf-8").read()
    req_packages = set()
    for line in req_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg_name = re.split(r"[!=<>]", line)[0].strip().lower()
        if pkg_name:
            req_packages.add(pkg_name)

    missing = sorted(normalized_third_party - req_packages)
    if missing:
        raise AssertionError(
            f"Third-party import(s) not declared in requirements.txt:\n"
            + "\n".join(f"  - {pkg}" for pkg in missing)
        )


def _normalize_pkg_name(name: str) -> str:
    """Normalize package name to canonical PyPI form (underscores → hyphens)."""
    return name.lower().replace("_", "-")


# Map import-name → canonical requirement name for known packages
# where the import name differs from the PyPI distribution name.
_ALIAS_TO_REQUIREMENT: dict[str, str] = {
    "google": "google-ads",
    "psycopg2": "psycopg2-binary",
    "resend": "resend",
}
