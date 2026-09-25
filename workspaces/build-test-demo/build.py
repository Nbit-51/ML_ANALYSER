import ast
from pathlib import Path

ast.parse(Path("harness.py").read_text())
print("Syntax build passed")
