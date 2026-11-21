#!/usr/bin/env python3
"""Usage: python probe_ntes.py 12658 2   (train, days ago). Prints raw NTES structure."""
import json
import sys
from datetime import datetime, timedelta

from ntes import NTESClient
from collect_history import IST, ntes_date_arg


def to_plain(obj, depth=0):
    if depth > 12:
        return "<max depth>"
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): to_plain(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v, depth + 1) for v in obj]
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return to_plain(fn(), depth + 1)
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        return to_plain(vars(obj), depth + 1)
    return repr(obj)


def find_key(obj, key, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.upper() == key:
                yield path + "." + k, v
            yield from find_key(v, key, path + "." + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from find_key(v, key, f"{path}[{i}]")


train, days = sys.argv[1], int(sys.argv[2])
jd = datetime.now(IST).date() - timedelta(days=days)
data = to_plain(NTESClient().live_status(train, ntes_date_arg(jd)))
print(f"=== {train} on {jd} ===")
print(json.dumps(data, indent=2, ensure_ascii=False)[:20000])
for path, stns in find_key(data, "STNS"):
    print(f"\n=== STNS at {path}: {type(stns).__name__}, len={len(stns) if hasattr(stns, '__len__') else '?'}")
    sample = stns[:3] if isinstance(stns, list) else stns
    print(json.dumps(sample, indent=2, ensure_ascii=False))
