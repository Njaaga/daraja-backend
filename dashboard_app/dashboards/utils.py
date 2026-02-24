# dashboards/utils.py
import copy
import operator
import re

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
                safe_vars = {k: float(v) for k, v in row.items() if isinstance(v, (int, float))}
                row[name] = eval(expr, {"__builtins__": {}}, safe_vars)
            except Exception:
                row[name] = None
        out.append(row)
    return out

# -------------------------
# Logic rules / expression
# -------------------------
OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

def parse_user_logic_expression(expr: str):
    """
    Convert user-friendly logic expression (single =) to Python
    Example: AccountSubType=LegalProfessionalFees -> AccountSubType == "LegalProfessionalFees"
    Supports multiple conditions: Amount>0 AND AccountSubType=LegalProfessionalFees
    """
    if not expr:
        return None

    # Replace = with == but ignore >=, <=, !=
    expr = re.sub(r'(?<![<>=!])=(?!=)', '==', expr)

    # Add quotes around string literals if missing
    parts = re.split(r'(\s+and\s+|\s+or\s+)', expr, flags=re.IGNORECASE)
    for i, part in enumerate(parts):
        # Skip AND/OR
        if part.strip().lower() in ("and", "or"):
            continue
        m = re.match(r'(\w+)\s*(==|!=|>|>=|<|<=)\s*(.+)', part.strip())
        if m:
            field, op, val = m.groups()
            # Quote if val is not numeric and not already quoted
            if not re.match(r'^-?\d+(\.\d+)?$', val) and not (val.startswith('"') and val.endswith('"')):
                val = f'"{val}"'
            parts[i] = f'{field}{op}{val}'
    return "".join(parts)

def apply_logic_rules(rows, logic_rules=None, logic_expression=None):
    if not logic_rules and not logic_expression:
        return rows

    out = []
    expr = parse_user_logic_expression(logic_expression) if logic_expression else None

    for r in rows:
        # Evaluate each logic_rule individually
        results = []
        if logic_rules:
            for rule in logic_rules:
                try:
                    field = rule.get("field")
                    op = OPS.get(rule.get("operator"))
                    target = rule.get("value")
                    value = get_value(r, field)
                    results.append(op(value, target) if op else False)
                except Exception:
                    results.append(False)

        # Evaluate logic_expression
        keep = True
        if expr:
            # Replace field names with their values in the row
            safe_expr = expr
            for key in r:
                val = r[key]
                # Quote strings
                if isinstance(val, str):
                    val = f'"{val}"'
                safe_expr = re.sub(rf'\b{key}\b', str(val), safe_expr)
            try:
                keep = eval(safe_expr, {"__builtins__": {}})
            except Exception:
                keep = False
        elif results:
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
