# dashboards/utils.py

import copy
import operator

# -------------------------
# Safe nested field access
# -------------------------
def get_value(row, field):
    if not row or not field:
        return None

    val = row
    for part in field.split("."):
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


# -------------------------
# Filters
# -------------------------
def apply_filters(rows, filters):
    if not filters:
        return rows

    out = []
    for r in rows:
        ok = True

        for field, expected in filters.get("equals", {}).items():
            if str(get_value(r, field)) != str(expected):
                ok = False
                break

        if not ok:
            continue

        for field, expected in filters.get("contains", {}).items():
            if expected.lower() not in str(get_value(r, field) or "").lower():
                ok = False
                break

        if ok:
            out.append(r)

    return out


# -------------------------
# Calculated fields
# -------------------------
def apply_calculated_fields(rows, calculated_fields):
    if not calculated_fields:
        return rows

    out = []
    for r in rows:
        row = copy.deepcopy(r)

        for cf in calculated_fields:
            name = cf.get("name")
            expr = cf.get("expression")

            if not name or not expr:
                continue

            try:
                # expose only numeric fields
                safe_vars = {
                    k: float(v)
                    for k, v in row.items()
                    if isinstance(v, (int, float))
                }
                row[name] = eval(expr, {"__builtins__": {}}, safe_vars)
            except Exception:
                row[name] = None

        out.append(row)

    return out


# -------------------------
# Logic rules
# -------------------------
OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

def apply_logic_rules(rows, logic_rules, logic_expression=None):
    if not logic_rules:
        return rows

    out = []

    for r in rows:
        results = []

        for rule in logic_rules:
            try:
                field = rule.get("field")
                op = OPS.get(rule.get("operator"))
                target = rule.get("value")
                value = get_value(r, field)

                results.append(op(value, target) if op else False)
            except Exception:
                results.append(False)

        if logic_expression:
            expr = logic_expression
            for i, res in enumerate(results, start=1):
                expr = expr.replace(f"{{{i}}}", str(res))
            try:
                keep = eval(expr, {"__builtins__": {}})
            except Exception:
                keep = False
        else:
            keep = all(results)

        if keep:
            out.append(r)

    return out


# -------------------------
# MAIN ENTRY
# -------------------------
def transform_rows_safe(
    rows,
    calculated_fields=None,
    logic_rules=None,
    logic_expression=None,
    filters=None,
):
    if not rows:
        return []

    rows = copy.deepcopy(rows)
    rows = apply_calculated_fields(rows, calculated_fields)
    rows = apply_logic_rules(rows, logic_rules, logic_expression)
    rows = apply_filters(rows, filters)
    return rows
