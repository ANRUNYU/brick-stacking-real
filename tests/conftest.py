from pathlib import Path
import pytest
from brick_stacking.runtime.config_loader import load_config


@pytest.fixture
def config():
    return load_config(Path(__file__).resolve().parents[1] / "config/defaults.yaml")
