"""Unit and Integration Tests for Locational Flexibility Enhancement.

Validates:
1. DER at constrained bus -> DIRECT relevance (factor 1.0)
2. DER upstream -> INDIRECT (same trunk) or LOW_RELEVANCE (substation bus)
3. DER on unrelated feeder section / parallel spur -> NOT_RELEVANT
4. Zero available local flexibility -> constraint remains (unserved > 0)
5. Increasing local flexibility -> constraint relief increases proportionally
6. Locational classification is deterministic
7. Technical vs. Available vs. Selectable distinction is strictly maintained
8. Required CSV artifacts and markdown engineering report are present and complete
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import pandas as pd
import numpy as np

from src.flexibility.locational import (
    LocationalRelevance,
    FEEDER_BUS_METADATA,
    classify_relevance,
    evaluate_locational_flexibility,
    run_locational_flexibility_pipeline,
)


@pytest.fixture(scope="module")
def csv_dir():
    return PROJECT_ROOT / "outputs" / "csv"


@pytest.fixture(scope="module")
def report_dir():
    return PROJECT_ROOT / "outputs" / "reports"


def test_der_at_constrained_bus_direct():
    """DER physically located at the constrained bus must be classified as DIRECT."""
    relevance, factor, reason = classify_relevance(
        der_bus="Bus_Residential_3",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert relevance == LocationalRelevance.DIRECT
    assert factor == 1.0
    assert "colocated" in reason.lower()

    # Solar curtailment at Bus_Residential_3 during voltage rise
    rel_rise, factor_rise, _ = classify_relevance(
        der_bus="Bus_Residential_3",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_RISE",
    )
    assert rel_rise == LocationalRelevance.DIRECT
    assert factor_rise == 1.0


def test_der_upstream_indirect_and_low():
    """DER upstream on radial trunk is INDIRECT; DER at substation bus is LOW_RELEVANCE."""
    # Bus_Residential_2 is upstream of Bus_Residential_3 on the same trunk
    rel_bus2, factor_bus2, reason_bus2 = classify_relevance(
        der_bus="Bus_Residential_2",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert rel_bus2 == LocationalRelevance.INDIRECT
    assert 0.0 < factor_bus2 < 1.0
    assert factor_bus2 == pytest.approx(0.65, abs=0.02)
    assert "upstream" in reason_bus2.lower()

    # Bus_Residential_1 is also upstream of Bus_Residential_3
    rel_bus1, factor_bus1, _ = classify_relevance(
        der_bus="Bus_Residential_1",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert rel_bus1 == LocationalRelevance.INDIRECT
    assert factor_bus1 == pytest.approx(0.35, abs=0.02)

    # Community BESS at Bus_Main_LV / Bus_BESS is at substation bus
    rel_bess, factor_bess, reason_bess = classify_relevance(
        der_bus="Bus_BESS",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert rel_bess == LocationalRelevance.LOW_RELEVANCE
    assert factor_bess == 0.05
    assert "substation" in reason_bess.lower() or "upstream" in reason_bess.lower()


def test_der_on_unrelated_feeder_section_not_relevant():
    """DER on parallel spurs must be classified as NOT_RELEVANT."""
    # Commercial HVAC at Bus_Commercial vs. Bus_Residential_3 voltage constraint
    rel_comm, factor_comm, reason_comm = classify_relevance(
        der_bus="Bus_Commercial",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert rel_comm == LocationalRelevance.NOT_RELEVANT
    assert factor_comm == 0.0
    assert "parallel" in reason_comm.lower() or "separate" in reason_comm.lower()

    # Health centre at Bus_Critical vs. Bus_Residential_3
    rel_crit, factor_crit, _ = classify_relevance(
        der_bus="Bus_Critical",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert rel_crit == LocationalRelevance.NOT_RELEVANT
    assert factor_crit == 0.0

    # Community BESS on Line_BESS cannot relieve Line_Trunk_1 congestion
    rel_bess_line, factor_bess_line, reason_bess_line = classify_relevance(
        der_bus="Bus_BESS",
        constraint_line="Line_Trunk_1",
        constraint_type="LINE_OVERLOAD",
    )
    assert rel_bess_line == LocationalRelevance.NOT_RELEVANT
    assert factor_bess_line == 0.0
    assert "cannot relieve" in reason_bess_line.lower() or "transit" in reason_bess_line.lower()


def test_zero_available_local_flexibility_constraint_remains():
    """When evening local downstream flexibility is zero, constraint remains with unserved > 0."""
    loc_df, sum_df = evaluate_locational_flexibility()

    # Evening undervoltage at 17:15 at Bus_Residential_3
    row_1715 = sum_df[sum_df["constraint_id"] == "C_VOLT_DROP_1715"].iloc[0]
    assert row_1715["constraint_location"] == "Bus_Residential_3"
    assert row_1715["required_flexibility_kw"] == 45.0
    # Total available includes upstream BESS + EV + FL across feeder
    assert row_1715["total_available_flexibility_kw"] > 100.0
    # But locationally relevant flexibility is only ~40.1 kW (due to attenuation & relevance factors)
    assert row_1715["locational_relevant_flexibility_kw"] < row_1715["required_flexibility_kw"]
    # Therefore, unserved flexibility is positive and status is DEFICIT
    assert row_1715["unserved_flexibility_kw"] > 0.0
    assert row_1715["constraint_status"] == "DEFICIT"
    assert "insufficient" in row_1715["locational_limitation"].lower()


def test_increasing_local_flexibility_increases_relief():
    """Increasing local flexibility at constrained bus increases relevant relief 1:1, unrelated does not."""
    # Test colocation: 10 kW added at Bus_Residential_3 provides 10 kW relevant relief
    _, factor_local, _ = classify_relevance(
        der_bus="Bus_Residential_3",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert factor_local == 1.0
    assert 10.0 * factor_local == 10.0

    # Adding 10 kW at Bus_Commercial provides 0 kW relevant relief
    _, factor_unrelated, _ = classify_relevance(
        der_bus="Bus_Commercial",
        constraint_bus="Bus_Residential_3",
        constraint_type="VOLTAGE_DROP",
    )
    assert factor_unrelated == 0.0
    assert 10.0 * factor_unrelated == 0.0


def test_locational_classification_deterministic():
    """Classification must be purely deterministic for repeated invocations."""
    for _ in range(5):
        rel1, fac1, rsn1 = classify_relevance("Bus_Residential_3", "Bus_Residential_3", "VOLTAGE_DROP")
        assert rel1 == LocationalRelevance.DIRECT
        assert fac1 == 1.0

        rel2, fac2, rsn2 = classify_relevance("Bus_BESS", "Bus_Residential_3", "VOLTAGE_DROP")
        assert rel2 == LocationalRelevance.LOW_RELEVANCE
        assert fac2 == 0.05

        rel3, fac3, rsn3 = classify_relevance("Bus_Commercial", "Bus_Residential_3", "VOLTAGE_DROP")
        assert rel3 == LocationalRelevance.NOT_RELEVANT
        assert fac3 == 0.0


def test_technical_vs_available_vs_selectable_distinction():
    """Verifies that available flexibility does not equal selectable flexibility for irrelevant DERs."""
    loc_df, _ = evaluate_locational_flexibility()

    # Filter for C_VOLT_DROP_1715 and BESS
    bess_rows = loc_df[(loc_df["constraint_id"] == "C_VOLT_DROP_1715") & (loc_df["der_bus"] == "Bus_BESS")]
    assert len(bess_rows) > 0
    bess = bess_rows.iloc[0]
    assert bess["available_flexibility_kw"] == 25.0
    # Selectable flexibility is attenuated by relevance factor (0.05 * 25.0 = 1.25 kW)
    assert bess["selectable_flexibility_kw"] == pytest.approx(1.25, rel=1e-2)
    assert bess["selectable_flexibility_kw"] < bess["available_flexibility_kw"]

    # Filter for BESS during C_LINE_REV_1345 on Line_Trunk_1 -> NOT_RELEVANT
    bess_line_rows = loc_df[(loc_df["constraint_id"] == "C_LINE_REV_1345") & (loc_df["der_bus"] == "Bus_BESS")]
    assert len(bess_line_rows) > 0
    bess_line = bess_line_rows.iloc[0]
    assert bess_line["available_flexibility_kw"] == 25.0
    assert bess_line["selectable_flexibility_kw"] == 0.0  # NOT_RELEVANT

    # Filter for any participating EV during C_VOLT_DROP_1715 -> INDIRECT (0.35 factor)
    ev_rows = loc_df[
        (loc_df["constraint_id"] == "C_VOLT_DROP_1715") &
        (loc_df["der_type"] == "EV") &
        (loc_df["available_flexibility_kw"] > 0)
    ]
    assert len(ev_rows) > 0
    ev = ev_rows.iloc[0]
    assert ev["available_flexibility_kw"] > 0.0
    assert ev["selectable_flexibility_kw"] < ev["available_flexibility_kw"]
    assert ev["locational_relevance"] == "INDIRECT"


def test_csv_and_report_artifacts_generated_and_valid(csv_dir, report_dir):
    """Verifies that all required CSV files and reports exist with required schema."""
    loc_csv = csv_dir / "locational_flexibility.csv"
    assert loc_csv.exists(), "locational_flexibility.csv missing"
    df_loc = pd.read_csv(loc_csv)
    expected_loc_cols = [
        "timestamp", "constraint_id", "constraint_type", "constraint_location",
        "der_id", "der_type", "der_bus", "locational_relevance",
        "available_flexibility_kw", "selectable_flexibility_kw", "reason"
    ]
    for col in expected_loc_cols:
        assert col in df_loc.columns, f"Missing column {col} in locational_flexibility.csv"
    assert len(df_loc) > 0

    sum_csv = csv_dir / "constraint_flexibility_summary.csv"
    assert sum_csv.exists(), "constraint_flexibility_summary.csv missing"
    df_sum = pd.read_csv(sum_csv)
    expected_sum_cols = [
        "timestamp", "constraint_id", "required_flexibility_kw",
        "total_available_flexibility_kw", "locational_relevant_flexibility_kw",
        "selected_flexibility_kw", "unserved_flexibility_kw", "constraint_status"
    ]
    for col in expected_sum_cols:
        assert col in df_sum.columns, f"Missing column {col} in constraint_flexibility_summary.csv"
    assert len(df_sum) > 0

    report_md = report_dir / "locational_flexibility_report.md"
    assert report_md.exists(), "locational_flexibility_report.md missing"
    content = report_md.read_text(encoding="utf-8")
    assert "Methodology" in content
    assert "Constraints Identified" in content
    assert "DER Locations" in content
    assert "Evening Undervoltage Explanation" in content
    assert "Evening Line Congestion Explanation" in content
    assert "Limitations" in content
