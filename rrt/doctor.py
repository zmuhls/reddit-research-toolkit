"""Setup checks behind 'python main.py check'.

Each check returns a status and, when something is off, the exact command or
action that fixes it.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from typing import List, Optional

from . import REPO_ROOT, credentials
from .datasets import data_root, list_datasets
from .errors import ACCESS_DOC, explain

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"

MIN_PYTHON = (3, 10)
CORE_PACKAGES = [("praw", "praw"), ("pandas", "pandas"), ("rich", "rich"), ("yaml", "PyYAML"), ("dotenv", "python-dotenv")]
ANALYSIS_PACKAGES = [("plotly", "plotly"), ("numpy", "numpy"), ("networkx", "networkx")]


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "?"


def check_python() -> Check:
    found = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < MIN_PYTHON:
        return Check(
            "Python version", FAIL, f"{found} is older than the toolkit supports",
            "Install Python 3.10 or newer from https://www.python.org/downloads/ and recreate the environment.",
        )
    return Check("Python version", PASS, found)


def check_environment() -> Check:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.environ.get("CONDA_DEFAULT_ENV"))
    if in_venv:
        return Check("Virtual environment", PASS, f"active ({sys.prefix})")
    return Check(
        "Virtual environment", WARN, "not active, packages will install system-wide",
        "macOS or Linux: source .venv/bin/activate    Windows: .venv\\Scripts\\activate",
    )


def check_packages(packages, label: str, install_file: str, required: bool) -> Check:
    missing, present = [], []
    for module, distribution in packages:
        try:
            importlib.import_module(module)
            present.append(f"{distribution} {_version(distribution)}")
        except Exception:
            missing.append(distribution)
    if missing:
        return Check(
            label, FAIL if required else WARN, "missing: " + ", ".join(missing),
            f"python -m pip install -r {install_file}",
        )
    return Check(label, PASS, ", ".join(present))


def check_data_folder(override: Optional[str] = None) -> Check:
    root = data_root(override)
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".write-test-", delete=True):
            pass
    except OSError as exc:
        return Check("Data folder", FAIL, f"cannot write to {root} ({exc.strerror or exc})",
                     "Choose another folder with --data-dir <folder>.")
    count = len(list_datasets(root))
    return Check("Data folder", PASS, f"{root} ({count} dataset{'s' if count != 1 else ''})")


def check_env_privacy() -> Optional[Check]:
    if not credentials.ENV_PATH.is_file():
        return None
    ignored = credentials.env_is_git_ignored()
    if ignored is False:
        return Check(".env privacy", WARN, "git is not set to ignore .env",
                     "Add a line containing only .env to .gitignore before you commit anything.")
    return Check(".env privacy", PASS, "git ignores .env")


def check_credentials_present() -> Check:
    creds = credentials.load()
    found = credentials.problems(creds)
    if not creds.present and (not credentials.ENV_PATH.is_file() and creds.source != "environment"):
        return Check(
            "Reddit credentials", SKIP, "not set up (only needed to collect new data)",
            f"python main.py setup   (who can still get credentials: {ACCESS_DOC})",
        )
    blocking = [problem for problem in found if "may be swapped" not in problem]
    if blocking:
        return Check("Reddit credentials", FAIL, " ".join(blocking), "python main.py setup")
    if found:
        return Check("Reddit credentials", WARN, f"found in {creds.source}. " + " ".join(found), "python main.py setup")
    return Check("Reddit credentials", PASS, f"found in {creds.source}")


def check_connection(reddit=None) -> Check:
    creds = credentials.load()
    if reddit is None and (not creds.present or [p for p in credentials.problems(creds) if "may be swapped" not in p]):
        return Check("Connection to Reddit", SKIP, "skipped, no usable credentials")
    try:
        result = credentials.check_connection(creds, reddit=reddit)
    except ModuleNotFoundError:
        return Check("Connection to Reddit", SKIP, "skipped, praw is not installed")
    if result.ok:
        return Check("Connection to Reddit", PASS, "signed in and read a public post")
    friendly = explain(result.error) if result.error else None
    stage = "Reddit rejected the sign-in" if result.stage == "login" else "signed in, but Reddit refused to serve data"
    detail = f"{stage}: {friendly.title}" if friendly else stage
    fix = "python main.py setup" if result.stage == "login" else f"See {ACCESS_DOC}"
    if friendly and friendly.code == "network":
        detail, fix = friendly.title, "Check the internet connection, then run: python main.py check"
    return Check("Connection to Reddit", FAIL, detail, fix)


def run_all(data_dir: Optional[str] = None, online: bool = True, reddit=None) -> List[Check]:
    checks = [
        check_python(),
        check_environment(),
        check_packages(CORE_PACKAGES, "Core packages", "requirements.txt", required=True),
        check_packages(ANALYSIS_PACKAGES, "Analysis packages (optional)", "requirements-analysis.txt", required=False),
        check_data_folder(data_dir),
        check_credentials_present(),
    ]
    privacy = check_env_privacy()
    if privacy:
        checks.append(privacy)
    if online:
        checks.append(check_connection(reddit=reddit))
    return checks


def repo_root_note() -> str:
    return str(REPO_ROOT)
