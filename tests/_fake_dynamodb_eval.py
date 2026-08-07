"""DynamoDB expression evaluation for the FakeDynamoDB test stub."""

from __future__ import annotations

import re
from typing import Any


def eval_condition(
    cond: str,
    record: dict,
    vals: dict,
    names: dict | None = None,
) -> bool:
    names = names or {}
    resolved = cond
    for alias, real in names.items():
        resolved = resolved.replace(alias, real)

    if "attribute_exists" in resolved:
        m = re.search(r"attribute_exists\((\w+)\)", resolved)
        if m and m.group(1) not in record:
            return False
        resolved = re.sub(r"attribute_exists\(\w+\)\s*(AND\s*)?", "", resolved).strip()
        if not resolved:
            return True

    if " OR " in resolved:
        return any(_eval_clause(c.strip(), record, vals) for c in resolved.split(" OR "))

    return all(_eval_clause(c.strip(), record, vals) for c in resolved.split(" AND ") if c.strip())


def _eval_clause(part: str, record: dict, vals: dict) -> bool:
    if "attribute_not_exists" in part:
        m = re.search(r"attribute_not_exists\((\w+)\)", part)
        return m is not None and m.group(1) not in record

    if "<=" in part:
        lhs, rhs = part.split("<=")
        return resolve_token(lhs.strip(), record, vals) <= resolve_token(rhs.strip(), record, vals)
    if "<" in part and "=" not in part:
        lhs, rhs = part.split("<")
        return resolve_token(lhs.strip(), record, vals) < resolve_token(rhs.strip(), record, vals)
    if "=" in part and "!" not in part:
        lhs, rhs = part.split("=")
        return resolve_token(lhs.strip(), record, vals) == resolve_token(rhs.strip(), record, vals)
    return True


def resolve_token(token: str, record: dict, vals: dict) -> Any:
    if token.startswith(":"):
        v = vals.get(token, {})
        return _val(v)
    if "if_not_exists" in token:
        m = re.match(r"if_not_exists\((\w+),\s*(:?\w+)\)", token)
        if m:
            field_name = m.group(1)
            default_ref = m.group(2)
            return record.get(field_name, resolve_token(default_ref, record, vals))
    return record.get(token, 0)


def apply_update(
    expr: str,
    record: dict,
    vals: dict,
    names: dict | None = None,
) -> None:
    names = names or {}
    resolved = expr
    for alias, real in names.items():
        resolved = resolved.replace(alias, real)

    if "REMOVE" in resolved:
        set_part, remove_part = resolved.split("REMOVE")
        for field_name in remove_part.strip().split(","):
            record.pop(field_name.strip(), None)
        resolved = set_part.strip()

    if not resolved.startswith("SET "):
        return
    for assignment in split_assignments(resolved[4:]):
        lhs, rhs = assignment.split("=", 1)
        lhs = lhs.strip()
        rhs = rhs.strip()

        if "+" in rhs:
            parts = rhs.split("+")
            val = sum(resolve_token(p.strip(), record, vals) for p in parts)
        elif "-" in rhs:
            parts = rhs.split("-")
            val = resolve_token(parts[0].strip(), record, vals)
            for p in parts[1:]:
                val -= resolve_token(p.strip(), record, vals)
        else:
            val = resolve_token(rhs, record, vals)
        record[lhs] = val


def split_assignments(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def match_key_condition(kce: str, record: dict, vals: dict) -> bool:
    if "=" not in kce:
        return True
    lhs, rhs = kce.split("=")
    if lhs.strip().startswith(":"):
        lhs_val = _val(vals.get(lhs.strip(), {}))
        rhs_val = record.get(rhs.strip())
    else:
        lhs_val = record.get(lhs.strip().replace(":", ""))
        rhs_val = _val(vals.get(rhs.strip(), {}))
    return lhs_val == rhs_val


def _val(attr: dict) -> Any:
    if "S" in attr:
        return attr["S"]
    if "N" in attr:
        return int(attr["N"])
    return None


def to_ddb(val: Any) -> dict:
    if isinstance(val, str):
        return {"S": val}
    return {"N": str(val)}
