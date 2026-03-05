# views/views_freight_tools.py
#
# ============================================================================
# Freight Professional Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the Freight Professional Toolkit
# category.  All domain logic (freight class math, FSC tables, FMCSA data
# retrieval, HOS simulation, etc.) is delegated to freight_calculator_utils.py.
# These views are intentionally thin HTTP adapters.
#
# Tools in this module:
#   freight_tools                    — Hub/landing page for the whole category
#   freight_class_calculator         — NMFC class from dims/weight (density method)
#   fuel_surcharge_calculator        — Carrier FSC from DOE diesel price index
#   hos_trip_planner                 — FMCSA Hours of Service itinerary generator
#   freight_safety                   — FMCSA carrier safety lookup by USDOT number
#   tie_down_calculator              — FMCSA-compliant tie-down count / WLL tool
#   cost_per_mile_calculator         — Trucker CPM: fixed + variable cost breakdown
#   linear_foot_calculator           — LTL trailer linear foot & density visualizer
#   detention_layover_fee_calculator — Dwell time fee estimator
#   warehouse_storage_calculator     — Pallet/sqft storage cost calculator
#   partial_rate_calculator          — Partial TL rate from pallet count vs FTL base
#   deadhead_calculator              — Deadhead miles & cost vs loaded revenue
#   multi_stop_splitter              — Per-leg mileage split for multi-stop routes
#   lane_rate_analyzer               — RPM breakdown with FSC for a given lane
#   freight_margin_calculator        — Gross margin / GP between customer & carrier
#
# ============================================================================
# GOOGLE MAPS API USAGE
# ============================================================================
# Several tools (partial_rate, deadhead, multi_stop, lane_rate, freight_margin)
# call utils.get_road_distance(origin_zip, dest_zip) which hits the Google Maps
# Distance Matrix API to return actual driving miles.  To reduce API spend:
#   - ZIP → lat/lon lookups use the local ZIP dataset (zip_data.py), not the
#     Geocoding API.
#   - Road distance results are cached in Django's cache framework.
#   - Tools that don't strictly need road miles (e.g. freight_class) never
#     call the Maps API.
# ============================================================================
# IMPORT NOTE
# ============================================================================
# `requests` is imported at module scope under the alias `_requests` to avoid
# shadowing any local variable named `requests` inside view functions.  The
# freight_safety view uses it to catch network exceptions from the FMCSA API.
# ============================================================================

import requests as _requests  # aliased to avoid shadowing Django's local `requests`

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after


# ===========================================================================
# Freight Tools Hub
# ===========================================================================
# Static landing page — card grid linking to each freight tool.
# @ensure_csrf_cookie ensures the CSRF cookie is set for any JS-driven
# AJAX requests fired from the hub page's quick-access widgets.
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_tools(request):
    return render(request, "projects/freight_tools.html")


# ===========================================================================
# Freight Class Calculator
# ===========================================================================
# Determines the NMFC (National Motor Freight Classification) freight class
# for an LTL shipment using the density classification method:
#   1. Calculate cubic volume from length × width × height (inches → cu ft)
#   2. Calculate density (lbs per cubic foot) from weight / volume
#   3. Map density to NMFC class (50, 55, 60, 65, 70, 77.5, 85, 92.5, 100,
#      110, 125, 150, 175, 200, 250, 300, 400, 500)
# Higher density → lower class → cheaper LTL rates.
#
# GET  → empty FreightClassForm.
# POST → validates; calls freight_calculator_utils.calculate_freight_class();
#        result dict includes volume, density, class, and classification notes.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_class_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import FreightClassForm

    form    = FreightClassForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data  # short alias; avoids repeated form.cleaned_data["x"]
        context["results"] = freight_calculator_utils.calculate_freight_class(
            length=d["length"], width=d["width"], height=d["height"],
            weight_per_unit=d["weight"], quantity=d["quantity"],
        )

    return render(request, "projects/freight_class_calculator.html", context)


# ===========================================================================
# Fuel Surcharge Calculator
# ===========================================================================
# Calculates the fuel surcharge (FSC) for a trip based on the carrier's
# fuel surcharge schedule, which ties the FSC rate to the DOE weekly retail
# diesel price index.  Common approaches include:
#   - Cost-per-mile FSC: extra cents/mile added to the linehaul rate
#   - Percentage FSC: a percentage of the linehaul applied as a surcharge
#
# The user supplies: trip miles, current diesel price ($/gallon), the
# carrier's base price (breakeven price for their FSC schedule), and the
# truck's average MPG.  The util derives the per-gallon fuel cost above
# baseline and converts it to a per-mile and total trip surcharge.
#
# GET  → empty FuelSurchargeForm.
# POST → validates; calls freight_calculator_utils.calculate_fuel_surcharge();
#        result dict includes surcharge per mile, total FSC, and effective rate.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fuel_surcharge_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import FuelSurchargeForm

    form    = FuelSurchargeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_fuel_surcharge(
            miles=d["trip_miles"], current_price=d["current_price"],
            base_price=d["base_price"], mpg=d["mpg"],
        )

    return render(request, "projects/fuel_surcharge_calculator.html", context)


# ===========================================================================
# HOS Trip Planner
# ===========================================================================
# Simulates an FMCSA Hours of Service (HOS) compliant driving itinerary for
# a long-haul trip under the property-carrying driver rules (11-hour driving
# limit, 14-hour window, 30-minute break after 8 hours, 10-hour restart).
#
# Inputs:
#   total_miles   — total trip distance in miles
#   avg_speed     — average highway speed in mph (used to convert miles to hours)
#   start_date    — departure date (date field)
#   start_time    — departure time (time field)
#
# The two date/time fields are combined here (datetime.combine) before being
# passed to the util, which returns a structured itinerary.
#
# GET  → empty HOSTripPlannerForm.
# POST → combines start_date + start_time into a datetime, calls
#        freight_calculator_utils.generate_hos_itinerary(), merges the
#        simulation_results dict into context.  total_trip_miles is also
#        added to context for the results summary header.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def hos_trip_planner(request):
    from datetime import datetime
    from .. import freight_calculator_utils
    from ..forms import HOSTripPlannerForm

    form    = HOSTripPlannerForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d              = form.cleaned_data
        # Combine separate date and time form fields into a single datetime
        # object that the util expects as its start_datetime argument.
        start_datetime = datetime.combine(d["start_date"], d["start_time"])

        simulation_results = freight_calculator_utils.generate_hos_itinerary(
            miles_remaining=d["total_miles"],
            speed=d["avg_speed"],
            start_datetime=start_datetime,
        )
        # simulation_results is a dict; merge its keys directly into context
        # so the template can reference items like {{ itinerary }}, {{ total_hours }}.
        context.update(simulation_results)
        context["total_trip_miles"] = d["total_miles"]

    return render(request, "projects/hos_trip_planner.html", context)


# ===========================================================================
# Freight Carrier Safety Reporter
# ===========================================================================
# Fetches safety and compliance data for a motor carrier from the FMCSA
# (Federal Motor Carrier Safety Administration) Web Services API using a
# USDOT number.  Returns data including:
#   - Company name, address, operating authority status
#   - Safety rating (Satisfactory / Conditional / Unsatisfactory / None)
#   - OOS (out-of-service) rates for drivers and vehicles
#   - Crash and inspection history
#
# The FMCSA API call is made inside freight_calculator_utils to keep HTTP
# logic out of the view layer.  This view handles the two expected failure
# modes:
#   - Carrier not found (API returned empty/None) → user-facing error message
#   - Network/API error (requests exception)      → generic retry message
#
# GET  → empty CarrierSearchForm (single USDOT number field).
# POST → validates; calls get_fmcsa_carrier_data_by_usdot(); sets `carrier`
#        (data dict) or `error` (string) in context.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_safety(request):
    from ..freight_calculator_utils import get_fmcsa_carrier_data_by_usdot
    from ..forms import CarrierSearchForm

    form    = CarrierSearchForm(request.POST or None)
    carrier = None
    error   = None

    if request.method == "POST" and form.is_valid():
        search_value = form.cleaned_data["search_value"]
        try:
            carrier = get_fmcsa_carrier_data_by_usdot(search_value)
            if not carrier:
                # API returned successfully but found no matching carrier.
                error = (
                    "Carrier not found in FMCSA. "
                    "Please verify you're submitting a valid DOT Number."
                )
        except _requests.exceptions.RequestException as e:
            # Network-level failure (timeout, DNS, connection refused, 5xx).
            error = (
                "There was an issue retrieving the carrier data. "
                f"Please try again later. Error: {str(e)}"
            )

    return render(
        request,
        "projects/freight_safety.html",
        {"form": form, "carrier": carrier, "error": error},
    )


# ===========================================================================
# FMCSA Tie-Down Calculator
# ===========================================================================
# Calculates the minimum number of tie-down assemblies required under FMCSA
# 49 CFR Part 393 (Subpart I) to secure cargo on a flatbed or open trailer.
# The rules depend on:
#   - Cargo weight and length
#   - Tie-down assembly Working Load Limit (WLL) — the rated strength of the
#     strap, chain, or binder being used
#
# Key regulation: the aggregate WLL of all tie-downs must be at least 50% of
# the cargo weight, AND the count must meet length-based minimums
# (≥10 ft: 2 tie-downs; add 1 per additional 10 ft).
#
# GET  → empty TieDownForm.
# POST → validates; calls freight_calculator_utils.calculate_required_tie_downs();
#        result dict includes minimum count (by weight rule), minimum count
#        (by length rule), the controlling minimum, and aggregate WLL required.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def tie_down_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import TieDownForm

    form    = TieDownForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_required_tie_downs(
            weight=d["cargo_weight"],
            length=d["cargo_length"],
            strap_wll=d["strap_wll"],
        )

    return render(request, "projects/tie_down_calculator.html", context)


# ===========================================================================
# Cost Per Mile (CPM) Calculator
# ===========================================================================
# Breaks down a trucking operation's total cost per mile into fixed and
# variable components:
#   Fixed (per month, amortised to CPM):
#     truck payment, insurance premiums, other fixed overhead
#   Variable (already in CPM):
#     fuel cost per mile, maintenance & tires per mile, driver pay per mile
#
# The result shows total CPM, fixed CPM, variable CPM, and monthly breakeven
# revenue at the entered monthly mileage.  Useful for owner-operators and
# small fleets evaluating whether a given load rate covers costs.
#
# GET  → empty CPMCalculatorForm.
# POST → validates; calls freight_calculator_utils.calculate_cost_per_mile();
#        result dict includes itemised CPM breakdown and breakeven analysis.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def cost_per_mile_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import CPMCalculatorForm

    form    = CPMCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_cost_per_mile(
            miles=d["monthly_miles"],
            truck_pay=d["truck_payment"],
            insurance=d["insurance"],
            other_fixed=d["other_fixed"],
            fuel_cpm=d["fuel_cpm"],
            maint_cpm=d["maintenance_cpm"],
            driver_cpm=d["driver_pay"],
        )

    return render(request, "projects/cost_per_mile_calculator.html", context)


# ===========================================================================
# LTL Linear Foot & Density Visualizer
# ===========================================================================
# Calculates how much trailer floor space (linear feet) an LTL shipment will
# occupy and the shipment's density (lbs/cu ft), two key metrics that LTL
# carriers use to rate shipments.
#
# LTL trailers are typically 102" wide × 110" tall.  Floor space is calculated
# based on the footprint (length × width) without considering stackability.
# Density determines whether a weight-based or space-based rate is applied.
#
# GET  → empty LinearFootForm.
# POST → validates; calls freight_calculator_utils.calculate_linear_feet();
#        result dict includes linear feet, density, and a simple visualization
#        data set for the template to render a trailer floor diagram.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def linear_foot_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import LinearFootForm

    form    = LinearFootForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_linear_feet(
            length=d["length"],
            width=d["width"],
            height=d["height"],
            weight=d["weight"],
            quantity=d["quantity"],
            is_stackable=d["is_stackable"],  # was missing entirely
        )

    return render(request, "projects/linear_foot_calculator.html", context)


# ===========================================================================
# Detention & Layover Fee Calculator
# ===========================================================================
# Estimates driver detention fees (hourly charges for waiting at a shipper or
# receiver beyond the free-time allowance) and layover fees (flat per-diem for
# an overnight delay).  Common industry standards:
#   - 2 free hours at pickup and delivery
#   - $50–$75/hour detention after the free period
#   - $150–$250/day layover for mandatory-restart delays
#
# GET  → empty DetentionLayoverForm.
# POST → validates; calls freight_calculator_utils.calculate_detention_layover();
#        result dict includes total detention hours, billable hours, and fees.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def detention_layover_fee_calculator(request):
    from datetime import datetime
    from .. import freight_calculator_utils
    from ..forms import DetentionFeeForm  # was: DetentionLayoverForm (does not exist)

    form    = DetentionFeeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        # The form collects arrival and departure as separate date + time fields.
        # Combine them into full datetime objects before passing to the util,
        # matching the same pattern used by hos_trip_planner.
        arrival_dt   = datetime.combine(d["arrival_date"],   d["arrival_time"])
        departure_dt = datetime.combine(d["departure_date"], d["departure_time"])

        # Function is calculate_detention_fee, not calculate_detention_layover.
        # Parameter names match the util signature exactly.
        context["results"] = freight_calculator_utils.calculate_detention_fee(
            arrival_dt=arrival_dt,
            departure_dt=departure_dt,
            free_time_hours=d["free_time_hours"],  # was: free_hours
            hourly_rate=d["hourly_rate"],           # was: detention_rate
        )

    return render(
        request, "projects/detention_layover_fee_calculator.html", context
    )


# ===========================================================================
# Warehouse Storage Calculator
# ===========================================================================
# Calculates warehouse storage costs for a given pallet count or square footage
# over a specified storage period.  Supports both pallet-position pricing
# (common in 3PL billing) and square-footage pricing (common in self-storage
# and smaller warehouses).
#
# GET  → empty WarehouseStorageForm.
# POST → validates; calls freight_calculator_utils.calculate_warehouse_storage();
#        result dict includes storage cost breakdown by week/month.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def warehouse_storage_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import WarehouseStorageForm

    form    = WarehouseStorageForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_warehouse_storage(
            area_length=d["area_length"],
            area_width=d["area_width"],
            p_length=d["pallet_length"],   # form field is pallet_length, util param is p_length
            p_width=d["pallet_width"],     # form field is pallet_width, util param is p_width
            stack_height=d["stack_height"],
        )

    return render(request, "projects/warehouse_storage_calculator.html", context)


# ===========================================================================
# Partial TL Rate Calculator
# ===========================================================================
# Estimates a rate for a partial truckload (PTL/volume LTL) shipment based on
# pallet count relative to a full truckload.  PTL moves occupy a portion of
# the trailer and are priced between LTL (per-100-lb) and FTL (flat rate) models.
#
# Pricing model:
#   PTL rate = (pallets / max_pallets_per_trailer) × FTL_rate × markup_factor
#   subject to a minimum charge floor
#
# GOOGLE MAPS:
#   Calls get_road_distance() to convert origin/dest ZIP codes to actual
#   driving miles.  The rate is then also expressed as a cost-per-mile for
#   comparison.  If the Maps API fails to return a route, an error message is
#   shown and no rate is calculated.
#
# `trailer_name` is looked up from the form's choices dict and added to context
# so the template can display "53' Dry Van" rather than an internal key string.
#
# GET  → empty form.
# POST → geocodes route; if route found, calculates rate; renders results.
#        If Maps API fails, renders error in context instead.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def partial_rate_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import PartialRateForm
    from ..utils import get_road_distance

    form    = PartialRateForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        # Get actual driving miles via Google Maps Distance Matrix API.
        exact_miles = get_road_distance(d["origin_zip"], d["dest_zip"])

        if exact_miles:
            context["results"] = freight_calculator_utils.calculate_partial_rate(
                origin_zip=d["origin_zip"],
                dest_zip=d["dest_zip"],
                distance_miles=exact_miles,
                trailer_type=d["trailer_type"],
                pallets=d["pallets"],
                weight=d["weight"],
                base_ftl_cpm=d["base_ftl_cpm"],
                markup=d["markup"],
                min_charge=d["min_charge"],
            )
            # Translate the internal trailer type key to its display label.
            context["trailer_name"] = dict(
                form.fields["trailer_type"].choices
            )[d["trailer_type"]]
        else:
            context["error_message"] = (
                "Unable to calculate a valid driving route between these ZIP codes."
            )

    return render(request, "projects/partial_rate_calculator.html", context)


# ===========================================================================
# Deadhead Mileage & Cost Calculator
# ===========================================================================
# Calculates the cost of running "empty" (deadhead) miles to reach a pickup
# location, and optionally evaluates whether the loaded portion of the trip
# justifies the deadhead expense.
#
# WORKFLOW:
#   1. Get deadhead miles: current truck position → pickup ZIP (required)
#      If the Maps API can't route this leg, return early with an error.
#   2. Optionally get loaded miles: pickup → delivery ZIP
#      Only attempted if both delivery_zip and load_rate are provided.
#      If the Maps API fails for this leg, return early with an error.
#   3. Call freight_calculator_utils.calculate_deadhead_cost() with all params.
#   4. Echo location context (ZIP codes) back to template for the results header.
#
# EARLY RETURNS:
#   This view uses explicit early returns (render + return) rather than
#   nested if-blocks to keep error handling flat and readable.  Each failure
#   mode exits immediately after setting context["error_message"].
#
# GET  → empty DeadheadCalculatorForm.
# POST → two Maps API calls (deadhead leg always; loaded leg optionally);
#        calculates deadhead cost and optionally revenue vs. cost comparison.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def deadhead_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import DeadheadCalculatorForm
    from ..utils import get_road_distance

    form    = DeadheadCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        # ── Step 1: Deadhead miles (current position → pickup) ──────────────
        deadhead_miles = get_road_distance(d["current_zip"], d["pickup_zip"])

        if not deadhead_miles:
            context["error_message"] = (
                "Unable to calculate a valid driving route between "
                "the current truck location and the pickup ZIP."
            )
            return render(request, "projects/deadhead_calculator.html", context)

        # ── Step 2: Loaded miles (pickup → delivery) — optional ────────────
        loaded_miles = None
        if d.get("delivery_zip") and d.get("load_rate"):
            loaded_miles = get_road_distance(d["pickup_zip"], d["delivery_zip"])
            if not loaded_miles:
                context["error_message"] = (
                    "Unable to calculate a valid driving route between "
                    "the pickup ZIP and the delivery ZIP."
                )
                return render(request, "projects/deadhead_calculator.html", context)

        # ── Step 3: Calculate deadhead cost (and optional revenue comparison) ─
        context["results"] = freight_calculator_utils.calculate_deadhead_cost(
            deadhead_miles=deadhead_miles,
            operating_cpm=d["operating_cpm"],
            load_rate=d.get("load_rate"),        # None → skip revenue comparison
            loaded_miles=loaded_miles,           # None → skip revenue comparison
        )

        # ── Step 4: Echo location context for the results header ────────────
        context["current_zip"]  = d["current_zip"]
        context["pickup_zip"]   = d["pickup_zip"]
        context["delivery_zip"] = d.get("delivery_zip", "")

    return render(request, "projects/deadhead_calculator.html", context)


# ===========================================================================
# Multi-Stop Route Mileage Splitter
# ===========================================================================
# Splits a multi-stop route into individual legs and calculates the mileage
# for each leg using the Google Maps Distance Matrix API.  Useful for:
#   - Billing multi-stop loads with per-leg invoicing
#   - Calculating stop-off charges (common in intermodal and LTL)
#   - Verifying route mileage for fuel tax (IFTA) reporting
#
# INPUT: route_zips is a list of ZIP codes built by the form's clean() method
# from a repeating set of form fields or a delimited text input.
#
# WORKFLOW:
#   1. Validate that there are at least 2 ZIPs (origin + destination).
#   2. For each consecutive pair (leg), call get_road_distance().
#      If any leg fails, return early with a specific error identifying the
#      failed leg by number and the two ZIP codes involved.
#   3. Build a `legs` list of dicts: {from_zip, to_zip, miles}.
#   4. Pass legs to freight_calculator_utils.calculate_multi_stop_route()
#      which aggregates totals and applies stop-off charges.
#
# EARLY RETURNS on Maps API failures preserve the form state so the user
# can fix the specific problematic ZIP code pair.
#
# GET  → empty MultiStopSplitterForm.
# POST → validates; iterates legs; calculates per-leg and total mileage.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def multi_stop_splitter(request):
    from .. import freight_calculator_utils
    from ..forms import MultiStopSplitterForm
    from ..utils import get_road_distance

    form    = MultiStopSplitterForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d          = form.cleaned_data
        route_zips = d["route_zips"]  # list assembled by form.clean()

        if len(route_zips) < 2:
            context["error_message"] = (
                "A route requires at least an origin and a destination."
            )
            return render(request, "projects/multi_stop_splitter.html", context)

        # Build the legs list; fail fast on the first unresolvable leg.
        legs = []
        for i in range(len(route_zips) - 1):
            from_zip = route_zips[i]
            to_zip   = route_zips[i + 1]
            miles    = get_road_distance(from_zip, to_zip)

            if not miles:
                context["error_message"] = (
                    f"Unable to calculate a driving route for Leg {i + 1}: "
                    f"{from_zip} → {to_zip}. Please verify both ZIP codes."
                )
                return render(
                    request, "projects/multi_stop_splitter.html", context
                )

            legs.append({"from_zip": from_zip, "to_zip": to_zip, "miles": miles})

        context["results"] = freight_calculator_utils.calculate_multi_stop_route(
            legs=legs,
            stop_off_charge=d.get("stop_off_charge"),  # None → no stop-off fees
        )
        # Echo route_zips back for the results header / map display.
        context["route_zips"] = route_zips

    return render(request, "projects/multi_stop_splitter.html", context)


# ===========================================================================
# Freight Lane Rate-Per-Mile Analyzer
# ===========================================================================
# Breaks down a freight lane's total rate into its components and calculates
# rate-per-mile (RPM) metrics for benchmarking:
#   - Base line-haul RPM
#   - Fuel surcharge RPM (if provided)
#   - All-in RPM (line-haul + FSC)
#   - Operating margin RPM (if operating_cpm provided: RPM minus CPM)
#
# GOOGLE MAPS:
#   Uses get_road_distance() to convert the origin/dest ZIP pair to actual
#   driving miles.  If the route is unresolvable, an error is returned and
#   no rate analysis is performed.
#
# GET  → empty LaneRateAnalyzerForm.
# POST → geocodes route; calculates RPM breakdown; renders results.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def lane_rate_analyzer(request):
    from .. import freight_calculator_utils
    from ..forms import LaneRateAnalyzerForm
    from ..utils import get_road_distance

    form    = LaneRateAnalyzerForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        exact_miles = get_road_distance(d["origin_zip"], d["dest_zip"])

        if not exact_miles:
            context["error_message"] = (
                "Unable to calculate a valid driving route between "
                "these ZIP codes. Please verify both entries."
            )
            return render(request, "projects/lane_rate_analyzer.html", context)

        context["results"] = freight_calculator_utils.calculate_lane_rate(
            origin_zip=d["origin_zip"],
            dest_zip=d["dest_zip"],
            distance_miles=exact_miles,
            line_haul_rate=d["line_haul_rate"],
            fuel_surcharge=d.get("fuel_surcharge"),   # None → omit from all-in calc
            operating_cpm=d.get("operating_cpm"),     # None → omit margin calc
        )

    return render(request, "projects/lane_rate_analyzer.html", context)


# ===========================================================================
# Freight Margin / Gross Profit Calculator
# ===========================================================================
# Calculates the gross profit (GP) and margin percentage for a brokered or
# carrier freight transaction.  Accounts for:
#   - Customer rate (revenue) and carrier rate (cost)
#   - Separately billed fuel surcharges on each side
#   - Accessorial charges (lumper, TONU, layover, etc.) on each side
#
# GP = (customer_rate + customer_fsc + customer_accessorials)
#    - (carrier_rate  + carrier_fsc  + carrier_accessorials)
# Margin % = GP / total customer revenue
#
# OPTIONAL ROAD MILES:
#   If both origin_zip and dest_zip are provided, the util also calculates
#   GP-per-mile.  If the Maps API fails, an informational warning is added
#   to context but the margin calculation still proceeds without per-mile
#   metrics.  This is the one tool where a Maps API failure is non-fatal —
#   the margin itself doesn't depend on distance.
#
# GET  → empty FreightMarginForm.
# POST → optionally geocodes route; always calculates margin; warns if
#        distance lookup failed but does not block the result.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_margin_calculator(request):
    from .. import freight_calculator_utils
    from ..forms import FreightMarginForm
    from ..utils import get_road_distance

    form    = FreightMarginForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        # ── Step 1: Optionally get road miles for per-mile metrics ──────────
        distance_miles = None
        if d.get("origin_zip") and d.get("dest_zip"):
            distance_miles = get_road_distance(d["origin_zip"], d["dest_zip"])
            if not distance_miles:
                # Non-fatal: warn the user but don't block the margin calculation.
                context["error_message"] = (
                    "Unable to calculate a valid driving route between "
                    "these ZIP codes. Margin calculated without per-mile metrics."
                )

        # ── Step 2: Calculate margin (distance_miles may be None) ───────────
        context["results"] = freight_calculator_utils.calculate_freight_margin(
            customer_rate=d["customer_rate"],
            carrier_rate=d["carrier_rate"],
            customer_fsc=d.get("customer_fsc"),
            carrier_fsc=d.get("carrier_fsc"),
            customer_accessorials=d.get("customer_accessorials"),
            carrier_accessorials=d.get("carrier_accessorials"),
            distance_miles=distance_miles,       # None → skip per-mile metrics
            origin_zip=d.get("origin_zip", ""),
            dest_zip=d.get("dest_zip", ""),
        )

    return render(request, "projects/freight_margin_calculator.html", context)