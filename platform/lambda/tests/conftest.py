"""Shared test fixtures for the Backend API test suite."""

import os
import sys

import pytest

# Ensure the src directory is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
