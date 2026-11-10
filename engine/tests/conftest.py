from pathlib import Path

import pytest

from bookpublisher.render.pipeline import Runtime

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture(scope="session")
def runtime(tmp_path_factory):
    rt = Runtime(base=tmp_path_factory.mktemp("bp-cache"), workers=2)
    yield rt
    rt.shutdown()


@pytest.fixture
def samples() -> Path:
    return SAMPLES
