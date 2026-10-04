"""Hysteresis controller for envelope chatter prevention.

Implements dual-threshold hysteresis to avoid high-frequency cycling between
unconstrained and restricted operating states.
"""

from typing import Dict, Any, Optional
import pandas as pd


class HysteresisController:
    """Maintains state memory to prevent envelope chatter around boundary conditions."""

    def __init__(self, config: Dict[str, Any]):
        doe_cfg = config.get("doe", {}).get("hysteresis", {})
        self.trafo_activate_pct = float(doe_cfg.get("transformer_activate_pct", 80.0))
        self.trafo_release_pct = float(doe_cfg.get("transformer_release_pct", 75.0))
        self.vm_low_activate_pu = float(doe_cfg.get("voltage_low_activate_pu", 0.950))
        self.vm_low_release_pu = float(doe_cfg.get("voltage_low_release_pu", 0.955))
        self.vm_high_activate_pu = float(doe_cfg.get("voltage_high_activate_pu", 1.050))
        self.vm_high_release_pu = float(doe_cfg.get("voltage_high_release_pu", 1.045))

        # Memory state
        self.current_state: str = "NORMAL"
        self.active_constraint: str = "NONE"
        self.state_history: list = []

    def evaluate_state(
        self,
        raw_risk_state: str,
        trafo_loading_pct: float,
        min_vm_pu: float,
        max_vm_pu: float,
        primary_constraint: str,
    ) -> Dict[str, Any]:
        """Determine filtered risk state using activation/release hysteresis thresholds.

        Returns:
            Dict containing:
                - effective_state: Filtered risk state
                - is_held_by_hysteresis: True if kept in warning/restricted state by hysteresis
                - primary_constraint: Updated or held constraint
        """
        # 1. Check activation triggers
        trafo_over = trafo_loading_pct >= self.trafo_activate_pct
        v_low = min_vm_pu <= self.vm_low_activate_pu
        v_high = max_vm_pu >= self.vm_high_activate_pu

        is_critical = (trafo_loading_pct >= 100.0) or (min_vm_pu < 0.90) or (max_vm_pu > 1.10)

        # 2. Check release conditions
        trafo_cleared = trafo_loading_pct < self.trafo_release_pct
        v_low_cleared = min_vm_pu > self.vm_low_release_pu
        v_high_cleared = max_vm_pu < self.vm_high_release_pu

        new_state = self.current_state
        held_by_hysteresis = False

        if raw_risk_state == "CRITICAL" or is_critical:
            new_state = "CRITICAL"
            self.active_constraint = primary_constraint
        elif raw_risk_state == "CONSTRAINED" or trafo_over or v_low or v_high:
            new_state = "CONSTRAINED"
            if trafo_over:
                self.active_constraint = "TRANSFORMER_OVERLOAD"
            elif v_low:
                self.active_constraint = "VOLTAGE_DROP"
            elif v_high:
                self.active_constraint = "VOLTAGE_RISE"
            else:
                self.active_constraint = primary_constraint
        elif self.current_state in ["CONSTRAINED", "WATCH"]:
            # In constrained/watch state: check if fully released or held by deadband
            all_cleared = trafo_cleared and v_low_cleared and v_high_cleared
            if all_cleared and raw_risk_state not in ["CONSTRAINED", "WATCH"]:
                new_state = "NORMAL"
                self.active_constraint = "NONE"
            else:
                # Held in current state by hysteresis deadband
                new_state = self.current_state
                held_by_hysteresis = True
        else:
            # Currently NORMAL: check if raw state indicates WATCH
            if raw_risk_state == "WATCH":
                new_state = "WATCH"
                self.active_constraint = primary_constraint
            else:
                new_state = "NORMAL"
                self.active_constraint = "NONE"

        self.current_state = new_state
        res = {
            "effective_state": new_state,
            "is_held_by_hysteresis": held_by_hysteresis,
            "primary_constraint": self.active_constraint if new_state != "NORMAL" else "NONE",
        }
        self.state_history.append(res)
        return res
