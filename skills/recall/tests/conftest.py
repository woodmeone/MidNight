"""pytest conftest for midnight-recall tests. Adds scripts/ to sys.path."""
import sys
import os

# Add the scripts directory to Python path so `from scripts.xxx` works
scripts_dir = os.path.join(os.path.dirname(__file__), '..', 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(scripts_dir))  # parent of scripts/ so `from scripts.xxx` resolves