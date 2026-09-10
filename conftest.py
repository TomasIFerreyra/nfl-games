import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(REPO_ROOT, "apps", "api")
ETL_DIR = os.path.join(REPO_ROOT, "packages", "etl")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ETL_DIR not in sys.path:
    sys.path.insert(0, ETL_DIR)
