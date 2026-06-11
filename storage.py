from __future__ import annotations

import json
from pathlib import Path

from models import Project


def save_project(project: Project, path: str) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        json.dump(project.to_dict(), file, ensure_ascii=False, indent=2)


def load_project(path: str) -> Project:
    with Path(path).open("r", encoding="utf-8") as file:
        return Project.from_dict(json.load(file))


def export_text(text: str, path: str) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        file.write(text)
