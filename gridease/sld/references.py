"""Source fingerprints and scoped observations, not an electrical rules library."""
import json
from importlib.resources import files


def reference_catalog():
    return json.loads(files('gridease.sld').joinpath('reference_catalog.json').read_text(encoding='utf-8'))
