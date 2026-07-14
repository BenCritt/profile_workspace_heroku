# pm_calculator_utils.py
#
# ==============================================================================
# PROJECT MANAGEMENT TOOLKIT — CALCULATION UTILITIES
# ==============================================================================
# Pure-math domain logic for the Project Management Toolkit category.
# No external API calls, no network I/O, no Django imports — every function
# here takes primitives in and returns a plain dict out, mirroring the
# conventions in freight_calculator_utils.py (has_* flags, rounded values,
# and *_context / *_label / *_note strings for template banners).
#
# Functions in this module:
#   calculate_evm           — Earned Value Management analysis (CV, SV, CPI,
#                             SPI, EAC forecasts, ETC, VAC, TCPI) per PMBOK.
#   calculate_pert          — Three-point (PERT) estimation: beta and
#                             triangular means, standard deviation, variance,
#                             confidence ranges, and target probability.
#   calculate_critical_path — Critical Path Method: topological sort with
#                             cycle detection, forward/backward pass,
#                             total & free float, and critical path(s).
#
# Formula reference (PMBOK Guide, Earned Value Management):
#   CV   = EV − AC                      (negative = over budget)
#   SV   = EV − PV                      (negative = behind schedule)
#   CPI  = EV ÷ AC                      (< 1.0 = over budget)
#   SPI  = EV ÷ PV                      (< 1.0 = behind schedule)
#   EAC (typical variance)   = BAC ÷ CPI
#   EAC (atypical variance)  = AC + (BAC − EV)
#   EAC (combined CPI × SPI) = AC + (BAC − EV) ÷ (CPI × SPI)
#   ETC  = EAC − AC
#   VAC  = BAC − EAC                    (negative = projected overrun)
#   TCPI (to BAC)        = (BAC − EV) ÷ (BAC − AC)
#   TCPI (to target EAC) = (BAC − EV) ÷ (target EAC − AC)
# ==============================================================================

import math


def calculate_evm(bac, pv, ac, ev=None, percent_complete=None, target_eac=None):
    """
    Performs a full Earned Value Management analysis for a project at a
    given status date: variances, performance indices, all three standard
    EAC forecasts, ETC, VAC, and TCPI feasibility — plus plain-English
    context labels/notes for the template's status banners.

    Args:
        bac (float): Budget at Completion — total authorized budget ($).
        pv (float): Planned Value — budgeted cost of work scheduled ($).
        ac (float): Actual Cost — cost actually incurred to date ($).
        ev (float|None): Earned Value — budgeted cost of work performed ($).
            May be None if percent_complete is supplied instead.
        percent_complete (float|None): Physical % of total scope completed
            (0–100). Used to derive EV (EV = % × BAC) when ev is None.
        target_eac (float|None): Optional management-set EAC target ($).
            When supplied, a TCPI toward that target is calculated.

    Returns:
        dict: Full EVM breakdown. Keys prefixed has_* gate optional blocks
        in the template, mirroring calculate_lane_rate()'s conventions.

    Raises:
        ValueError: If neither ev nor percent_complete is provided.
            (The form's clean() enforces this before the view calls us;
            the raise is a defensive guard for any future callers.)
    """
    # --- Resolve Earned Value -------------------------------------------
    # The form guarantees exactly one of (ev, percent_complete) is present.
    # NOTE: check `is not None`, never truthiness — 0.0 is a legal EV
    # (work has started but nothing has been earned yet).
    if ev is None and percent_complete is None:
        raise ValueError(
            "calculate_evm() requires either ev or percent_complete."
        )

    if ev is None:
        ev = bac * (percent_complete / 100.0)
        ev_source = "percent"
    else:
        ev_source = "direct"

    # --- Core Variances & Indices ---------------------------------------
    # ac and pv are form-enforced >= 0.01, so these divisions are safe.
    cv  = ev - ac
    sv  = ev - pv
    cpi = ev / ac
    spi = ev / pv

    # --- Progress Percentages -------------------------------------------
    pct_complete = (ev / bac) * 100.0   # physical progress (earned)
    pct_planned  = (pv / bac) * 100.0   # where the baseline said we'd be
    pct_spent    = (ac / bac) * 100.0   # can exceed 100% on overruns

    work_remaining   = bac - ev          # budgeted value of remaining scope
    budget_remaining = bac - ac          # can be negative on overruns
    is_complete      = work_remaining <= 0  # EV is form-capped at BAC

    results = {
        # Echo inputs (rounded for display)
        "bac": round(bac, 2),
        "pv": round(pv, 2),
        "ev": round(ev, 2),
        "ac": round(ac, 2),
        "ev_source": ev_source,
        # When EV was derived, the template shows a small provenance note.
        "percent_complete_input": (
            round(percent_complete, 1) if percent_complete is not None else None
        ),

        # Progress
        "pct_complete": round(pct_complete, 1),
        "pct_planned": round(pct_planned, 1),
        "pct_spent": round(pct_spent, 1),
        "work_remaining": round(work_remaining, 2),
        "budget_remaining": round(budget_remaining, 2),
        "abs_budget_remaining": round(abs(budget_remaining), 2),
        "budget_remaining_is_negative": budget_remaining < 0,
        "is_complete": is_complete,

        # Variances (abs values + flags let the template render
        # "−$5,000.00" typography instead of "$-5000.00")
        "cv": round(cv, 2),
        "abs_cv": round(abs(cv), 2),
        "cv_is_favorable": cv >= 0,
        "sv": round(sv, 2),
        "abs_sv": round(abs(sv), 2),
        "sv_is_favorable": sv >= 0,

        # Indices
        "cpi": round(cpi, 3),
        "spi": round(spi, 3),
    }

    # --- Cost Context (CPI bands) ----------------------------------------
    # Banner severity mapping in the template:
    #   under → info | on → (no banner) | over → warning | sig_over → danger
    if cpi >= 1.02:
        cost_context = "under"
        cost_context_label = "Under Budget"
        cost_context_note = (
            "The project is earning more value per dollar than planned. "
            "Cost efficiency is ahead of the baseline."
        )
    elif cpi >= 0.98:
        cost_context = "on"
        cost_context_label = "On Budget"
        cost_context_note = (
            "Cost performance is tracking the baseline within a normal "
            "tolerance band."
        )
    elif cpi >= 0.90:
        cost_context = "over"
        cost_context_label = "Over Budget"
        cost_context_note = (
            "The project is earning less value per dollar than planned. "
            "Identify the cost drivers before the variance compounds."
        )
    else:
        cost_context = "sig_over"
        cost_context_label = "Significantly Over Budget"
        cost_context_note = (
            "Cost efficiency is well below the baseline. At this CPI, a "
            "significant budget overrun is likely without corrective action."
        )

    results["cost_context"] = cost_context
    results["cost_context_label"] = cost_context_label
    results["cost_context_note"] = cost_context_note

    # --- Schedule Context (SPI bands) -------------------------------------
    if spi >= 1.02:
        schedule_context = "ahead"
        schedule_context_label = "Ahead of Schedule"
        schedule_context_note = (
            "Work is being completed faster than the baseline plan."
        )
    elif spi >= 0.98:
        schedule_context = "on"
        schedule_context_label = "On Schedule"
        schedule_context_note = (
            "Schedule performance is tracking the baseline within a normal "
            "tolerance band."
        )
    elif spi >= 0.90:
        schedule_context = "behind"
        schedule_context_label = "Behind Schedule"
        schedule_context_note = (
            "Less work has been completed than planned to date. Review the "
            "critical path for slipping activities."
        )
    else:
        schedule_context = "sig_behind"
        schedule_context_label = "Significantly Behind Schedule"
        schedule_context_note = (
            "Work accomplishment is well below plan. Recovery will likely "
            "require re-sequencing, added resources, or scope decisions."
        )

    results["schedule_context"] = schedule_context
    results["schedule_context_label"] = schedule_context_label
    results["schedule_context_note"] = schedule_context_note

    # --- EAC Forecasts -----------------------------------------------------
    # Atypical (AC + remaining work at budgeted cost) is always computable.
    eac_atypical = ac + work_remaining
    results["eac_atypical"] = round(eac_atypical, 2)

    # Typical (BAC ÷ CPI) requires CPI > 0 — i.e., some value earned.
    if cpi > 0:
        eac_typical = bac / cpi
        results["has_eac_typical"] = True
        results["eac_typical"] = round(eac_typical, 2)
    else:
        eac_typical = None
        results["has_eac_typical"] = False

    # Combined (schedule-adjusted) requires both indices > 0.
    if cpi > 0 and spi > 0:
        eac_combined = ac + (work_remaining / (cpi * spi))
        results["has_eac_combined"] = True
        results["eac_combined"] = round(eac_combined, 2)
    else:
        results["has_eac_combined"] = False

    # Primary forecast for the headline block: the CPI-based ("typical")
    # forecast is the PMBOK default; fall back to atypical when EV = 0.
    if eac_typical is not None:
        eac_primary = eac_typical
        results["eac_primary_label"] = "Typical — BAC ÷ CPI"
        results["forecast_note"] = None
    else:
        eac_primary = eac_atypical
        results["eac_primary_label"] = "Atypical — AC + (BAC − EV)"
        results["forecast_note"] = (
            "CPI-based forecasting requires EV greater than zero. Showing "
            "the atypical-variance forecast: actual cost to date plus all "
            "remaining work at its budgeted cost."
        )

    etc_primary = eac_primary - ac
    vac_primary = bac - eac_primary

    results["eac_primary"] = round(eac_primary, 2)
    results["etc_primary"] = round(etc_primary, 2)
    results["vac_primary"] = round(vac_primary, 2)
    results["abs_vac_primary"] = round(abs(vac_primary), 2)
    results["vac_is_favorable"] = vac_primary >= 0

    # --- TCPI to BAC ---------------------------------------------------------
    # Feasibility of finishing within the original budget at some required
    # future efficiency. Guard the three states in priority order:
    #   complete → exhausted budget → normal calculation.
    if is_complete:
        results["has_tcpi_bac"] = True
        results["tcpi_bac"] = 0.0
        results["tcpi_context"] = "complete"
        results["tcpi_context_label"] = "Project Complete"
        results["tcpi_context_note"] = (
            "All budgeted work has been earned. No remaining work to index."
        )
    elif budget_remaining <= 0:
        results["has_tcpi_bac"] = False
        results["tcpi_context"] = "exhausted"
        results["tcpi_context_label"] = "Budget Exhausted"
        results["tcpi_context_note"] = (
            "Actual costs have reached or exceeded BAC with work remaining, "
            "so finishing within the original budget is no longer possible. "
            "An approved EAC re-baseline is needed."
        )
    else:
        tcpi_bac = work_remaining / budget_remaining
        results["has_tcpi_bac"] = True
        results["tcpi_bac"] = round(tcpi_bac, 3)

        if tcpi_bac <= 1.0:
            results["tcpi_context"] = "on_track"
            results["tcpi_context_label"] = "On Track"
            results["tcpi_context_note"] = (
                "Current efficiency is sufficient to finish within budget."
            )
        elif tcpi_bac <= 1.10:
            results["tcpi_context"] = "achievable"
            results["tcpi_context_label"] = "Achievable"
            results["tcpi_context_note"] = (
                "Finishing on budget requires a modest efficiency "
                "improvement over current performance."
            )
        elif tcpi_bac <= 1.25:
            results["tcpi_context"] = "difficult"
            results["tcpi_context_label"] = "Difficult"
            results["tcpi_context_note"] = (
                "Finishing on budget requires a substantial, sustained "
                "efficiency improvement — treat this as a warning flag."
            )
        else:
            results["tcpi_context"] = "unrealistic"
            results["tcpi_context_label"] = "Unrealistic"
            results["tcpi_context_note"] = (
                "The required efficiency is rarely achievable in practice. "
                "The budget likely needs re-baselining or a scope review."
            )

    # --- TCPI to Management EAC Target (optional) ------------------------------
    # The form enforces target_eac > ac, so the denominator is positive.
    if target_eac is not None and target_eac > 0:
        tcpi_target = work_remaining / (target_eac - ac)
        target_delta = target_eac - eac_primary  # + = more conservative

        results["has_target"] = True
        results["target_eac"] = round(target_eac, 2)
        results["tcpi_target"] = round(max(tcpi_target, 0.0), 3)
        results["target_delta"] = round(target_delta, 2)
        results["abs_target_delta"] = round(abs(target_delta), 2)
        results["target_is_optimistic"] = target_delta < 0
    else:
        results["has_target"] = False

    return results

# ==============================================================================
# PERT / THREE-POINT ESTIMATION
# ==============================================================================
# Formula reference (PMBOK Guide, Estimate Activity Durations / Costs):
#   Beta (PERT) estimate  = (O + 4M + P) ÷ 6
#   Triangular estimate   = (O + M + P) ÷ 3
#   Standard deviation σ  = (P − O) ÷ 6
#   Variance              = σ²
#   Confidence ranges     = estimate ± 1σ (≈68.3%), ± 2σ (≈95.5%),
#                           ± 3σ (≈99.7%)  [normal approximation]
#   Z-score for a target  = (target − estimate) ÷ σ
#   P(X ≤ target)         = Φ(Z), the standard normal CDF
# ==============================================================================


def _normal_cdf(z):
    """
    Standard normal cumulative distribution function Φ(z), implemented
    with math.erf so there's no dependency on scipy:
        Φ(z) = 0.5 × (1 + erf(z ÷ √2))
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def calculate_pert(optimistic, most_likely, pessimistic, target_value=None):
    """
    Performs a three-point (PERT) estimation analysis for a single
    activity: beta and triangular means, standard deviation, variance,
    1–3σ confidence ranges, skew and uncertainty context banners, and —
    when a target is supplied — the Z-score and probability of coming in
    at or under that target.

    All inputs are unit-agnostic: days, hours, or dollars work equally,
    as long as every value uses the same unit.

    Args:
        optimistic (float): Best-case estimate (O). Form-enforced >= 0.
        most_likely (float): Most likely estimate (M). Form-enforced
            O <= M <= P.
        pessimistic (float): Worst-case estimate (P).
        target_value (float|None): Optional deadline/budget in the same
            unit. When supplied, Z-score and completion probability are
            calculated against the beta estimate.

    Returns:
        dict: Full PERT breakdown. Keys prefixed has_* gate optional
        blocks in the template, mirroring calculate_evm()'s conventions.
    """
    # --- Core Estimates ----------------------------------------------------
    beta_estimate = (optimistic + 4.0 * most_likely + pessimistic) / 6.0
    triangular_estimate = (optimistic + most_likely + pessimistic) / 3.0
    sigma = (pessimistic - optimistic) / 6.0
    variance = sigma ** 2

    # σ = 0 iff P == O (which forces O == M == P given the form's
    # ordering validation) — a deterministic, single-point estimate.
    has_spread = sigma > 0

    # How far the weighted mean sits from the mode (M).  Positive delta
    # means the pessimistic tail pulled the estimate above "most likely".
    ml_delta = beta_estimate - most_likely

    results = {
        # Echo inputs (rounded for display)
        "optimistic": round(optimistic, 2),
        "most_likely": round(most_likely, 2),
        "pessimistic": round(pessimistic, 2),

        # Estimates
        "beta_estimate": round(beta_estimate, 2),
        "triangular_estimate": round(triangular_estimate, 2),
        "sigma": round(sigma, 2),
        "variance": round(variance, 2),
        "has_spread": has_spread,

        # Mean-vs-mode adjustment (abs value + flag → clean typography)
        "ml_delta": round(ml_delta, 2),
        "abs_ml_delta": round(abs(ml_delta), 2),
        "ml_delta_is_positive": ml_delta >= 0,

        # Confidence ranges (normal approximation; template always shows
        # the bounded-distribution caveat line beneath these)
        "range_1_low": round(beta_estimate - sigma, 2),
        "range_1_high": round(beta_estimate + sigma, 2),
        "range_2_low": round(beta_estimate - 2 * sigma, 2),
        "range_2_high": round(beta_estimate + 2 * sigma, 2),
        "range_3_low": round(beta_estimate - 3 * sigma, 2),
        "range_3_high": round(beta_estimate + 3 * sigma, 2),
    }

    # --- Skew Context (where M sits between O and P) -------------------------
    # Banner severity mapping in the template:
    #   optimistic_anchor → info | symmetric → (no banner) |
    #   pessimistic_anchor → warning
    if has_spread:
        m_position = (most_likely - optimistic) / (pessimistic - optimistic)

        if m_position <= 0.35:
            skew_context = "optimistic_anchor"
            skew_context_label = "Most Likely Sits Near Best Case"
            skew_context_note = (
                "Your most likely value is close to the optimistic bound, "
                "leaving a long pessimistic tail. The PERT estimate adjusts "
                "above your most likely value to price in that downside risk."
            )
        elif m_position >= 0.65:
            skew_context = "pessimistic_anchor"
            skew_context_label = "Most Likely Sits Near Worst Case"
            skew_context_note = (
                "Your most likely value is close to the pessimistic bound. "
                "Either there is genuinely little downside left, or the "
                "pessimistic estimate hasn't been stretched far enough — "
                "worst-case bounds are commonly underestimated."
            )
        else:
            skew_context = "symmetric"
            skew_context_label = "Balanced Estimate"
            skew_context_note = (
                "Your most likely value sits near the middle of the range, "
                "so the beta and triangular estimates stay close together."
            )

        results["skew_context"] = skew_context
        results["skew_context_label"] = skew_context_label
        results["skew_context_note"] = skew_context_note

    # --- Uncertainty Context (coefficient of variation bands) -----------------
    # cv = σ ÷ estimate.  Only meaningful with spread (σ > 0 implies the
    # beta estimate is also > 0, since all inputs are non-negative).
    if has_spread:
        cv = sigma / beta_estimate
        results["uncertainty_pct"] = round(cv * 100.0, 1)

        if cv < 0.05:
            uncertainty_context = "tight"
            uncertainty_context_label = "Tight Estimate"
            uncertainty_context_note = (
                "The spread between bounds is small relative to the "
                "estimate. Uncertainty is low."
            )
        elif cv < 0.15:
            uncertainty_context = "moderate"
            uncertainty_context_label = "Moderate Uncertainty"
            uncertainty_context_note = (
                "The spread between bounds is in a normal range for a "
                "reasonably understood activity."
            )
        elif cv < 0.30:
            uncertainty_context = "high"
            uncertainty_context_label = "High Uncertainty"
            uncertainty_context_note = (
                "The spread between bounds is large relative to the "
                "estimate. Consider decomposing this activity into "
                "smaller, better-understood pieces."
            )
        else:
            uncertainty_context = "very_high"
            uncertainty_context_label = "Very High Uncertainty"
            uncertainty_context_note = (
                "The pessimistic-to-optimistic spread dominates the "
                "estimate itself. Decompose the work or model it "
                "probabilistically with a Monte Carlo simulation before "
                "committing to dates or budgets."
            )

        results["uncertainty_context"] = uncertainty_context
        results["uncertainty_context_label"] = uncertainty_context_label
        results["uncertainty_context_note"] = uncertainty_context_note
    else:
        results["deterministic_note"] = (
            "There is no spread between the optimistic and pessimistic "
            "bounds, so this is a deterministic single-point estimate — "
            "no uncertainty is being modeled."
        )

    # --- Target Probability (optional) -----------------------------------------
    if target_value is not None:
        results["has_target"] = True
        results["target_value"] = round(target_value, 2)

        if has_spread:
            z = (target_value - beta_estimate) / sigma
            probability = _normal_cdf(z)

            results["has_z"] = True
            results["z_score"] = round(z, 2)
            results["probability_pct"] = round(probability * 100.0, 1)

            # Contextual honesty note when the target falls outside the
            # distribution's actual bounds (the normal approximation
            # assigns probability out there; the real beta cannot).
            if target_value < optimistic:
                results["target_context"] = "below_optimistic"
                results["target_note"] = (
                    "Your target is below even the best-case estimate. "
                    "Under the bounded PERT distribution the true "
                    "probability is effectively 0% — the figure shown "
                    "comes from the normal approximation."
                )
            elif target_value > pessimistic:
                results["target_context"] = "above_pessimistic"
                results["target_note"] = (
                    "Your target is beyond the worst-case estimate. "
                    "Under the bounded PERT distribution the true "
                    "probability is effectively 100% — the figure shown "
                    "comes from the normal approximation."
                )
            else:
                results["target_context"] = "normal"
                results["target_note"] = None
        else:
            # Deterministic estimate: the outcome either meets the
            # target or it doesn't — no Z-score to compute.
            results["has_z"] = False
            results["target_context"] = "deterministic"
            if target_value >= beta_estimate:
                results["probability_pct"] = 100.0
                results["target_note"] = (
                    "With a single-point estimate, a target at or above "
                    "the estimate is met with certainty under this model."
                )
            else:
                results["probability_pct"] = 0.0
                results["target_note"] = (
                    "With a single-point estimate, a target below the "
                    "estimate cannot be met under this model."
                )
    else:
        results["has_target"] = False

    return results

# ==============================================================================
# CRITICAL PATH METHOD (CPM)
# ==============================================================================
# Formula reference (PMBOK Guide, Develop Schedule / schedule network
# analysis, zero-based convention):
#   Forward pass:   ES = max(EF of predecessors), 0 for start activities
#                   EF = ES + duration
#   Backward pass:  LF = min(LS of successors), project duration for
#                   finish activities
#                   LS = LF − duration
#   Total float:    TF = LS − ES  (equivalently LF − EF)
#   Free float:     FF = min(ES of successors) − EF
#                   (for finish activities: project duration − EF)
#   Critical path:  the chain(s) of activities with TF = 0
#
# The activity list arrives pre-validated from CPMCalculatorForm: unique
# IDs, non-negative durations, and predecessor references already resolved
# to canonical IDs.  The one thing the form cannot check without running
# the scheduling algorithm itself is circular dependency — so cycle
# detection lives here, and a cycle raises ValueError with a
# user-friendly message for the view's error_message pattern.
# ==============================================================================

# Tolerance for float comparisons in the passes.  Durations are floats,
# so "zero float" and "edge continuity" checks must absorb tiny fp error.
_CPM_EPS = 1e-9

# Near-critical threshold: activities with 0 < TF <= 10% of the project
# duration get flagged — that's where schedule surprises usually hide.
_NEAR_CRITICAL_FRACTION = 0.10

# Cap on enumerated critical paths (parallel critical branches can
# multiply combinatorially; the display only needs the first several).
_MAX_CRITICAL_PATHS = 10


def calculate_critical_path(activities):
    """
    Performs a full Critical Path Method analysis on an activity network:
    topological sort (Kahn's algorithm) with cycle detection, forward and
    backward passes, total and free float, critical/near-critical
    flagging, and critical path enumeration.

    Args:
        activities (list[dict]): Pre-validated activity list from
            CPMCalculatorForm, in the user's input order.  Each dict:
                id (str): unique activity ID (canonical casing)
                duration (float): activity duration, >= 0
                predecessors (list[str]): canonical predecessor IDs

    Returns:
        dict: Full CPM breakdown — project duration, per-activity table
        rows (input order), critical path string(s), and banner flags.

    Raises:
        ValueError: If the network contains a circular dependency.  The
            message names the activities involved so the user can fix
            their input; the view surfaces it via error_message.
    """
    # --- Index the network ---------------------------------------------------
    ids = [a["id"] for a in activities]
    duration = {a["id"]: float(a["duration"]) for a in activities}
    preds = {a["id"]: list(a["predecessors"]) for a in activities}

    # Successor map (preserves input order for deterministic output).
    succs = {aid: [] for aid in ids}
    for aid in ids:
        for p in preds[aid]:
            succs[p].append(aid)

    # --- Topological sort (Kahn's algorithm) + cycle detection ---------------
    in_degree = {aid: len(preds[aid]) for aid in ids}
    # Seed with start activities in input order; process FIFO so ties
    # resolve deterministically by input position.
    ready = [aid for aid in ids if in_degree[aid] == 0]
    topo_order = []

    while ready:
        current = ready.pop(0)
        topo_order.append(current)
        for s in succs[current]:
            in_degree[s] -= 1
            if in_degree[s] == 0:
                ready.append(s)

    if len(topo_order) < len(ids):
        # Every unprocessed activity sits on (or downstream of) a cycle.
        stuck = [aid for aid in ids if aid not in set(topo_order)]
        shown = ", ".join(stuck[:10])
        suffix = ", …" if len(stuck) > 10 else ""
        raise ValueError(
            "These activities form or depend on a circular dependency: "
            f"{shown}{suffix}. Remove the loop and recalculate."
        )

    # --- Forward pass (ES / EF) -----------------------------------------------
    es, ef = {}, {}
    for aid in topo_order:
        es[aid] = max((ef[p] for p in preds[aid]), default=0.0)
        ef[aid] = es[aid] + duration[aid]

    project_duration = max(ef.values()) if ef else 0.0

    # --- Backward pass (LS / LF) ------------------------------------------------
    ls, lf = {}, {}
    for aid in reversed(topo_order):
        lf[aid] = min((ls[s] for s in succs[aid]), default=project_duration)
        ls[aid] = lf[aid] - duration[aid]

    # --- Float & criticality ------------------------------------------------------
    total_float, free_float, is_critical = {}, {}, {}
    near_threshold = _NEAR_CRITICAL_FRACTION * project_duration

    for aid in ids:
        # Clamp tiny fp negatives to a clean zero before rounding.
        tf = max(0.0, ls[aid] - es[aid])
        if succs[aid]:
            ff = max(0.0, min(es[s] for s in succs[aid]) - ef[aid])
        else:
            ff = max(0.0, project_duration - ef[aid])
        total_float[aid] = tf
        free_float[aid] = ff
        is_critical[aid] = tf <= _CPM_EPS

    critical_ids = [aid for aid in ids if is_critical[aid]]
    near_critical_ids = [
        aid for aid in ids
        if not is_critical[aid]
        and project_duration > 0
        and total_float[aid] <= near_threshold + _CPM_EPS
    ]

    # --- Critical path enumeration ----------------------------------------------
    # DFS from critical start activities, following only edges that are
    # "tight" (EF of the predecessor meets ES of the successor) between
    # two critical activities.  A critical activity with no tight critical
    # continuation terminates a path.  Enumeration is capped: parallel
    # critical branches multiply, and the display only needs the first few.
    critical_paths = []
    paths_truncated = False

    def _walk(aid, trail):
        nonlocal paths_truncated
        if len(critical_paths) >= _MAX_CRITICAL_PATHS:
            paths_truncated = True
            return
        nxt = [
            s for s in succs[aid]
            if is_critical[s] and abs(es[s] - ef[aid]) <= _CPM_EPS
        ]
        if not nxt:
            critical_paths.append(trail)
            return
        for s in nxt:
            _walk(s, trail + [s])

    for aid in ids:
        if is_critical[aid] and not preds[aid]:
            _walk(aid, [aid])
        if len(critical_paths) >= _MAX_CRITICAL_PATHS:
            paths_truncated = True
            break

    critical_path_displays = [" → ".join(p) for p in critical_paths]

    # --- Assemble results (input order, display-rounded) ---------------------------
    activity_rows = []
    for aid in ids:
        activity_rows.append({
            "id": aid,
            "duration": round(duration[aid], 2),
            "predecessors_display": ", ".join(preds[aid]) if preds[aid] else "—",
            "es": round(es[aid], 2),
            "ef": round(ef[aid], 2),
            "ls": round(ls[aid], 2),
            "lf": round(lf[aid], 2),
            "total_float": round(total_float[aid], 2),
            "free_float": round(free_float[aid], 2),
            "is_critical": is_critical[aid],
            "is_near_critical": aid in near_critical_ids,
        })

    results = {
        "project_duration": round(project_duration, 2),
        "activities": activity_rows,
        "activity_count": len(ids),

        # Critical path(s)
        "critical_count": len(critical_ids),
        "critical_path_display": (
            critical_path_displays[0] if critical_path_displays else ""
        ),
        "critical_paths": critical_path_displays,
        "num_critical_paths": len(critical_path_displays),
        "has_multiple_critical_paths": len(critical_path_displays) > 1,
        "paths_truncated": paths_truncated,

        # Near-critical flagging
        "has_near_critical": len(near_critical_ids) > 0,
        "near_critical_count": len(near_critical_ids),
        "near_critical_display": ", ".join(near_critical_ids),
        "near_critical_threshold": round(near_threshold, 2),
    }

    # --- Banner notes -------------------------------------------------------------------
    if results["has_multiple_critical_paths"]:
        results["multi_path_note"] = (
            "Schedule risk is spread across parallel chains — a slip on "
            "any one of them delays the whole project, and there is no "
            "single sequence to focus recovery efforts on."
        )
    if results["has_near_critical"]:
        results["near_critical_note"] = (
            "These activities have total float within "
            f"{int(_NEAR_CRITICAL_FRACTION * 100)}% of the project "
            "duration. Small slips here can create a brand-new critical "
            "path — watch them as closely as the critical activities."
        )

    return results
