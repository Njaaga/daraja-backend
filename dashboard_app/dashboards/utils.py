# dashboards/utils.py

import copy
from typing import List, Dict, Any

def get_value(row: dict, field: str):
    """
    Safely get a value from a row using dot notation.
    Example: field="CustomerRef.name"
    """
    if not field or not isinstance(row, dict):
        return None

    val = row
    for part in field.split("."):
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val

def apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, Any]):
    """
    Apply simple filters to rows.
    Filters can be like:
    {
        "equals": {"CustomerRef.name": "ABC"},
        "contains": {"Description": "Test"}
    }
    """
    if not filters:
        return rows

    filtered = []
    for r in rows:
        keep = True

        # Equals filters
        for k, v in filters.get("equals", {}).items():
            if str(get_value(r, k)) != str(v):
                keep = False
                break

        if not keep:
            continue

        # Contains filters
        for k, v in filters.get("contains", {}).items():
            if v.lower() not in str(get_value(r, k) or "").lower():
                keep = False
                break

        if keep:
            filtered.append(r)

    return filtered

def apply_calculated_fields(rows: List[Dict[str, Any]], calculated_fields: List[Dict[str, Any]]):
    """
    Apply calculated fields to rows.
    Each item in calculated_fields can be:
    {"name": "Total", "expression": "Qty * Price"}
    """
    if not calculated_fields:
        return rows

    out = []
    for r in rows:
        r_copy = copy.deepcopy(r)
        for cf in calculated_fields:
            expr = cf.get("expression")
            name = cf.get("name")
            if not expr or not name:
                continue
            # Safe evaluation: only allow arithmetic operations on row values
            try:
                local_vars = {k: float(get_value(r_copy, k) or 0) for k in r_copy}
                r_copy[name] = eval(expr, {"__builtins__": {}}, local_vars)
            except Exception:
                r_copy[name] = None
        out.append(r_copy)
    return out

def apply_logic_rules(rows: List[Dict[str, Any]], logic_rules: List[Dict[str, Any]], logic_expression: str = None):
    """
    Apply logic rules (AND/OR) to filter rows based on custom logic.
    logic_rules example:
    [
        {"field": "Amount", "operator": ">", "value": 100},
        {"field": "Status", "operator": "==", "value": "Open"}
    ]
    logic_expression example: "1 and 2"  # indices correspond to rules
    """
    if not logic_rules:
        return rows

    def check_rule(row, rule):
        op = rule.get("operator")
        field_val = get_value(row, rule.get("field"))
        target_val = rule.get("value")

        if op == "==":
            return str(field_val) == str(target_val)
        elif op == "!=":
            return str(field_val) != str(target_val)
        elif op == ">":
            try:
                return float(field_val or 0) > float(target_val)
            except Exception:
                return False
        elif op == ">=":
            try:
                return float(field_val or 0) >= float(target_val)
            except Exception:
                return False
        elif op == "<":
            try:
                return float(field_val or 0) < float(target_val)
            except Exception:
                return False
        elif op == "<=":
            try:
                return float(field_val or 0) <= float(target_val)
            except Exception:
                return False
        return False

    out = []
    for r in rows:
        results = [check_rule(r, rule) for rule in logic_rules]
        if logic_expression:
            # Replace indices in expression with True/False results
            expr = logic_expression
            for i, val in enumerate(results, start=1):
                expr = expr.replace(str(i), str(val))
            try:
                keep = eval(expr, {"__builtins__": {}})
            except Exception:
                keep = False
        else:
            # Default: AND all rules
            keep = all(results)

        if keep:
            out.append(r)
    return out

def transform_rows_safe(
    rows: List[Dict[str, Any]],
    calculated_fields: List[Dict[str, Any]] = None,
    logic_rules: List[Dict[str, Any]] = None,
    logic_expression: str = None,
    filters: Dict[str, Any] = None
):
    """
    Apply filters, calculated fields, and logic rules to rows.
    """
    if not rows:
        return []

    r = copy.deepcopy(rows)
    r = apply_calculated_fields(r, calculated_fields)
    r = apply_logic_rules(r, logic_rules, logic_expression)
    r = apply_filters(r, filters)
    return r
