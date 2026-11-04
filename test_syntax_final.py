#!/usr/bin/env python3
"""Quick test to verify the modified code parses correctly."""
import sys
sys.path.insert(0, '.')

print("Testing classifica.py...")
try:
    import scripts.classifica as c
    print(f"  classifica.py: OK - {len(dir(c))} functions/classes")
    # Check for expected symbols
    assert hasattr(c, 'RegistroRicerca'), "Missing RegistroRicerca class"
    assert hasattr(c, 'TIPI'), "Missing TIPI constant"
    assert hasattr(c, 'TONI'), "Missing TONI constant"
    assert hasattr(c, 'SCHEMA_LOTTO'), "Missing SCHEMA_LOTTO"
    assert hasattr(c, 'SCHEMA_ANALISI'), "Missing SCHEMA_ANALISI"
    assert hasattr(c, 'RegistroRicerca'), "Missing RegistroRicerca class"
    print("  All expected symbols present")
except Exception as e:
    print(f"  classifica.py ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Testing llm.py...")
try:
    import scripts.llm as l
    print(f"  llm.py: OK - {len(dir(l))} functions/classes")
    # Check for TimeoutException
    assert hasattr(l, 'TimeoutException'), "Missing TimeoutException class"
    print("  TimeoutException class present")
except Exception as e:
    print(f"  llm.py ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nAll syntax checks passed!")