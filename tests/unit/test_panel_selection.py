"""Initial panel selection (ADR-0012 #55): config/panel.toml parses into a
three-member panel of distinct vendor families, each backed by a real B4
screening evidence artifact committed under docs/panel/screening/.
"""

from pathlib import Path

from gnomon.config.run_config import RunConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_TOML = REPO_ROOT / "config" / "panel.toml"


def test_panel_toml_loads_three_distinct_families():
    panel = RunConfig.from_file(PANEL_TOML).panel

    assert panel is not None
    assert len(panel.judges) == 3
    families = [judge.family for judge in panel.judges]
    assert len(set(families)) == 3


def test_panel_toml_members_carry_screening_evidence():
    panel = RunConfig.from_file(PANEL_TOML).panel

    for judge in panel.judges:
        assert judge.screening_evidence is not None
        evidence_path = REPO_ROOT / judge.screening_evidence
        assert evidence_path.is_file(), f"missing screening evidence: {evidence_path}"
