#!/usr/bin/env python3
import ast
import sys

files_to_check = [
    'scripts/classifica.py',
    'scripts/llm.py'
]

all_ok = True
for f in files_to_check:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            source = file.read()
        ast.parse(source)
        print(f'{f}: OK - valid Python syntax')
    except SyntaxError as e:
        print(f'{f}: SYNTAX ERROR - {e}')
        all_ok = False

if all_ok:
    print("\nAll files have valid Python syntax!")
    sys.exit(0)
else:
    sys.exit(1)