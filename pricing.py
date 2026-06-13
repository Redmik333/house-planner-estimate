from __future__ import annotations

import json
from math import cos, radians
from pathlib import Path
import sys
from typing import Any

from models import Project


WALL_SECTIONS = ("wall_materials", "brick_types", "block_types")


def app_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DEFAULT_MATERIALS_PATH = app_base_path() / "materials.json"


def load_materials(path: Path = DEFAULT_MATERIALS_PATH) -> dict[str, Any]:
    """Читает каталог материалов из JSON и создаёт минимальный файл, если его нет."""
    if not path.exists():
        materials = _fallback_materials()
        save_materials(materials, path)
        return materials

    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)

    materials = _merge_defaults(_fallback_materials(), loaded)
    if materials != loaded:
        save_materials(materials, path)
    return materials


def load_prices(path: Path = DEFAULT_MATERIALS_PATH) -> dict[str, Any]:
    """Старое имя оставлено, чтобы не ломать импорт в старых сборках."""
    return load_materials(path)


def save_materials(materials: dict[str, Any], path: Path = DEFAULT_MATERIALS_PATH) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(materials, file, ensure_ascii=False, indent=2)


def wall_catalog(materials: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for section in WALL_SECTIONS:
        values = materials.get(section, {})
        if isinstance(values, dict):
            result.update(values)
    return result


def wall_material_info(materials: dict[str, Any], name: str) -> dict[str, Any]:
    aliases = {
        "Газоблок": "Газоблок 300 мм",
        "Кирпич": "Кирпич керамический рядовой",
        "Каркас": "Каркас 150 мм",
    }
    return wall_catalog(materials).get(name) or wall_catalog(materials).get(aliases.get(name, name), {})


def material_price_label(name: str, data: dict[str, Any], price_key: str = "price_per_m2") -> str:
    price = float(data.get(price_key, 0) or 0)
    return f"{name} — {format_money(price)}/м²" if price else name


def section_item(materials: dict[str, Any], section: str, name: str) -> dict[str, Any]:
    return dict(materials.get(section, {}).get(name, {}))


def calculate_estimate(project: Project, materials: dict[str, Any]) -> dict[str, float]:
    project.update_auto_roof_height()

    length = project.total_wall_length_m()
    wall_area = project.wall_area_m2()
    footprint_area = project.footprint_area_m2()
    house_area = project.approximate_house_area_m2()
    floor_1_area = project.floor_area_m2(1)
    floor_2_area = project.floor_area_m2(2) if project.floor_mode == "2 этажа" else 0.0

    walls_cost = 0.0
    second_floor_walls_cost = 0.0
    weighted_thickness = 0.0
    for floor in project.visible_floors():
        for wall in floor.walls:
            info = wall_material_info(materials, wall.material)
            default_thickness = float(info.get("thickness_m", wall.thickness) or wall.thickness or 0.3)
            price_per_m3 = float(info.get("price_per_m3", 0) or 0)
            price_per_m2 = float(info.get("price_per_m2", 0) or 0)
            has_manual_rate = wall.price_per_m2 > 0 and abs(wall.price_per_m2 - price_per_m2) > 1
            if has_manual_rate:
                rate = wall.price_per_m2
            elif price_per_m3 > 0:
                rate = price_per_m3 * wall.thickness
            elif default_thickness > 0 and wall.thickness > 0:
                rate = price_per_m2 * (wall.thickness / default_thickness)
            else:
                rate = price_per_m2
            area_multiplier = 1.35 if project.floor_mode == "1 этаж + мансарда" and floor.level == 1 else 1.0
            wall_area_item = wall.area_m2() * area_multiplier
            item_cost = wall_area_item * rate
            walls_cost += item_cost
            if floor.level == 2:
                second_floor_walls_cost += item_cost
            weighted_thickness += wall.length_m * wall.thickness

    avg_thickness = weighted_thickness / length if length > 0 else 0.0

    foundation = section_item(materials, "foundation_types", project.foundation_type)
    foundation_rate = float(foundation.get("price_per_m2", 0) or 0)
    foundation_factor = float(foundation.get("complexity_factor", 1) or 1)
    foundation_cost = footprint_area * foundation_rate * foundation_factor

    roof_metrics = calculate_roof_metrics(project, materials)
    roof_area = roof_metrics["roof_area"]
    roofing = section_item(materials, "roofing_materials", project.roofing)
    roof_type = section_item(materials, "roof_types", project.roof_type)
    roofing_rate = float(roofing.get("price_per_m2", 0) or 0)
    waste_factor = float(roofing.get("waste_factor", 1) or 1)
    install_factor = float(roofing.get("installation_complexity", 1) or 1)
    roof_type_factor = float(roof_type.get("complexity_factor", 1) or 1)
    roofing_cost = roof_area * roofing_rate * waste_factor * install_factor * roof_type_factor * project.roof_complexity
    gable_area = calculate_gable_area(project)
    gable_rate = _gable_rate(project, materials)
    gable_cost = gable_area * gable_rate
    roof_cost = roofing_cost + gable_cost

    windows_cost = sum(_window_price(window, materials) * max(1, window.count) for window in project.all_windows())
    doors_cost = sum(_door_price(door, materials) for door in project.all_doors())
    openings_cost = windows_cost + doors_cost

    insulation = section_item(materials, "insulation_types", project.insulation_type)
    insulation_cost = wall_area * float(insulation.get("price_per_m2", 0) or 0)

    facade = section_item(materials, "facade_finish", project.facade_finish or project.finishing)
    facade_cost = wall_area * float(facade.get("price_per_m2", 0) or 0) * float(facade.get("complexity_factor", 1) or 1)
    finishing_cost = facade_cost

    stairs_cost = sum(_stair_price(stair, materials) for stair in project.all_stairs())
    slab_rate = float(materials.get("flooring", {}).get("slab_price_per_m2", 3800) or 3800)
    slab_cost = floor_1_area * slab_rate if project.floor_mode == "2 этажа" else 0.0
    second_floor_cost = second_floor_walls_cost + slab_cost

    floor_factor = _floor_complexity_factor(project)
    subtotal = walls_cost + foundation_cost + roof_cost + openings_cost + insulation_cost + facade_cost + stairs_cost + slab_cost
    complexity_extra = subtotal * (floor_factor - 1)
    extra_costs_total = sum(max(0.0, float(item.amount)) for item in project.extra_costs)
    total = subtotal + complexity_extra + extra_costs_total
    cost_per_m2 = total / house_area if house_area > 0 else 0.0

    return {
        "house_area": house_area,
        "floor_1_area": floor_1_area,
        "floor_2_area": floor_2_area,
        "total_area": house_area,
        "footprint_area": footprint_area,
        "wall_length": length,
        "wall_area": wall_area,
        "wall_thickness": avg_thickness,
        "total_wall_height": project.total_wall_height_m(),
        "walls_cost": walls_cost,
        "foundation_cost": foundation_cost,
        "roof_cost": roof_cost,
        "roofing_cost": roofing_cost,
        "roof_area": roof_area,
        "roof_slope_count": roof_metrics["slope_count"],
        "roof_slope_area": roof_metrics["slope_area"],
        "roof_ridge_length": roof_metrics["ridge_length"],
        "roof_span_width": roof_metrics["span_width"],
        "roof_base_width": roof_metrics["base_width"],
        "roof_base_depth": roof_metrics["base_depth"],
        "roof_weight": roof_area * float(roofing.get("weight_per_m2", 0) or 0),
        "roof_waste_factor": waste_factor,
        "roof_installation_complexity": install_factor,
        "roof_service_life": float(roofing.get("service_life_years", 0) or 0),
        "gable_area": gable_area,
        "gable_height": project.roof_gable_height,
        "gable_cost": gable_cost,
        "windows_cost": windows_cost,
        "doors_cost": doors_cost,
        "openings_cost": openings_cost,
        "stairs_cost": stairs_cost,
        "slab_cost": slab_cost,
        "second_floor_cost": second_floor_cost,
        "insulation_cost": insulation_cost,
        "facade_cost": facade_cost,
        "finishing_cost": finishing_cost,
        "extra_costs_total": extra_costs_total,
        "floor_complexity_factor": floor_factor,
        "complexity_extra": complexity_extra,
        "cost_per_m2": cost_per_m2,
        "total": total,
    }


def calculate_roof_area(project: Project, materials: dict[str, Any]) -> float:
    return calculate_roof_metrics(project, materials)["roof_area"]


def calculate_roof_metrics(project: Project, materials: dict[str, Any]) -> dict[str, float]:
    width_m, depth_m = project.footprint_bounds_m()
    if width_m <= 0 or depth_m <= 0:
        return {
            "roof_area": 0.0,
            "slope_count": float(project.roof_slope_count()),
            "slope_area": 0.0,
            "ridge_length": 0.0,
            "span_width": 0.0,
            "base_width": 0.0,
            "base_depth": 0.0,
        }
    base_area = (width_m + project.roof_overhang * 2) * (depth_m + project.roof_overhang * 2)
    roof_type = section_item(materials, "roof_types", project.roof_type)
    area_factor = float(roof_type.get("area_factor", 1.25) or 1.25)
    can_edit_angle = bool(roof_type.get("can_edit_angle", project.roof_type != "Плоская"))
    angle = max(1.0, min(60.0, project.roof_angle))
    angle_factor = 1.0 if not can_edit_angle else 1 / max(0.35, cos(radians(angle)))
    roof_area = base_area * area_factor * angle_factor
    slope_count = max(1, project.roof_slope_count())
    return {
        "roof_area": roof_area,
        "slope_count": float(slope_count),
        "slope_area": roof_area / slope_count,
        "ridge_length": project.roof_ridge_length_m(),
        "span_width": project.roof_span_width_m(),
        "base_width": width_m + project.roof_overhang * 2,
        "base_depth": depth_m + project.roof_overhang * 2,
    }


def calculate_gable_area(project: Project) -> float:
    if project.roof_type not in ("Двускатная", "Полувальмовая", "Мансардная"):
        return 0.0
    span = project.roof_span_width_m()
    if span <= 0:
        return 0.0
    count = 2.0
    if project.roof_type == "Полувальмовая":
        count = 1.2
    if project.roof_type == "Мансардная":
        count = 2.0
    return 0.5 * span * max(0.0, project.roof_gable_height) * count


def _gable_rate(project: Project, materials: dict[str, Any]) -> float:
    facade = section_item(materials, "facade_finish", project.facade_finish or project.finishing)
    facade_rate = float(facade.get("price_per_m2", 0) or 0)
    if facade_rate:
        return facade_rate
    wall_info = wall_material_info(materials, project.wall_material)
    return float(wall_info.get("price_per_m2", 0) or 0)


def format_money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def estimate_to_text(project: Project, estimate: dict[str, float]) -> str:
    extra_lines = []
    if project.extra_costs:
        extra_lines = ["", "Дополнительные расходы:"]
        for item in project.extra_costs:
            extra_lines.append(f"- {item.name}: {format_money(item.amount)}")
    return "\n".join(
        [
            "Примерная смета дома",
            "",
            f"Этажность: {project.floor_mode}",
            f"Высота 1 этажа: {project.floor_1_height:.1f} м",
            f"Высота 2 этажа: {project.floor_2_height:.1f} м",
            f"Высота цоколя: {project.plinth_height:.1f} м",
            f"Высота перекрытия: {project.slab_height:.1f} м",
            f"Общая высота стен: {estimate['total_wall_height']:.1f} м",
            f"Фундамент: {project.foundation_type}",
            f"Крыша: {project.roof_type}",
            f"Кровля: {project.roofing}",
            f"Направление конька: {project.roof_ridge_direction}",
            f"Угол крыши: {project.roof_angle:.0f}°",
            f"Высота конька: {project.roof_ridge_height:.1f} м",
            f"Свес крыши: {project.roof_overhang:.1f} м",
            f"Высота фронтона: {project.roof_gable_height:.1f} м",
            f"Коэффициент сложности: {project.roof_complexity:.2f}",
            f"Утепление: {project.insulation_type}",
            f"Фасад: {project.facade_finish}",
            f"Стен: {len(project.all_walls())}",
            f"Дверей: {len(project.all_doors())}",
            f"Окон в смете: {sum(max(1, window.count) for window in project.all_windows())}",
            f"Лестниц: {len(project.all_stairs())}",
            "",
            f"Площадь 1 этажа: {estimate['floor_1_area']:.1f} м²",
            f"Площадь 2 этажа: {estimate['floor_2_area']:.1f} м²",
            f"Площадь дома: {estimate['house_area']:.1f} м²",
            f"Площадь застройки: {estimate['footprint_area']:.1f} м²",
            f"Общая длина стен: {estimate['wall_length']:.1f} м",
            f"Площадь стен: {estimate['wall_area']:.1f} м²",
            f"Средняя толщина стен: {estimate['wall_thickness']:.2f} м",
            f"Примерная площадь крыши: {estimate['roof_area']:.1f} м²",
            f"Площадь одного ската: {estimate['roof_slope_area']:.1f} м²",
            f"Длина конька: {estimate['roof_ridge_length']:.1f} м",
            f"Площадь фронтонов: {estimate['gable_area']:.1f} м²",
            f"Стоимость стен: {format_money(estimate['walls_cost'])}",
            f"Стоимость фундамента: {format_money(estimate['foundation_cost'])}",
            f"Стоимость кровли: {format_money(estimate['roofing_cost'])}",
            f"Стоимость фронтонов: {format_money(estimate['gable_cost'])}",
            f"Стоимость крыши: {format_money(estimate['roof_cost'])}",
            f"Стоимость окон: {format_money(estimate['windows_cost'])}",
            f"Стоимость дверей: {format_money(estimate['doors_cost'])}",
            f"Стоимость лестницы: {format_money(estimate['stairs_cost'])}",
            f"Стоимость перекрытия: {format_money(estimate['slab_cost'])}",
            f"Стоимость второго этажа: {format_money(estimate['second_floor_cost'])}",
            f"Стоимость утепления: {format_money(estimate['insulation_cost'])}",
            f"Стоимость фасада: {format_money(estimate['facade_cost'])}",
            f"Поправка этажности: {format_money(estimate['complexity_extra'])}",
            f"Дополнительные расходы: {format_money(estimate.get('extra_costs_total', 0))}",
            *extra_lines,
            "",
            f"Цена за м²: {format_money(estimate.get('cost_per_m2', 0))}",
            f"Итого: {format_money(estimate['total'])}",
            "",
            "Расчёт является приблизительным и подходит для ранней оценки проекта.",
        ]
    )


def _window_price(window, materials: dict[str, Any]) -> float:
    if window.price > 0:
        return window.price
    template = section_item(materials, "window_templates", window.template_name)
    price = float(template.get("price", 0) or 0)
    if price > 0:
        return price
    price_per_m2 = window.price_per_m2 or float(template.get("price_per_m2", 0) or 0)
    return window.width * window.height * price_per_m2


def _door_price(door, materials: dict[str, Any]) -> float:
    if door.price > 0:
        return door.price
    template = section_item(materials, "door_templates", door.template_name)
    return float(template.get("price", 0) or 0)


def _stair_price(stair, materials: dict[str, Any]) -> float:
    if stair.price > 0:
        return stair.price
    stair_prices = materials.get("stairs", {})
    base_rate = float(stair_prices.get("base_price_per_m2", 18000) or 18000)
    step_rate = float(stair_prices.get("step_price", 2500) or 2500)
    base = max(0.5, stair.width) * max(1.0, stair.length) * base_rate
    steps = max(1, stair.steps) * step_rate
    factor = {"Прямая": 1.0, "Г-образная": 1.18, "П-образная": 1.35}.get(stair.stair_type, 1.0)
    return (base + steps) * factor


def _floor_complexity_factor(project: Project) -> float:
    if project.floor_mode == "2 этажа":
        return 1.08
    if project.floor_mode == "1 этаж + мансарда":
        return 1.12
    return 1.0


def _merge_defaults(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    result = dict(loaded)
    for key, default_value in defaults.items():
        if key not in result:
            result[key] = default_value
        elif isinstance(default_value, dict) and isinstance(result[key], dict):
            nested = dict(default_value)
            nested.update(result[key])
            result[key] = nested
    return result


def _fallback_materials() -> dict[str, Any]:
    # Этот минимальный набор нужен только если пользователь удалил materials.json.
    return {
        "wall_materials": {
            "Газоблок 300 мм": {
                "name": "Газоблок 300 мм",
                "thickness_m": 0.3,
                "price_per_m2": 3200,
                "price_per_m3": 10650,
                "thermal_conductivity": 0.12,
                "weight_per_m2": 135,
                "category": "газоблок",
            },
            "Каркас 150 мм": {
                "name": "Каркас 150 мм",
                "thickness_m": 0.15,
                "price_per_m2": 2400,
                "price_per_m3": 16000,
                "thermal_conductivity": 0.04,
                "weight_per_m2": 55,
                "category": "каркас",
            },
        },
        "brick_types": {
            "Кирпич керамический рядовой": {
                "name": "Кирпич керамический рядовой",
                "price_per_m2": 5200,
                "price_per_piece": 18,
                "pieces_per_m2": 102,
                "weight": 3.5,
                "thickness_m": 0.38,
                "category": "кирпич",
            }
        },
        "block_types": {
            "Пеноблок": {
                "name": "Пеноблок",
                "thickness_m": 0.3,
                "price_per_m2": 2800,
                "price_per_m3": 9300,
                "thermal_conductivity": 0.16,
                "weight_per_m2": 125,
                "category": "блок",
            }
        },
        "roof_types": {
            "Плоская": {"area_factor": 1.0, "complexity_factor": 1.0, "can_edit_ridge_height": False, "can_edit_angle": False, "needs_ridge_line": False},
            "Односкатная": {"area_factor": 1.15, "complexity_factor": 1.05, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": False},
            "Двускатная": {"area_factor": 1.25, "complexity_factor": 1.1, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": True},
            "Вальмовая": {"area_factor": 1.35, "complexity_factor": 1.22, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": True},
            "Полувальмовая": {"area_factor": 1.32, "complexity_factor": 1.28, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": True},
            "Мансардная": {"area_factor": 1.55, "complexity_factor": 1.45, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": True},
            "Шатровая": {"area_factor": 1.4, "complexity_factor": 1.35, "can_edit_ridge_height": True, "can_edit_angle": True, "needs_ridge_line": False},
        },
        "roofing_materials": {
            "Металлочерепица": {"price_per_m2": 2600, "weight_per_m2": 5, "waste_factor": 1.1, "service_life_years": 30, "installation_complexity": 1.0},
            "Профлист": {"price_per_m2": 1900, "weight_per_m2": 4.5, "waste_factor": 1.08, "service_life_years": 25, "installation_complexity": 0.9},
            "Мягкая кровля": {"price_per_m2": 3100, "weight_per_m2": 9, "waste_factor": 1.12, "service_life_years": 35, "installation_complexity": 1.1},
        },
        "foundation_types": {
            "Плита": {"price_per_m2": 8500, "complexity_factor": 1.15},
            "Лента": {"price_per_m2": 6200, "complexity_factor": 1.0},
            "Сваи": {"price_per_m2": 3800, "complexity_factor": 0.85},
        },
        "flooring": {"slab_price_per_m2": 3800},
        "stairs": {"base_price_per_m2": 18000, "step_price": 2500},
        "insulation_types": {"Без утепления": {"price_per_m2": 0, "thermal_conductivity": 0, "thickness_m": 0}},
        "facade_finish": {
            "Без отделки": {"price_per_m2": 0, "complexity_factor": 1.0},
            "Черновая": {"price_per_m2": 9000, "complexity_factor": 1.0},
            "Чистовая": {"price_per_m2": 18000, "complexity_factor": 1.0},
        },
        "window_templates": {
            "Стандартное окно 1.5 x 1.4 м": {"width": 1.5, "height": 1.4, "sill_height": 0.9, "glass_type": "двухкамерный", "price": 24000, "price_per_m2": 0},
            "Свой размер": {"width": 1.2, "height": 1.4, "sill_height": 0.9, "glass_type": "двухкамерный", "price": 0, "price_per_m2": 14500, "custom": True},
        },
        "door_templates": {
            "Входная 0.9 x 2.1 м": {"width": 0.9, "height": 2.1, "price": 42000, "opening_direction": "Наружу", "hinge_side": "Левая"},
            "Свой размер": {"width": 0.9, "height": 2.1, "price": 0, "opening_direction": "Внутрь", "hinge_side": "Левая", "custom": True},
        },
    }
