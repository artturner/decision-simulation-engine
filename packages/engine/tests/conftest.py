import sys
import pathlib

here = pathlib.Path(__file__).parent

# Engine src — fallback when not installed with `pip install -e .`
sys.path.insert(0, str(here.parent / "src"))

# expr package (sibling in monorepo) — fallback when not installed
expr_src = here.parent.parent.parent / "expr" / "src"
if expr_src.exists():
    sys.path.insert(0, str(expr_src))
