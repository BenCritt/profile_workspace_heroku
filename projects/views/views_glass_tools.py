# views/views_glass_tools.py
#
# ============================================================================
# Glass Artist Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the Glass Artist Toolkit category.
# All computation is delegated to glass_utils.py; these views are intentionally
# thin — they handle HTTP mechanics (form binding, GET/POST branching, context
# assembly, template rendering) and nothing else.
#
# Tools in this module:
#   glass_artist_toolkit       — Hub/landing page for the whole category
#   glass_volume_calculator    — Volume & weight for standard glass blank shapes
#   kiln_schedule_generator    — Step-by-step firing schedule by brand/project
#   stained_glass_cost_estimator — Commission cost estimation (labor + materials)
#   kiln_controller_utils      — Temperature converter + ramp-rate calculator
#   stained_glass_materials    — Lead came / copper foil / solder material estimator
#   lampwork_materials         — Rod/tube glass weight for torchwork beads
#   glass_reaction_checker     — Known silver/sulfur reaction lookup by glass code
#   frit_mixing_calculator     — Powdered frit-to-medium ratio for painting
#   circle_cutter_calculator   — Compass-cutter pivot offset for circles & ovals
#
# ============================================================================
# DECORATOR CONVENTIONS (applied to every view in this file)
# ============================================================================
#
# @trim_memory_after
#   Custom decorator (see projects/decorators.py).  After the view returns,
#   it calls gc.collect() and malloc_trim(0) to release Python/libc memory
#   back to the OS.  This matters on Heroku's single-dyno setup where the
#   process is long-lived and memory accumulates between requests.
#
# @ensure_csrf_cookie   (hub views only)
#   Forces Django to set the CSRF cookie on GET requests even though the hub
#   pages themselves have no form.  This primes the cookie so that any JS
#   fetch() or XHR call made from the hub page can include the CSRF token
#   without an extra round-trip.  Only needed on pages that make JS-driven
#   POST requests to sub-tool endpoints.
#
# @cache_control(no_cache=True, must_revalidate=True, no_store=True)
#   Prevents browsers and Cloudflare from caching tool-result pages.
#   Without this, a user could hit Back and see stale results from a prior
#   form submission, which could be confusing for result-bearing pages.
#
# IMPORT PATTERN — WHY LAZY?
#   heavy utility modules (glass_utils, forms, etc.) are imported *inside*
#   each view function rather than at module scope.  Rationale:
#     1. Gunicorn/Heroku forks worker processes at startup.  Deferring heavy
#        imports until request time means the parent process stays lean.
#     2. Glass tools are not always hit on every request; lazy imports avoid
#        paying the import cost for unused tools.
#     3. It mirrors the pattern established in the original monolithic views.py
#        and keeps the refactored modules behaviorally identical.
# ============================================================================

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after


# ===========================================================================
# Glass Artist Toolkit Hub
# ===========================================================================
# The hub page is a static landing page — it renders a card grid linking to
# every tool in the category.  It carries no form logic.
#
# @ensure_csrf_cookie is applied here (not on the individual tool views)
# because in-page navigation from the hub uses JS to initiate form POSTs.
# The cookie must already be set before those requests fire.
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_artist_toolkit(request):
    return render(request, "projects/glass_artist_toolkit.html")


# ===========================================================================
# Glass Volume & Weight Calculator
# ===========================================================================
# Calculates the volume (cubic inches) and estimated weight (lbs) of a glass
# blank given its shape (rectangle, circle, cylinder, etc.), glass type
# (soda-lime, borosilicate, lead crystal), and an optional waste factor.
#
# GET  → renders an empty GlassVolumeForm.
# POST → validates the form, calls glass_utils.calculate_glass_volume_weight(),
#        and injects the result dict into context as "results" for the template.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_volume_calculator(request):
    from .. import glass_utils
    from ..forms import GlassVolumeForm

    form    = GlassVolumeForm(request.POST or None)  # binds on POST, unbound on GET
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        # Pass all cleaned fields, let the util decide which shape fields to use.
        context["results"] = glass_utils.calculate_glass_volume_weight(
            shape=form.cleaned_data["shape"],
            glass_type=form.cleaned_data["glass_type"],
            waste_factor=form.cleaned_data["waste_factor"],
            data=form.cleaned_data,  # full dict; util extracts shape-specific dims
        )

    return render(request, "projects/glass_volume_calculator.html", context)


# ===========================================================================
# Kiln Firing Schedule Generator
# ===========================================================================
# Produces a step-by-step kiln firing schedule (ramp rate, target temp, hold
# duration for each segment) based on the glass brand, project type (fuse,
# slump, cast, anneal, etc.), and pack thickness in inches.
#
# GET  → empty form.
# POST → calls glass_utils.generate_kiln_schedule(), which returns a dict with:
#          "schedule" — list of segment dicts (step, ramp, target, hold, notes)
#          "total_time" — total estimated cycle time in minutes
#        Both are merged into context.  A human-readable "project_name" string
#        is also assembled here for display in the template header.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_schedule_generator(request):
    from .. import glass_utils
    from ..forms import KilnScheduleForm

    form    = KilnScheduleForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        data   = form.cleaned_data
        result = glass_utils.generate_kiln_schedule(
            brand=data["brand"],
            project=data["project_type"],
            thickness=data["thickness"],
        )
        # result is {"schedule": [...], "total_time": N} — merge into context
        # so the template can reference {{ schedule }} and {{ total_time }} directly.
        context.update(result)

        # Build a descriptive label for the schedule heading, e.g.
        # "Bullseye - Full Fuse (6mm)"
        context["project_name"] = (
            f"{data['brand'].title()} - "
            f"{data['project_type'].replace('_', ' ').title()}"
        )

    return render(request, "projects/kiln_schedule_generator.html", context)


# ===========================================================================
# Stained Glass Cost Estimator
# ===========================================================================
# Estimates the total cost of a stained glass commission including:
#   - Glass material cost (panel area × price/sqft × waste factor)
#   - Labor cost (estimated hours × hourly rate)
#   - Optional markup percentage for retail pricing
#
# GET  → empty form.
# POST → calls glass_utils.estimate_stained_glass_cost() with panel dimensions,
#        piece count, glass price/sqft, labor rate, estimated hours, and markup.
#        Returns a results dict that the template iterates for line-item display.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_cost_estimator(request):
    from .. import glass_utils
    from ..forms import StainedGlassCostForm

    form    = StainedGlassCostForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data  # short alias avoids repetitive form.cleaned_data["x"]
        context["results"] = glass_utils.estimate_stained_glass_cost(
            w=d["width"], h=d["height"], pieces=d["pieces"],
            glass_price=d["glass_price"], rate=d["labor_rate"],
            user_hours=d["estimated_hours"], markup=d["markup"],
        )

    return render(request, "projects/stained_glass_cost_estimator.html", context)


# ===========================================================================
# Kiln Controller Utilities
# ===========================================================================
# A two-in-one utility page with two independent sub-forms on the same template:
#
#   TOOL 1 — Temperature Converter
#     Converts between °F, °C, and °K.
#     Uses a hidden <input name="action" value="convert"> field to identify
#     which sub-form was submitted.
#
#   TOOL 2 — Ramp Rate Calculator
#     Given a start temp, target temp, and ramp rate (°F or °C per hour),
#     calculates time-to-target and segment duration.
#     Uses a hidden <input name="action" value="ramp"> field.
#
# Because both forms live on the same page, each POST must check `action`
# to determine which sub-form to validate and which utility function to call.
# The other form is left in its initial unbound state so it doesn't show
# spurious validation errors.
#
# GET  → both forms rendered in their initial (unbound) state.
# POST → only the submitted sub-form is validated; the result dict is placed
#        in context under "convert_result" or "ramp_result" respectively.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_controller_utils(request):
    from .. import glass_utils
    from ..forms import TempConverterForm, RampCalculatorForm

    # Start with both forms in their unbound initial state.
    convert_form = TempConverterForm(initial={"action": "convert"})
    ramp_form    = RampCalculatorForm(initial={"action": "ramp"})
    context      = {"convert_form": convert_form, "ramp_form": ramp_form}

    if request.method == "POST":
        # Inspect the hidden "action" field to route to the correct sub-form.
        action = request.POST.get("action")

        if action == "convert":
            convert_form = TempConverterForm(request.POST)
            if convert_form.is_valid():
                res = glass_utils.convert_temperature(
                    convert_form.cleaned_data["temperature"],
                    convert_form.cleaned_data["from_unit"],
                )
                # Build a human-readable input/output pair for the template.
                # res["orig"] is the original unit symbol; res["unit"] is the result unit.
                context["convert_result"] = {
                    "input":  f"{convert_form.cleaned_data['temperature']}{res['orig']}",
                    "output": f"{round(res['val'], 1)}{res['unit']}",
                }
                context["convert_form"] = convert_form  # rebind with submitted data

        elif action == "ramp":
            ramp_form = RampCalculatorForm(request.POST)
            if ramp_form.is_valid():
                res = glass_utils.calculate_ramp_details(
                    ramp_form.cleaned_data["start_temp"],
                    ramp_form.cleaned_data["target_temp"],
                    ramp_form.cleaned_data["rate"],
                )
                if res:
                    context["ramp_result"] = res
                else:
                    # The util returns None when rate == 0 (division by zero guard).
                    ramp_form.add_error("rate", "Rate must be greater than 0.")
                context["ramp_form"] = ramp_form  # rebind with submitted data

    return render(request, "projects/kiln_controller_utils.html", context)


# ===========================================================================
# Stained Glass Materials Calculator
# ===========================================================================
# Estimates the raw materials needed for a stained glass panel:
#   - Lead came (feet, by profile: H-came border, round/flat interior)
#   - Copper foil (linear inches, based on piece count)
#   - Solder (oz, based on came/foil length)
#
# The "method" field selects between leaded (traditional came) and Tiffany
# (copper foil) construction techniques, which drives different material
# formulae in glass_utils.
#
# GET  → empty form.
# POST → validates; calls glass_utils.estimate_stained_glass_materials().
#        "method_display" injects the human-readable method name (from the
#        form's choices dict) into context for the results heading.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_materials(request):
    from .. import glass_utils
    from ..forms import StainedGlassMaterialsForm

    form    = StainedGlassMaterialsForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = glass_utils.estimate_stained_glass_materials(
            w=d["width"], h=d["height"], pieces=d["pieces"],
            method=d["method"], waste_factor=d["waste_factor"],
        )
        # Translate the internal choice key (e.g. "lead") to a display label
        # (e.g. "Traditional Lead Came") for the results section header.
        context["method_display"] = (
            dict(form.fields["method"].choices)[d["method"]]
        )

    return render(request, "projects/stained_glass_materials.html", context)


# ===========================================================================
# Lampwork Material Calculator
# ===========================================================================
# Estimates glass rod/tube consumption for flameworked beads and vessels.
# Inputs include glass system (soda-lime, borosilicate, etc.), bead shape
# (solid rod wrap, hollow tube, disc, etc.), diameter, length, and quantity.
#
# GET  → empty form.
# POST → calls glass_utils.calculate_lampwork_weight().
#        The result dict is augmented with human-readable display labels
#        (glass_name, shape_name) looked up from the form's choices dicts
#        so the template doesn't need to do that lookup itself.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def lampwork_materials(request):
    from .. import glass_utils
    from ..forms import LampworkMaterialForm

    form    = LampworkMaterialForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d       = form.cleaned_data
        results = glass_utils.calculate_lampwork_weight(
            glass_type=d["glass_type"],   shape=d["form_factor"],
            dia_mm=d["diameter_mm"],      length_in=d["length_inches"],
            qty=d["quantity"],            wall_mm=d.get("wall_mm", 0),
        )
        # Translate internal choice keys to human-readable display labels.
        results["glass_name"] = dict(form.fields["glass_type"].choices)[d["glass_type"]]
        results["shape_name"] = dict(form.fields["form_factor"].choices)[d["form_factor"]]
        context["results"]    = results

    return render(request, "projects/lampwork_materials.html", context)


# ===========================================================================
# Glass Reaction Checker
# ===========================================================================
# Looks up known chemical reactions between two glass color codes when fired
# together.  The classic example is Bullseye's Silver Yellow (001120) reacting
# with copper-bearing blues to produce dramatic color shifts at kiln temperature.
#
# The data backing this tool lives in glass_utils as a reaction lookup table.
# This view is intentionally simple — form in, results out.
#
# GET  → empty two-field form (glass_a, glass_b).
# POST → calls glass_utils.check_glass_reaction(a, b); result includes reaction
#        severity, description, and recommended isolation technique.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_reaction_checker(request):
    from .. import glass_utils
    from ..forms import GlassReactionForm

    form    = GlassReactionForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        context["results"] = glass_utils.check_glass_reaction(
            form.cleaned_data["glass_a"],
            form.cleaned_data["glass_b"],
        )

    return render(request, "projects/glass_reaction_checker.html", context)


# ===========================================================================
# Enamel / Frit Mixing Calculator
# ===========================================================================
# Calculates the correct ratio of powdered frit (or enamel) to liquid painting
# medium (water, oil, squeegee oil, etc.) based on the intended application
# style (brushwork, screen printing, airbrushing, sifting).
#
# Different application styles require very different viscosities; the ratios
# are documented per-style in glass_utils.calculate_frit_medium_ratio().
#
# GET  → empty form (powder weight + application style).
# POST → returns ratio, final volume estimate, and mixing notes.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def frit_mixing_calculator(request):
    from .. import glass_utils
    from ..forms import FritMixingForm

    form    = FritMixingForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = glass_utils.calculate_frit_medium_ratio(
            powder_weight=d["powder_weight"],
            application_style=d["application_style"],
        )

    return render(request, "projects/frit_mixing_calculator.html", context)


# ===========================================================================
# Circle / Oval Cutter Calculator
# ===========================================================================
# Calculates the pivot pin offset needed on a compass-style circle cutter
# (e.g. Toyo, Silberschnitt) to score a circle or oval of the specified
# finished size, accounting for:
#   - The cutter wheel's offset from the pivot center ("cutter_offset")
#   - A grind allowance subtracted from the target dimension before scribing,
#     so the piece finishes to exact size after edge grinding.
#
# Shape choices map to descriptive labels (e.g. "circle" → "Circle (equal axes)")
# via the form's choices dict.  The label is passed to the util for display
# in the results breakdown.
#
# GET  → empty form.
# POST → calls glass_utils.calculate_circle_cutter_settings(); result includes
#        pivot setting in inches, diameter to scribe, and grind amount.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def circle_cutter_calculator(request):
    from .. import glass_utils
    from ..forms import CircleCutterForm

    form    = CircleCutterForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data

        # Translate the internal choice key to the display label string that
        # glass_utils expects for its per-shape logic branching.
        shape_map  = dict(form.fields["shape_type"].choices)
        shape_name = shape_map[d["shape_type"]]

        context["results"] = glass_utils.calculate_circle_cutter_settings(
            target_dim=d["target_diameter"],
            shape=shape_name,
            cutter_offset=d["cutter_offset"],
            grind_allowance=float(d["grind_allowance"]),
        )

    return render(request, "projects/circle_cutter_calculator.html", context)