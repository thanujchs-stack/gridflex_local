"""Envelope Transition Event Detector for GridFlex Local.

Tracks state transitions (e.g. NORMAL -> CONSTRAINED, CONSTRAINED -> NORMAL)
and limit adjustments for all DERs over the forecast horizon.
"""

from typing import List, Dict, Any
import pandas as pd

from src.envelopes.models import EnvelopeEventRecord


class EnvelopeEventDetector:
    """Detects and logs meaningful dynamic operating envelope transition events."""

    def __init__(self):
        self.events: List[EnvelopeEventRecord] = []

    def detect_events(self, envelopes_df: pd.DataFrame) -> pd.DataFrame:
        """Scan envelopes DataFrame grouped by DER to detect boundary and state changes.

        Returns:
            DataFrame of envelope_events.csv
        """
        self.events = []
        if envelopes_df.empty:
            return pd.DataFrame(columns=[
                "timestamp", "der_id", "previous_state", "new_state",
                "previous_limit_kw", "new_limit_kw", "constraint", "reason"
            ])

        # Group by der_id and process chronologically
        der_groups = envelopes_df.groupby("der_id")

        for der_id, group in der_groups:
            sorted_group = group.sort_values("timestamp")
            prev_state = "NORMAL"
            prev_limit = float(sorted_group["normal_max_kw"].iloc[0])

            for _, row in sorted_group.iterrows():
                t = pd.to_datetime(row["timestamp"])
                curr_state = str(row["risk_state"])
                curr_limit = float(row["dynamic_max_kw"])
                constraint = str(row["constraint_type"])
                reason = str(row["reason"])

                # Trigger event if risk state changes OR if dynamic limit changes by > 0.05 kW
                limit_changed = abs(curr_limit - prev_limit) > 0.05
                state_changed = curr_state != prev_state

                if state_changed or limit_changed:
                    evt = EnvelopeEventRecord(
                        timestamp=t,
                        der_id=str(der_id),
                        previous_state=prev_state,
                        new_state=curr_state,
                        previous_limit_kw=prev_limit,
                        new_limit_kw=curr_limit,
                        constraint=constraint,
                        reason=reason,
                    )
                    self.events.append(evt)
                    prev_state = curr_state
                    prev_limit = curr_limit

        if not self.events:
            return pd.DataFrame(columns=[
                "timestamp", "der_id", "previous_state", "new_state",
                "previous_limit_kw", "new_limit_kw", "constraint", "reason"
            ])

        return pd.DataFrame([e.to_dict() for e in self.events])
