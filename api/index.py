"""Vercel entry point for the AHG POS HTTP handler."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ahg_pos.app import POSHandler  # noqa: E402

# Vercel detects this explicit top-level class as its Python HTTP handler.
class handler(POSHandler):
    pass
