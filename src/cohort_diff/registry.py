"""Cohort definitions: SQL files with a small metadata header.

Each file in ``cohort_diff/definitions`` starts with ``-- key: value`` lines
(``name``, ``condition``, ``description``, ``reference``) followed by one query
that returns a single column, ``hadm_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

REQUIRED_KEYS = ("name", "condition", "description", "reference")


@dataclass(frozen=True)
class Definition:
    name: str
    condition: str
    description: str
    reference: str
    sql: str


def parse(text: str) -> Definition:
    meta: dict[str, str] = {}
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not body and stripped.startswith("--") and ":" in stripped:
            key, value = stripped[2:].split(":", 1)
            meta[key.strip()] = value.strip()
        elif stripped or body:
            body.append(line)
    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        raise ValueError(f"definition header missing {missing}")
    return Definition(sql="\n".join(body).strip(), **{k: meta[k] for k in REQUIRED_KEYS})


def builtin() -> dict[str, Definition]:
    """All definitions shipped with the package, keyed by name."""
    folder = resources.files("cohort_diff") / "definitions"
    defs = [parse(f.read_text()) for f in folder.iterdir() if f.name.endswith(".sql")]
    return {d.name: d for d in sorted(defs, key=lambda d: d.name)}


def load(name_or_path: str) -> Definition:
    """A built-in definition by name, or a user's ``.sql`` file by path."""
    if name_or_path.endswith(".sql"):
        return parse(Path(name_or_path).read_text())
    defs = builtin()
    if name_or_path not in defs:
        raise KeyError(f"unknown definition {name_or_path!r}; known: {', '.join(defs)}")
    return defs[name_or_path]
