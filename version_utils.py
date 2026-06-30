"""Shared helpers for comparing JKWorld app and flow versions."""

from __future__ import annotations

from itertools import zip_longest
import re


def version_numbers(version: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", version)]


def compare_numeric_versions(left: str, right: str) -> int:
    left_numbers = version_numbers(left)
    right_numbers = version_numbers(right)
    if not left_numbers or not right_numbers:
        raise ValueError("Both versions must contain at least one number")
    for left_part, right_part in zip_longest(
        left_numbers,
        right_numbers,
        fillvalue=0,
    ):
        if left_part < right_part:
            return -1
        if left_part > right_part:
            return 1
    return 0


def should_update_version(current: str, latest: str) -> bool:
    if not version_numbers(latest):
        return False
    if not version_numbers(current):
        return True
    return compare_numeric_versions(current, latest) < 0


def version_at_least(current: str, minimum: str) -> bool:
    if not version_numbers(minimum):
        return True
    if not version_numbers(current):
        return False
    return compare_numeric_versions(current, minimum) >= 0
