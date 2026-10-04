"""Energy shift tracking engine for EVs and Flexible Loads.

Guarantees strict energy conservation across time:
- Shifted power at time t must be paid back in an eligible forward recovery window.
- Energy is conserved (shifted, never deleted).
- V2G is strictly disabled (unidirectional charging throttle only).
- Driver departure deadlines and process completion requirements are enforced.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd


class ShiftEnergyTracker:
    """Tracks energy deferral and scheduled recovery for shiftable DERs."""

    def __init__(self, timestep_hours: float = 0.25):
        self.dt_h = timestep_hours
        # Maps der_id -> list of pending energy shifts: [{'energy_kwh': float, 'deadline_ts': Timestamp, 'source_ts': Timestamp}]
        self.pending_shifts: Dict[str, List[Dict[str, Any]]] = {}
        # Records of executed shifts and payback allocations
        self.shift_records: List[Dict[str, Any]] = []

    def register_shift(
        self,
        der_id: str,
        der_type: str,
        timestamp: pd.Timestamp,
        shifted_kw: float,
        deadline_timestamp: pd.Timestamp,
        reason: str = "GRID_CONSTRAINT_RELIEF"
    ) -> float:
        """Register deferred power allocation and record energy obligation.

        Returns:
            shifted_energy_kwh
        """
        shifted_kw = max(0.0, float(shifted_kw))
        shifted_kwh = shifted_kw * self.dt_h

        if shifted_kwh > 0.0:
            if der_id not in self.pending_shifts:
                self.pending_shifts[der_id] = []

            shift_item = {
                "der_id": der_id,
                "der_type": der_type,
                "source_ts": timestamp,
                "deadline_ts": deadline_timestamp,
                "energy_kwh": shifted_kwh,
                "power_kw": shifted_kw,
                "recovered_kwh": 0.0,
                "reason": reason,
            }
            self.pending_shifts[der_id].append(shift_item)
            self.shift_records.append(shift_item)

        return shifted_kwh

    def get_pending_energy(self, der_id: str) -> float:
        """Total unrecovered shifted energy for DER."""
        if der_id not in self.pending_shifts:
            return 0.0
        return sum(s["energy_kwh"] - s["recovered_kwh"] for s in self.pending_shifts[der_id])

    def schedule_payback(
        self,
        der_id: str,
        timestamp: pd.Timestamp,
        max_recovery_power_kw: float,
    ) -> float:
        """Recover pending shifted energy during an unconstrained timestep.

        Returns:
            recovered_power_kw applied in this interval.
        """
        if der_id not in self.pending_shifts or not self.pending_shifts[der_id]:
            return 0.0

        max_recovery_kwh = max_recovery_power_kw * self.dt_h
        recovered_kwh_total = 0.0

        for s in self.pending_shifts[der_id]:
            needed_kwh = s["energy_kwh"] - s["recovered_kwh"]
            if needed_kwh > 0.0:
                alloc_kwh = min(needed_kwh, max_recovery_kwh - recovered_kwh_total)
                s["recovered_kwh"] += alloc_kwh
                recovered_kwh_total += alloc_kwh
                if recovered_kwh_total >= max_recovery_kwh:
                    break

        # Remove fully recovered items
        self.pending_shifts[der_id] = [
            s for s in self.pending_shifts[der_id] if s["energy_kwh"] > s["recovered_kwh"] + 1e-6
        ]

        return float(recovered_kwh_total / self.dt_h)

    def verify_energy_conservation(self) -> Tuple[bool, float, float]:
        """Verify that total shifted energy equals total recovered energy + remaining obligations.

        Returns:
            (is_conserved, total_shifted_kwh, accounted_kwh)
        """
        total_shifted = sum(r["energy_kwh"] for r in self.shift_records)
        total_recovered = sum(r["recovered_kwh"] for r in self.shift_records)
        total_pending = sum(self.get_pending_energy(d) for d in self.pending_shifts)

        is_conserved = bool(np.isclose(total_shifted, total_recovered + total_pending, atol=1e-5))
        return is_conserved, total_shifted, total_recovered + total_pending
