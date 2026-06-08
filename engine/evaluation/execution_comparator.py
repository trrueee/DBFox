from __future__ import annotations

import math
from typing import Any, List, Dict
from decimal import Decimal
from datetime import datetime, date

class ExecutionIsomorphismComparator:
    """Compares two database result sets for value-set isomorphism."""

    @staticmethod
    def normalize_value(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float, Decimal)):
            # Normalize numeric values to rounded floats to avoid precision mismatches
            return round(float(val), 6)
        if isinstance(val, (datetime, date)):
            return val.isoformat()
        if isinstance(val, str):
            # Clean and strip string values
            return val.strip()
        return val

    def compare(self, expected: List[Dict[str, Any]], actual: List[Dict[str, Any]]) -> bool:
        """Compares two list of dicts for equivalence, ignoring row and column key order/names."""
        if not isinstance(expected, list) or not isinstance(actual, list):
            return False

        if len(expected) != len(actual):
            return False

        # Extract rows as normalized tuples. We sort the keys of each row dict
        # or use values positionally. To handle cases where column aliases are different
        # but the select columns are in the same relative position, we extract values
        # in dictionary insertion order (which matches SQL select expression order).
        # However, to be fully robust, if column names match but are in a different order,
        # we can align actual columns to expected columns by key if keys are identical.
        # Let's align actual rows to expected keys if the keys match, otherwise compare positionally.
        
        expected_rows: List[tuple[Any, ...]] = []
        actual_rows: List[tuple[Any, ...]] = []

        for row in expected:
            expected_rows.append(tuple(self.normalize_value(v) for v in row.values()))

        # Check if actual and expected have the same set of keys (names)
        if expected and actual:
            exp_keys = set(expected[0].keys())
            act_keys = set(actual[0].keys())
            if exp_keys == act_keys:
                # Align actual row keys to expected key order
                key_order = list(expected[0].keys())
                for row in actual:
                    actual_rows.append(tuple(self.normalize_value(row.get(k)) for k in key_order))
            else:
                # Fall back to positional values
                for row in actual:
                    actual_rows.append(tuple(self.normalize_value(v) for v in row.values()))
        else:
            for row in actual:
                actual_rows.append(tuple(self.normalize_value(v) for v in row.values()))

        # Sort the rows so order of rows does not matter
        try:
            # We sort based on str representation to avoid TypeError in Python 3 on mixed types
            expected_sorted = sorted(expected_rows, key=lambda t: tuple(str(x) for x in t))
            actual_sorted = sorted(actual_rows, key=lambda t: tuple(str(x) for x in t))
        except Exception:
            expected_sorted = sorted(expected_rows)
            actual_sorted = sorted(actual_rows)

        # Compare element-wise with tolerance for floats
        for exp_tup, act_tup in zip(expected_sorted, actual_sorted):
            if len(exp_tup) != len(act_tup):
                return False
            for ev, av in zip(exp_tup, act_tup):
                if ev is None or av is None:
                    if ev != av:
                        return False
                elif isinstance(ev, float) and isinstance(av, float):
                    if not math.isclose(ev, av, rel_tol=1e-5, abs_tol=1e-5):
                        return False
                else:
                    if ev != av:
                        return False

        return True
