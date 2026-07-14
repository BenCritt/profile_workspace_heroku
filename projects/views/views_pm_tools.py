# views/views_pm_tools.py
#
# ============================================================================
# Project Management Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the Project Management Toolkit
# category.  All domain logic (EVM formulas, forecast math, TCPI feasibility
# banding, etc.) is delegated to pm_calculator_utils.py.  These views are
# intentionally thin HTTP adapters.
#
# Tools in this module:
#   pm_tools        — Hub/landing page for the whole category
#   evm_calculator  — Earned Value Management: CV/SV, CPI/SPI, EAC forecasts,
#                     ETC, VAC, and TCPI with plain-English interpretations
#   pert_calculator — Three-point (PERT) estimation: beta/triangular means,
#                     σ, variance, confidence ranges, and target probability
#   critical_path_calculator — Critical Path Method: forward/backward pass,
#                     total & free float, critical path identification
#
# ============================================================================
# EXTERNAL API USAGE
# ============================================================================
# None.  Every tool in this category is pure computation — no Google Maps,
# no third-party data feeds, no network I/O.  This keeps the category free
# to operate at any traffic level with zero API spend.
# ============================================================================

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after


# ===========================================================================
# Project Management Tools Hub
# ===========================================================================
# Static landing page — card grid linking to each PM tool.
# @ensure_csrf_cookie ensures the CSRF cookie is set for any JS-driven
# AJAX requests fired from the hub page's quick-access widgets.
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def pm_tools(request):
    return render(request, "projects/pm_tools.html")


# ===========================================================================
# Earned Value Management (EVM) Calculator
# ===========================================================================
# Performs a full PMBOK-style Earned Value analysis from the four core
# inputs (BAC, PV, EV, AC):
#   1. Variances:  CV = EV − AC, SV = EV − PV
#   2. Indices:    CPI = EV ÷ AC, SPI = EV ÷ PV
#   3. Forecasts:  EAC (typical BAC÷CPI, atypical AC+BAC−EV, and combined
#                  CPI×SPI), plus ETC = EAC − AC and VAC = BAC − EAC
#   4. TCPI:       to BAC always; to a management EAC target when supplied
#
# EV may be entered directly or derived from percent complete
# (EV = % × BAC) — the form enforces exactly one of the two, and the util
# resolves whichever was provided.
#
# GET  → empty EVMCalculatorForm.
# POST → validates; calls pm_calculator_utils.calculate_evm();
#        result dict includes variances, indices, forecast comparison,
#        TCPI feasibility, and context labels for the status banners.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def evm_calculator(request):
    from .. import pm_calculator_utils
    from ..forms import EVMCalculatorForm

    form    = EVMCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data  # short alias; avoids repeated form.cleaned_data["x"]
        context["results"] = pm_calculator_utils.calculate_evm(
            bac=d["bac"],
            pv=d["pv"],
            ac=d["ac"],
            ev=d.get("ev"),                             # None → derive from %
            percent_complete=d.get("percent_complete"), # None → EV entered directly
            target_eac=d.get("target_eac"),             # None → omit TCPI-to-target
        )

    return render(request, "projects/evm_calculator.html", context)


# ===========================================================================
# PERT / Three-Point Estimation Calculator
# ===========================================================================
# Performs a PMBOK-style three-point estimation analysis from optimistic,
# most likely, and pessimistic values:
#   1. Estimates:  beta (O + 4M + P) ÷ 6 and triangular (O + M + P) ÷ 3
#   2. Dispersion: σ = (P − O) ÷ 6 and variance = σ²
#   3. Ranges:     estimate ± 1σ / 2σ / 3σ (normal approximation)
#   4. Target:     Z-score and P(X ≤ target) via the standard normal CDF,
#                  when an optional target value is supplied
#
# Inputs are unit-agnostic (days, hours, or dollars) as long as all
# fields share the same unit.  The form enforces O ≤ M ≤ P; equal values
# are allowed and the util handles the zero-spread case explicitly.
#
# GET  → empty PERTCalculatorForm.
# POST → validates; calls pm_calculator_utils.calculate_pert();
#        result dict includes estimates, dispersion, confidence ranges,
#        skew/uncertainty context banners, and optional target analysis.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def pert_calculator(request):
    from .. import pm_calculator_utils
    from ..forms import PERTCalculatorForm

    form    = PERTCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data  # short alias; avoids repeated form.cleaned_data["x"]
        context["results"] = pm_calculator_utils.calculate_pert(
            optimistic=d["optimistic"],
            most_likely=d["most_likely"],
            pessimistic=d["pessimistic"],
            target_value=d.get("target_value"),  # None → omit probability block
        )

    return render(request, "projects/pert_calculator.html", context)


# ===========================================================================
# Critical Path Method (CPM) Calculator
# ===========================================================================
# Performs a full schedule network analysis on a user-supplied activity
# list (ID, duration, predecessors — parsed and validated by
# CriticalPathCalculatorForm into a structured list):
#   1. Topological sort (Kahn's algorithm) with cycle detection
#   2. Forward pass  → Early Start / Early Finish per activity
#   3. Backward pass → Late Start / Late Finish per activity
#   4. Total float, free float, critical & near-critical flagging
#   5. Critical path enumeration (capped; parallel chains multiply)
#
# ERROR HANDLING SPLIT:
#   Format and reference problems (bad durations, duplicate IDs, unknown
#   predecessors, self-references) are caught by the form with line
#   numbers.  Circular dependencies can only be detected by running the
#   scheduling algorithm itself, so the util raises ValueError for
#   cycles and this view surfaces it via context["error_message"] —
#   the same pattern lane_rate_analyzer uses for route failures.
#
# GET  → empty CriticalPathCalculatorForm.
# POST → validates; calls pm_calculator_utils.calculate_critical_path();
#        result dict includes project duration, the per-activity
#        ES/EF/LS/LF/TF/FF table, and critical path display strings.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def critical_path_calculator(request):
    from .. import pm_calculator_utils
    from ..forms import CriticalPathCalculatorForm

    form    = CriticalPathCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data  # short alias; avoids repeated form.cleaned_data["x"]
        try:
            context["results"] = pm_calculator_utils.calculate_critical_path(
                activities=d["activities"],  # parsed list from clean_activities()
            )
        except ValueError as e:
            # Circular dependency — the only input problem the form
            # cannot detect without running the algorithm itself.
            context["error_message"] = str(e)

    return render(request, "projects/critical_path_calculator.html", context)