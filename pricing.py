from __future__ import annotations

import json
from math import cos, radians
from pathlib import Path
import sys
from typing import Any

from models import Project


def app_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DEFAULT_PRICES_PATH = app_base_path() / "prices.json"

DEFAULT_PRICES: dict[str, Any] = {
    "wall_materials": {
        "Газоблок": 3200,
        "Кирпич": 5200,
        "Пеноблок": 2800,
        "Каркас": 2400,
    },
    "foundation": {
        "Плита": 8500,
        "Лента": 6200,
        "Сваи": 3800,
    },
    "roof_type_multiplier": {
        "Плоская": 1.0,
        "Односкатная": 1.15,
        "Двускатная": 1.25,
        "Вальмовая": 1.35,
    },
    "roofing": {
        "Металлочерепица": 2600,
        "Профлист": 1900,
        "Мягкая кровля": 3100,
    },
    "doors": {
        "Базовая дверь": 28000,
    },
    "windows": {
        "Базовое окно": 18000,
    },
    "finishing": {
        "Без отделки": 0,
        "Черновая": 9000,
        "Чистовая": 18000,
    },
}


def load_prices(path: Path = DEFAULT_PRICES_PATH) -> dict[str, Any]:
    if not path.exists():
        save_prices(DEFAULT_PRICES, path)
        return DEFAULT_PRICES.copy()

    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)

    prices = _merge_defaults(DEFAULT_PRICES, loaded)

    # Поддержка старого файла prices.json, где двери и окна лежали в openings.
    openings = loaded.get("openings", {})
    if "doors" not in loaded and "Дверь" in openings:
        prices["doors"]["Базовая дверь"] = openings["Дверь"]
    if "windows" not in loaded and "Окно" in openings:
        prices["windows"]["Базовое окно"] = openings["Окно"]

    if prices != loaded:
        save_prices(prices, path)
    return prices


def save_prices(prices: dict[str, Any], path: Path = DEFAULT_PRICES_PATH) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(prices, file, ensure_ascii=False, indent=2)


def calculate_estimate(project: Project, prices: dict[str, Any]) -> dict[str, float]:
    length = project.total_wall_length_m()
    wall_area = project.wall_area_m2()
    house_area = project.approximate_house_area_m2()

    walls_cost = 0.0
    for wall in project.walls:
        rate = wall.price_per_m2 or prices["wall_materials"].get(wall.material, 0)
        walls_cost += wall.area_m2() * rate * project.floors

    foundation_rate = prices["foundation"].get(project.foundation_type, 0)
    roofing_rate = prices["roofing"].get(project.roofing, 0)
    roof_multiplier = prices["roof_type_multiplier"].get(project.roof_type, 1.25)
    finishing_rate = prices["finishing"].get(project.finishing, 0)

    door_price = prices["doors"].get("Базовая дверь", 0)
    window_price = prices["windows"].get("Базовое окно", 0)
    openings_cost = len(project.doors) * door_price
    openings_cost += sum(max(1, window.count) * window_price for window in project.windows)

    foundation_cost = house_area * foundation_rate / max(project.floors, 1)
    footprint_width, footprint_height = project.footprint_bounds_m()
    if footprint_width <= 0 or footprint_height <= 0:
        roof_base_area = 0.0
    else:
        roof_base_area = (footprint_width + project.roof_overhang * 2) * (footprint_height + project.roof_overhang * 2)
    angle = max(1.0, min(60.0, project.roof_angle))
    angle_multiplier = 1.0 if project.roof_type == "Плоская" else 1 / max(0.35, cos(radians(angle)))
    roof_area = roof_base_area * roof_multiplier * angle_multiplier
    roof_cost = roof_area * roofing_rate * project.roof_complexity
    finishing_cost = house_area * finishing_rate

    total = walls_cost + foundation_cost + roof_cost + openings_cost + finishing_cost

    return {
        "house_area": house_area,
        "wall_length": length,
        "wall_area": wall_area,
        "walls_cost": walls_cost,
        "foundation_cost": foundation_cost,
        "roof_cost": roof_cost,
        "roof_area": roof_area,
        "openings_cost": openings_cost,
        "finishing_cost": finishing_cost,
        "total": total,
    }


def format_money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def estimate_to_text(project: Project, estimate: dict[str, float]) -> str:
    return "\n".join(
        [
            "Примерная смета дома",
            "",
            f"Этажность: {project.floors}",
            f"Фундамент: {project.foundation_type}",
            f"Крыша: {project.roof_type}",
            f"Кровля: {project.roofing}",
            f"Направление конька: {project.roof_ridge_direction}",
            f"Угол крыши: {project.roof_angle:.0f}°",
            f"Высота конька: {project.roof_ridge_height:.1f} м",
            f"Свес крыши: {project.roof_overhang:.1f} м",
            f"Коэффициент сложности: {project.roof_complexity:.2f}",
            f"Отделка: {project.finishing}",
            f"Стен: {len(project.walls)}",
            f"Дверей: {len(project.doors)}",
            f"Окон в смете: {sum(max(1, window.count) for window in project.windows)}",
            "",
            f"Площадь дома: {estimate['house_area']:.1f} м²",
            f"Общая длина стен: {estimate['wall_length']:.1f} м",
            f"Площадь стен: {estimate['wall_area']:.1f} м²",
            f"Примерная площадь крыши: {estimate['roof_area']:.1f} м²",
            f"Стоимость стен: {format_money(estimate['walls_cost'])}",
            f"Стоимость фундамента: {format_money(estimate['foundation_cost'])}",
            f"Стоимость крыши: {format_money(estimate['roof_cost'])}",
            f"Стоимость окон и дверей: {format_money(estimate['openings_cost'])}",
            f"Стоимость отделки: {format_money(estimate['finishing_cost'])}",
            "",
            f"Итого: {format_money(estimate['total'])}",
            "",
            "Расчёт является приблизительным и подходит для ранней оценки проекта.",
        ]
    )


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, default_value in defaults.items():
        loaded_value = loaded.get(key)
        if isinstance(default_value, dict):
            result[key] = default_value.copy()
            if isinstance(loaded_value, dict):
                result[key].update(loaded_value)
        else:
            result[key] = loaded_value if loaded_value is not None else default_value
    return result
