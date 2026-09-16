"""Reference execution of plan version 1, with binary64 numeric rows.

The first dataset slice accepts numeric columns only. External data must have
an explicit schema, sorted MERGE inputs, and at most one repeating side per key.
Outputs are returned in memory; callers publish them only after successful run.
"""
from __future__ import annotations

import math
from collections import Counter
from copy import deepcopy
from sas_semantics import sas_round, sas_proc_sort, sas_merge_by, sas_sort_key


def normalize_catalog(catalog):
    result = {}
    for raw_name, table in catalog.items():
        name = raw_name.lower()
        if name in result:
            raise ValueError(f"duplicate dataset name: {raw_name}")
        schema = {k.lower(): v for k, v in table["schema"].items()}
        if len(schema) != len(table["schema"]) or any(v != "number" for v in schema.values()):
            raise ValueError("unique numeric columns are required by plan version 1")
        rows = []
        for raw_row in table["rows"]:
            row = {k.lower(): v for k, v in raw_row.items()}
            if len(row) != len(raw_row) or set(row) != set(schema):
                raise ValueError(f"row does not match schema in {name}")
            for key, value in row.items():
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ValueError(f"non-numeric value: {name}.{key}")
                    row[key] = float(value)
                    if not math.isfinite(row[key]):
                        raise ValueError("non-finite inputs must be represented as null")
            rows.append(row)
        result[name] = {"schema": schema, "rows": rows}
    return result


def number(expr, row):
    if expr["kind"] == "variable":
        return row.get(expr["value"])
    return expr["value"]


def round_value(value, unit):
    if value is None or unit is None or unit <= 0:
        return None
    try:
        result = sas_round(value, unit)
        return result if math.isfinite(result) else None
    except (OverflowError, ValueError):
        return None


def run_plan(plan, catalog=None, *, allow_partial=False):
    if plan["version"] != 1:
        raise ValueError("unsupported plan version")
    if plan["tickets"] and not allow_partial:
        raise RuntimeError("saschi: blocked translation. Nothing from this program was executed.")
    tables = normalize_catalog(catalog or {})
    logs = []
    for step in plan["steps"]:
        inputs, keys = step["inputs"], step["by"]
        for name in inputs:
            if name not in tables:
                raise ValueError(f"input dataset is missing: {name}")
        if step["kind"] == "sort":
            table = deepcopy(tables[inputs[0]])
            if not set(keys) <= set(table["schema"]):
                raise ValueError("BY column missing from schema")
            table["rows"] = sas_proc_sort(table["rows"], keys, step["nodupkey"])
            tables[step["name"]] = table
            continue
        schema = {}
        if step["kind"] == "merge":
            for name in inputs:
                if not set(keys) <= set(tables[name]["schema"]):
                    raise ValueError("BY column missing from schema")
                schema.update(tables[name]["schema"])
            sides = [tables[name]["rows"] for name in inputs]
            key = lambda r: tuple(sas_sort_key(r[k]) for k in keys)
            for side in sides:
                if any(key(a) > key(b) for a, b in zip(side, side[1:])):
                    raise ValueError("MERGE requires ascending BY-sorted inputs")
            counts = [Counter(key(row) for row in side) for side in sides]
            if any(n > 1 and counts[1][k] > 1 for k, n in counts[0].items()):
                raise ValueError("DS-003: many-to-many MERGE requires human review")
            rows, _, _ = sas_merge_by(*sides, keys)
            rows = [{name: row.get(name) for name in schema} for row in rows]
        elif inputs:
            schema = dict(tables[inputs[0]]["schema"])
            rows = deepcopy(tables[inputs[0]]["rows"])
        else:
            rows = [{}]
        for op in step["operations"]:
            args = op["args"]
            if op["kind"] in ("assign", "round"):
                schema[args["name"]] = "number"
                for expr in [args["value"]] + ([args["unit"]] if op["kind"] == "round" else []):
                    if expr["kind"] == "variable":
                        schema.setdefault(expr["value"], "number")
            elif op["kind"] == "put":
                for name in args["names"]:
                    schema.setdefault(name, "number")
        output = []
        for input_row in rows:
            row = {name: input_row.get(name) for name in schema}
            for op in step["operations"]:
                args = op["args"]
                if op["kind"] == "assign":
                    row[args["name"]] = number(args["value"], row)
                elif op["kind"] == "round":
                    row[args["name"]] = round_value(number(args["value"], row), number(args["unit"], row))
                elif op["kind"] == "put":
                    logs.append(" ".join(n + "=" + ("." if row.get(n) is None else format(row[n], ".17g")) for n in args["names"]))
                else:
                    raise ValueError(f"unsupported operation: {op['kind']}")
            output.append(row)
        if step["name"] != "_null_":
            tables[step["name"]] = {"schema": schema, "rows": output}
    return {"datasets": tables, "log": logs}
