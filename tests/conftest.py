import pathlib
import sys

# Make the src/ layout importable (simforge.*) without installing the package.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
