from __future__ import annotations

import pandas as pd
import pytest

from cohort_diff.synth import SynthConfig, generate


@pytest.fixture(scope="session")
def tables() -> dict[str, pd.DataFrame]:
    return generate(SynthConfig(n_patients=400, seed=3))
