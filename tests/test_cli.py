from __future__ import annotations

from pathlib import Path

import pytest

from cohort_diff.cli import main


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("synth")
    assert main(["synth", "--out", str(root), "--patients", "80"]) == 0
    return root


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--condition", "aki"]) == 0
    out = capsys.readouterr().out
    assert "aki_kdigo_48h" in out and "dm_icd" not in out


def test_run_and_compare(data: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "ids.csv"
    assert main(["run", "aki_icd", "--data", str(data), "--out", str(out)]) == 0
    assert out.read_text().startswith("hadm_id")
    report = tmp_path / "r.md"
    args = ["compare", "--condition", "aki", "--data", str(data), "--out", str(report)]
    assert main([*args, "--bootstrap", "50"]) == 0
    text = report.read_text()
    assert "Pairwise overlap" in text and "Uncertainty (patient-level bootstrap)" in text


def test_compare_needs_two(data: Path) -> None:
    assert main(["compare", "aki_icd", "--data", str(data)]) == 2


def test_missing_data(tmp_path: Path) -> None:
    assert main(["run", "aki_icd", "--data", str(tmp_path)]) == 2
