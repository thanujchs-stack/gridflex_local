"""Optimization Problem Formulation for Phase 6 Dispatch Planning.

Sets up linear programming decision vectors, bounds, matrices, and multi-objective
cost vectors for optimization within Phase 5 Dynamic Operating Envelopes.
"""

from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd


class OptimizationProblem:
    """Builds standard linear programming matrices for multi-step horizon optimization.

    Minimizes: c^T x
    Subject to:
        A_ub @ x <= b_ub
        A_eq @ x == b_eq
        bounds: l <= x <= u
    """

    def __init__(
        self,
        config: Dict[str, Any],
        opt_config: Dict[str, Any],
        envelopes_df: pd.DataFrame,
        coordination_plan_df: pd.DataFrame,
        net_load_forecast_df: pd.DataFrame,
        pv_forecast_df: pd.DataFrame,
        load_forecast_df: pd.DataFrame,
        initial_bess_soc: float = 0.50,
        participation_rate: float = 0.70,
    ):
        self.config = config
        self.opt_config = opt_config
        self.envelopes_df = envelopes_df.copy()
        self.envelopes_df["timestamp"] = pd.to_datetime(self.envelopes_df["timestamp"])
        self.coordination_plan_df = coordination_plan_df.copy()
        self.coordination_plan_df["timestamp"] = pd.to_datetime(self.coordination_plan_df["timestamp"])
        self.net_load_forecast_df = net_load_forecast_df.copy()
        self.pv_forecast_df = pv_forecast_df.copy()
        self.load_forecast_df = load_forecast_df.copy()

        self.initial_soc = initial_bess_soc
        self.participation_rate = participation_rate

        # Battery parameters
        bat_cfg = config.get("battery", {})
        self.bess_cap = float(bat_cfg.get("energy_capacity_kwh", 100.0))
        self.eta_chg = float(bat_cfg.get("charge_efficiency", 0.95))
        self.eta_dis = float(bat_cfg.get("discharge_efficiency", 0.95))
        self.soc_min = float(bat_cfg.get("min_soc", 0.20))
        self.soc_max = float(bat_cfg.get("max_soc", 0.90))
        self.soc_floor = 0.30  # 20% min + 10% reserve
        self.dt_h = 0.25

        # Extract weights
        w = opt_config.get("weights", {})
        self.w_viol = float(w.get("constraint_violation", 1000.0))
        self.w_act = float(w.get("flexibility_activation", 1.0))
        self.w_curt = float(w.get("pv_curtailment", 10.0))
        self.w_cyc = float(w.get("battery_cycling", 2.5))
        self.w_shift = float(w.get("shifting", 1.5))
        self.w_part = float(w.get("participation", 3.0))

        # Transformer warning limit
        trafo_cfg = config.get("network", {}).get("transformer", {})
        trafo_sn_kva = float(trafo_cfg.get("sn_mva", 0.250)) * 1000.0
        warning_pct = float(opt_config.get("limits", {}).get("transformer_warning_loading_pct", 80.0))
        self.trafo_limit_kw = trafo_sn_kva * 0.95 * (warning_pct / 100.0)  # ~190 kW

        # Unique timesteps
        self.timesteps = sorted(self.envelopes_df["timestamp"].drop_duplicates().tolist())
        self.n_steps = len(self.timesteps)

        # Unique DER lists
        self.pv_ids = sorted(self.envelopes_df[self.envelopes_df["der_type"] == "PV"]["der_id"].drop_duplicates().tolist())
        self.ev_ids = sorted(self.envelopes_df[self.envelopes_df["der_type"] == "EV"]["der_id"].drop_duplicates().tolist())
        self.fl_ids = sorted(self.envelopes_df[self.envelopes_df["der_type"] == "FLEXIBLE_LOAD"]["der_id"].drop_duplicates().tolist())
        self.bess_id = "BESS_COMMUNITY_01"

        self.n_pv = len(self.pv_ids)
        self.n_ev = len(self.ev_ids)
        self.n_fl = len(self.fl_ids)

    def build_matrices(self) -> Dict[str, Any]:
        """Build variables vector indexing, cost vector c, equality and inequality constraints."""
        T = self.n_steps

        # Variable layout per timestep t:
        # 1. P_bat_dis(t) [1]
        # 2. P_bat_chg(t) [1]
        # 3. P_pv_curt(i, t) [n_pv]
        # 4. P_ev_throttle(j, t) [n_ev]
        # 5. P_fl_shift(k, t) [n_fl]
        # 6. P_grid_imp(t) [1]
        # 7. P_grid_exp(t) [1]
        # 8. S_trafo(t) [1]
        # 9. S_volt(t) [1]
        step_var_count = 1 + 1 + self.n_pv + self.n_ev + self.n_fl + 1 + 1 + 1 + 1
        total_vars = step_var_count * T

        # Map variable offsets
        def var_idx(t_idx: int, var_type: str, item_idx: int = 0) -> int:
            base = t_idx * step_var_count
            if var_type == "bat_dis":
                return base + 0
            elif var_type == "bat_chg":
                return base + 1
            elif var_type == "pv_curt":
                return base + 2 + item_idx
            elif var_type == "ev_throttle":
                return base + 2 + self.n_pv + item_idx
            elif var_type == "fl_shift":
                return base + 2 + self.n_pv + self.n_ev + item_idx
            elif var_type == "grid_imp":
                return base + 2 + self.n_pv + self.n_ev + self.n_fl + 0
            elif var_type == "grid_exp":
                return base + 2 + self.n_pv + self.n_ev + self.n_fl + 1
            elif var_type == "s_trafo":
                return base + 2 + self.n_pv + self.n_ev + self.n_fl + 2
            elif var_type == "s_volt":
                return base + 2 + self.n_pv + self.n_ev + self.n_fl + 3
            raise ValueError(f"Unknown var_type: {var_type}")

        # Cost vector c and bounds
        c = np.zeros(total_vars)
        bounds = [(0.0, None) for _ in range(total_vars)]

        for t_idx, t in enumerate(self.timesteps):
            t_envs = self.envelopes_df[self.envelopes_df["timestamp"] == t]
            r_match = self.coordination_plan_df[self.coordination_plan_df["timestamp"] == t]
            risk_state = str(r_match["risk_state"].iloc[0]) if not r_match.empty else "NORMAL"
            risk_mult = 2.0 if risk_state == "CRITICAL" else (1.5 if risk_state == "CONSTRAINED" else 1.0)

            # 1. BESS
            bat_env = t_envs[t_envs["der_type"] == "BESS"]
            max_dis = float(bat_env["dynamic_max_kw"].iloc[0]) if not bat_env.empty else 25.0
            max_chg = abs(float(bat_env["dynamic_min_kw"].iloc[0])) if not bat_env.empty else 25.0

            idx_dis = var_idx(t_idx, "bat_dis")
            idx_chg = var_idx(t_idx, "bat_chg")
            bounds[idx_dis] = (0.0, max(0.0, max_dis))
            bounds[idx_chg] = (0.0, max(0.0, max_chg))
            c[idx_dis] = self.w_act + self.w_cyc
            c[idx_chg] = self.w_act

            # 2. PV
            for i, pid in enumerate(self.pv_ids):
                p_env = t_envs[t_envs["der_id"] == pid]
                curt_allowed = bool(p_env["curtailment_allowed"].iloc[0]) if not p_env.empty else False
                avail_pv = float(p_env["available_pv_kw"].iloc[0]) if not p_env.empty else 0.0
                dyn_max = float(p_env["dynamic_export_limit_kw"].iloc[0]) if not p_env.empty else avail_pv

                # Participation check
                is_participating = (hash(pid) % 100 < self.participation_rate * 100) and curt_allowed
                max_curt = max(0.0, avail_pv - dyn_max) if is_participating else 0.0

                idx_pv = var_idx(t_idx, "pv_curt", i)
                bounds[idx_pv] = (0.0, max(0.0, max_curt))
                c[idx_pv] = self.w_curt

            # 3. EV
            for j, eid in enumerate(self.ev_ids):
                e_env = t_envs[t_envs["der_id"] == eid]
                dyn_chg_lim = float(e_env["dynamic_max_kw"].iloc[0]) if not e_env.empty else 0.0
                rated_ev = 7.4
                is_participating = (hash(eid) % 100 < self.participation_rate * 100)
                max_throttle = max(0.0, rated_ev - dyn_chg_lim) if is_participating else 0.0

                idx_ev = var_idx(t_idx, "ev_throttle", j)
                bounds[idx_ev] = (0.0, max(0.0, max_throttle))
                c[idx_ev] = self.w_shift

            # 4. Flexible Load
            for k, fid in enumerate(self.fl_ids):
                f_env = t_envs[t_envs["der_id"] == fid]
                dyn_max_fl = float(f_env["dynamic_max_kw"].iloc[0]) if not f_env.empty else 0.0
                normal_fl = float(f_env["normal_max_kw"].iloc[0]) if not f_env.empty else 0.0
                is_participating = (hash(fid) % 100 < self.participation_rate * 100)
                max_shift = max(0.0, normal_fl - dyn_max_fl) if is_participating else 0.0

                idx_fl = var_idx(t_idx, "fl_shift", k)
                bounds[idx_fl] = (0.0, max(0.0, max_shift))
                c[idx_fl] = self.w_shift

            # 5. Grid import / export & Slacks
            idx_imp = var_idx(t_idx, "grid_imp")
            idx_exp = var_idx(t_idx, "grid_exp")
            idx_strafo = var_idx(t_idx, "s_trafo")
            idx_svolt = var_idx(t_idx, "s_volt")

            bounds[idx_imp] = (0.0, 500.0)
            bounds[idx_exp] = (0.0, 500.0)
            bounds[idx_strafo] = (0.0, None)
            bounds[idx_svolt] = (0.0, None)

            c[idx_imp] = 0.01  # Minimal economic preference
            c[idx_exp] = 0.00
            c[idx_strafo] = self.w_viol * risk_mult
            c[idx_svolt] = self.w_viol * risk_mult

        # ----------------------------------------------------
        # Equality Constraints (A_eq @ x == b_eq): Power Balance
        # ----------------------------------------------------
        A_eq_list = []
        b_eq_list = []

        for t_idx, t in enumerate(self.timesteps):
            eq_row = np.zeros(total_vars)
            nl_val = float(self.net_load_forecast_df["forecast"].iloc[min(t_idx, len(self.net_load_forecast_df) - 1)])

            # Grid import - Grid export
            eq_row[var_idx(t_idx, "grid_imp")] = 1.0
            eq_row[var_idx(t_idx, "grid_exp")] = -1.0

            # BESS: + discharge relieves grid (acts like generation), - charge increases load
            eq_row[var_idx(t_idx, "bat_dis")] = 1.0
            eq_row[var_idx(t_idx, "bat_chg")] = -1.0

            # PV curtailment: curtailing solar reduces generation, increasing net draw from grid
            for i in range(self.n_pv):
                eq_row[var_idx(t_idx, "pv_curt", i)] = -1.0

            # EV throttle: reducing EV charge reduces load
            for j in range(self.n_ev):
                eq_row[var_idx(t_idx, "ev_throttle", j)] = 1.0

            # FL shift: reducing flexible load reduces load
            for k in range(self.n_fl):
                eq_row[var_idx(t_idx, "fl_shift", k)] = 1.0

            A_eq_list.append(eq_row)
            b_eq_list.append(nl_val)

        # ----------------------------------------------------
        # Inequality Constraints (A_ub @ x <= b_ub)
        # ----------------------------------------------------
        A_ub_list = []
        b_ub_list = []

        # A. Transformer Loading Limits
        for t_idx in range(T):
            # Grid import <= trafo_limit + s_trafo
            # P_grid_imp(t) - S_trafo(t) <= trafo_limit
            ub_row1 = np.zeros(total_vars)
            ub_row1[var_idx(t_idx, "grid_imp")] = 1.0
            ub_row1[var_idx(t_idx, "s_trafo")] = -1.0
            A_ub_list.append(ub_row1)
            b_ub_list.append(self.trafo_limit_kw)

            # Grid export <= trafo_limit
            ub_row2 = np.zeros(total_vars)
            ub_row2[var_idx(t_idx, "grid_exp")] = 1.0
            A_ub_list.append(ub_row2)
            b_ub_list.append(self.trafo_limit_kw)

        # B. Battery Energy Constraints (Cumulative SOC limits)
        # For each step t_end:
        # SOC(t_end) >= soc_floor (0.30)
        # Sum_{tau=0}^{t_end} ( P_dis(tau)*dt/eta_dis - P_chg(tau)*dt*eta_chg ) <= (initial_soc - 0.30) * bess_cap
        for t_end in range(1, T + 1):
            dis_row = np.zeros(total_vars)
            for tau in range(t_end):
                dis_row[var_idx(tau, "bat_dis")] = (self.dt_h / self.eta_dis)
                dis_row[var_idx(tau, "bat_chg")] = -(self.dt_h * self.eta_chg)
            A_ub_list.append(dis_row)
            b_ub_list.append((self.initial_soc - self.soc_floor) * self.bess_cap)

            # SOC(t_end) <= soc_max (0.90)
            chg_row = np.zeros(total_vars)
            for tau in range(t_end):
                chg_row[var_idx(tau, "bat_chg")] = (self.dt_h * self.eta_chg)
                chg_row[var_idx(tau, "bat_dis")] = -(self.dt_h / self.eta_dis)
            A_ub_list.append(chg_row)
            b_ub_list.append((self.soc_max - self.initial_soc) * self.bess_cap)

        # C. EV Departure Energy Constraints (Max throttling across horizon)
        for j, eid in enumerate(self.ev_ids):
            ev_row = np.zeros(total_vars)
            for t_idx in range(T):
                ev_row[var_idx(t_idx, "ev_throttle", j)] = self.dt_h
            # Throttling cannot exceed 50% of nominal daily charge energy to protect departure
            A_ub_list.append(ev_row)
            b_ub_list.append(7.5)  # Max allowable throttling = 7.5 kWh

        # D. Directional Flexibility Requirement (from Phase 4 Coordination Plan)
        for t_idx, t in enumerate(self.timesteps):
            r_match = self.coordination_plan_df[self.coordination_plan_df["timestamp"] == t]
            req_up = float(r_match["required_up_kw"].iloc[0]) if not r_match.empty else 0.0
            req_down = float(r_match["required_down_kw"].iloc[0]) if not r_match.empty else 0.0

            if req_up > 0.01:
                # Relief provided = P_bat_dis - P_bat_chg + sum(ev_throt) + sum(fl_shift) - sum(pv_curt) + S_volt >= req_up
                # -> -P_bat_dis + P_bat_chg - sum(ev_throt) - sum(fl_shift) + sum(pv_curt) - S_volt <= -req_up
                up_row = np.zeros(total_vars)
                up_row[var_idx(t_idx, "bat_dis")] = -1.0
                up_row[var_idx(t_idx, "bat_chg")] = 1.0
                for j in range(self.n_ev):
                    up_row[var_idx(t_idx, "ev_throttle", j)] = -1.0
                for k in range(self.n_fl):
                    up_row[var_idx(t_idx, "fl_shift", k)] = -1.0
                for i in range(self.n_pv):
                    up_row[var_idx(t_idx, "pv_curt", i)] = 1.0
                up_row[var_idx(t_idx, "s_volt")] = -1.0

                A_ub_list.append(up_row)
                b_ub_list.append(-req_up)

            if req_down > 0.01:
                # Downward absorption = P_bat_chg - P_bat_dis + sum(pv_curt) + S_volt >= req_down
                down_row = np.zeros(total_vars)
                down_row[var_idx(t_idx, "bat_chg")] = -1.0
                down_row[var_idx(t_idx, "bat_dis")] = 1.0
                for i in range(self.n_pv):
                    down_row[var_idx(t_idx, "pv_curt", i)] = -1.0
                down_row[var_idx(t_idx, "s_volt")] = -1.0

                A_ub_list.append(down_row)
                b_ub_list.append(-req_down)

        return {
            "c": c,
            "A_eq": np.array(A_eq_list),
            "b_eq": np.array(b_eq_list),
            "A_ub": np.array(A_ub_list),
            "b_ub": np.array(b_ub_list),
            "bounds": bounds,
            "var_idx": var_idx,
            "step_var_count": step_var_count,
            "total_vars": total_vars,
            "timesteps": self.timesteps,
            "pv_ids": self.pv_ids,
            "ev_ids": self.ev_ids,
            "fl_ids": self.fl_ids,
        }
