from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_VERSION = "1.0.0"
UPDATE_INFO_URL = "https://raw.githubusercontent.com/Redmik333/house-planner-estimate/main/version.json"


def compare_versions(current: str, remote: str) -> int:
    """Сравнивает версии вида 1.0.0 или v1.0.1."""
    current_parts = _version_parts(current)
    remote_parts = _version_parts(remote)
    max_len = max(len(current_parts), len(remote_parts))
    current_parts.extend([0] * (max_len - len(current_parts)))
    remote_parts.extend([0] * (max_len - len(remote_parts)))
    if remote_parts > current_parts:
        return 1
    if remote_parts < current_parts:
        return -1
    return 0


def check_for_updates(
    current_version: str = APP_VERSION,
    version_url: str = UPDATE_INFO_URL,
    timeout: float = 6.0,
) -> dict[str, Any] | None:
    """Читает удалённый version.json и возвращает данные, если версия новее."""
    request = urllib.request.Request(version_url, headers={"User-Agent": "house-planner-updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    remote_version = str(data.get("version", "")).strip()
    download_url = str(data.get("url", "")).strip()
    if not remote_version or not download_url:
        return None
    if compare_versions(current_version, remote_version) <= 0:
        return None
    return data


def download_update(update_info: dict[str, Any]) -> Path:
    """Скачивает установщик во временную папку и возвращает путь к нему."""
    url = str(update_info["url"])
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "HousePlannerSetup.exe"
    if not filename.lower().endswith(".exe"):
        filename += ".exe"
    target = Path(tempfile.gettempdir()) / filename
    request = urllib.request.Request(url, headers={"User-Agent": "house-planner-updater"})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())
    return target


def run_installer(installer_path: str | Path) -> None:
    """Запускает скачанный установщик. Закрытие приложения делает вызывающий код."""
    subprocess.Popen([str(installer_path)], close_fds=True)


def _version_parts(value: str) -> list[int]:
    cleaned = value.strip().lower().lstrip("v")
    parts = [int(part) for part in re.findall(r"\d+", cleaned)]
    return parts or [0]
