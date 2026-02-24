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
                safe_vars = {k: float(v) for k, v in row.items() if isinstance(v, (int, float))}
                row[name] = eval(expr, {"__builtins__": {}}, safe_vars)
            except Exception:
                row[name] = None
        out.append(row)
    return out

# -------------------------
# Logic rules & expression
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
    if not logic_rules and not logic_expression:
        return rows

    out = []
    for r in rows:
        keep = True

        # Apply explicit logic rules (operator-based)
        if logic_rules:
            for rule in logic_rules:
                try:
                    field = rule.get("field")
                    op = OPS.get(rule.get("operator"))
                    target = rule.get("value")
                    value = get_value(r, field)
                    if op:
                        keep = op(value, target)
                    else:
                        keep = False
                except Exception:
                    keep = False
                if not keep:
                    break

        # Apply logic_expression if given
        if keep and logic_expression:
            try:
                # Replace field names with values in row safely
                expr = logic_expression
                for key in r.keys():
                    val = r[key]
                    # Quote string values for safe eval
                    if isinstance(val, str):
                        val = f'"{val}"'
                    expr = expr.replace(key, str(val))
                keep = eval(expr, {"__builtins__": {}})
            except Exception:
                keep = False

        if keep:
            out.append(r)
    return out

# -------------------------
# MAIN ENTRY
# -------------------------
def transform_rows_safe(rows, calculated_fields=None, logic_rules=None, logic_expression=None, filters=None):
    if not rows:
        return []

    rows = copy.deepcopy(rows)
    rows = apply_calculated_fields(rows, calculated_fields)
    rows = apply_logic_rules(rows, logic_rules, logic_expression)
    rows = apply_filters(rows, filters)
    return rows
