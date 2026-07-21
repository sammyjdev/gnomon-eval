"""Panel configuration tests (ADR-0012).

Panel members declare distinct vendor families while existing single-judge
configuration remains valid.
"""

import pytest
from pydantic import ValidationError
from test_run_config import VALID_TOML

from gnomon.config.run_config import PanelConfig, PanelJudgeConfig, RunConfig


def test_panel_accepts_two_distinct_vendor_families():
    panel = PanelConfig(
        judges=[
            {"provider": "ollama", "model": "judge-a", "family": "vendor-a"},
            {"provider": "ollama", "model": "judge-b", "family": "vendor-b"},
        ]
    )
    assert [judge.family for judge in panel.judges] == ["vendor-a", "vendor-b"]


def test_panel_rejects_duplicate_vendor_families():
    with pytest.raises(ValidationError, match="duplicate families"):
        PanelConfig(
            judges=[
                {"provider": "ollama", "model": "judge-a", "family": "vendor-a"},
                {"provider": "ollama", "model": "judge-b", "family": "vendor-a"},
            ]
        )


def test_panel_rejects_fewer_than_two_judges():
    with pytest.raises(ValidationError):
        PanelConfig(judges=[{"provider": "ollama", "model": "judge-a", "family": "vendor-a"}])


def test_existing_single_judge_toml_has_no_panel(tmp_path):
    path = tmp_path / "run.toml"
    path.write_text(VALID_TOML, encoding="utf-8")
    assert RunConfig.from_file(path).panel is None


def test_panel_loads_from_toml(tmp_path):
    path = tmp_path / "panel.toml"
    path.write_text(
        VALID_TOML
        + """

[panel]
[[panel.judges]]
provider = "ollama"
model = "judge-a"
family = "vendor-a"

[[panel.judges]]
provider = "stub"
model = "judge-b"
family = "vendor-b"
""",
        encoding="utf-8",
    )
    panel = RunConfig.from_file(path).panel
    assert panel is not None
    assert len(panel.judges) == 2
    assert panel.judges[0].model == "judge-a"
    assert panel.judges[1].family == "vendor-b"


def test_panel_judge_screening_evidence_defaults_to_none():
    judge = PanelJudgeConfig(provider="ollama", model="m", family="f")

    assert judge.screening_evidence is None


def test_panel_judge_carries_screening_evidence_path():
    judge = PanelJudgeConfig(
        provider="ollama",
        model="m",
        family="f",
        screening_evidence="results/screening/m.json",
    )

    assert judge.screening_evidence == "results/screening/m.json"
