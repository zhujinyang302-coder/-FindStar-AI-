from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_matching.py"
    spec = importlib.util.spec_from_file_location("evaluate_matching", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample() -> dict:
    return {
        "direction": "lost_to_found",
        "lost_payload": {
            "title": "黑色双肩包",
            "description": "图书馆三楼丢失黑色双肩包，包内有蓝色水杯和一本教材",
            "category": "钱包箱包",
            "color": "黑色",
            "location_code": "LIB-3F",
            "location_text": "图书馆三楼",
            "lost_at": "2026-11-01T09:00:00",
        },
        "found_payload": {
            "title": "黑色双肩包",
            "description": "图书馆三楼拾到黑色双肩包，包内有蓝色水杯和一本教材",
            "category": "钱包箱包",
            "color": "黑色",
            "location_code": "LIB-3F",
            "location_text": "图书馆三楼",
            "found_at": "2026-11-01T10:00:00",
        },
        "label": True,
        "split": "validation",
    }


def test_evaluate_insufficient_samples_marks_unavailable():
    module = _load_module()
    report = module.evaluate([_sample()])
    assert report["conclusion_available"] is False
    assert report["by_direction"]["lost_to_found"]["samples"] == 1


def test_evaluate_hits_positive_candidate():
    module = _load_module()
    report = module.evaluate([_sample()])
    metrics = report["by_direction"]["lost_to_found"]
    assert metrics["top1_hit_rate"] == 1.0
    assert metrics["false_recommend_rate"] == 0.0