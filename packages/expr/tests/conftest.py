import sys
import pathlib

# Ensure the src layout package is importable when running pytest directly
# (without `pip install -e .`). Editable install is preferred; this is a fallback.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
