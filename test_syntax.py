#!/usr/bin/env python3
"""Test syntax of classifica.py and llm.py"""
import sys
sys.path.insert(0, '.')

print("Testing classifica.py...")
try:
    import scripts.classifica
    print("  classifica.py: OK")
except Exception as e:
    print(f"  classifica.py: ERROR - {e}")
    sys.exit(1)

print("Testing llm.py...")
try:
    import scripts.llm
    print("  llm.py: OK")
except Exception as e:
    print(f"  llm.py: ERROR - {e}")
    sys.exit(1)

print("\nAll syntax checks passed!")