#!/usr/bin/env python3
"""Lightweight pytest-free test runner (works offline)."""
import asyncio
import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

def discover_test_modules():
    mods = []
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        name = p.stem
        mods.append((name, p))
    return mods

async def main():
    passed = skipped = failed = 0
    failures = []
    for name, path in discover_test_modules():
        module = importlib.import_module(name)
        funcs = []
        for attr in dir(module):
            obj = getattr(module, attr)
            if attr.startswith("test_") and (inspect.iscoroutinefunction(obj) or inspect.isfunction(obj)):
                funcs.append(obj)
        for fn in funcs:
            try:
                if inspect.iscoroutinefunction(fn):
                    await fn()
                else:
                    fn()
                print(f"  PASS {name}.{fn.__name__}")
                passed += 1
            except Exception as e:
                # check skip
                if e.__class__.__name__ == "SkipTest" or "SkipTest" in [c.__name__ for c in type(e).__mro__]:
                    print(f"  SKIP {name}.{fn.__name__}: {e}")
                    skipped += 1
                else:
                    print(f"  FAIL {name}.{fn.__name__}: {type(e).__name__}: {e}")
                    failed += 1
                    failures.append((name, fn.__name__, e))
    print("\n" + "="*50)
    print(f"PASSED={passed} SKIPPED={skipped} FAILED={failed}")
    if failed:
        for name, fn, e in failures:
            print(f"  - {name}.{fn}: {e}")
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
