from typing import List, Dict
import operator
from datetime import datetime

OPS = {
    "=": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}

# -----------------------------
# LOGIC EXPRESSIONS (calculated fields)
# -----------------------------
def apply_logic_expressions(rows: List[Dict], expressions: List[Dict]):
    """
    Each expression:
    {
      "name": "profit",
      "expression": "TotalAmt - TaxAmt"
    }
    """
    for row in rows:
        for expr in expressions or []:
            try:
                row[expr["name"]] = eval(expr["expression"], {}, row)
            except Exception:
                row[expr["name"]] = None
    return rows


# -----------------------------
# LOGIC RULES (boolean gates)
# -----------------------------
def apply_logic_rules(rows: List[Dict], rules: List[Dict]):
    """
    Each rule:
    {
      "field": "profit",
      "operator": ">",
      "value": 0
    }
    """
    filtered = []
    for row in rows:
        passed = True
        for rule in rules or []:
            try:
                op = OPS[rule["operator"]]
                if not op(row.get(rule["field"]), rule["value"]):
                    passed = False
                    break
            except Exception:
                passed = False
                break

        if passed:
            filtered.append(row)

    return filtered


# -----------------------------
# FILTERS (QB/date/entity filters)
# -----------------------------
def apply_filters(rows: List[Dict], filters: List[Dict]):
    """
    Supports:
    - between (dates)
    - equals
    """
    result = rows

    for f in filters or []:
        field = f.get("field")
        op = f.get("operator")
        value = f.get("value")

        if op == "between":
            start, end = value
            result = [
                r for r in result
                if start <= r.get(field) <= end
            ]

        elif op == "=":
            result = [r for r in result if r.get(field) == value]

    return result


# -----------------------------
# FULL PIPELINE
# -----------------------------
def transform_rows(rows, chart):
    rows = apply_logic_expressions(
        rows, chart.logic_expressions
    )
    rows = apply_logic_rules(
        rows, chart.logic_rules
    )
    rows = apply_filters(
        rows, chart.filters
    )
    return rows
