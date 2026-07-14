# forms/forms_pm_tools.py
#
# Project Management Toolkit form classes.
#
# Forms and their consuming views:
#   EVMCalculatorForm  → views_pm_tools.evm_calculator
#   PERTCalculatorForm → views_pm_tools.pert_calculator
#   CriticalPathCalculatorForm → views_pm_tools.critical_path_calculator

from django import forms
import re
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
)


# --- Earned Value Management (EVM) Calculator ---
class EVMCalculatorForm(forms.Form):
    """
    Accepts the four core EVM inputs (BAC, PV, AC, and EV — with percent
    complete as an alternative way to supply EV) plus an optional
    management EAC target for TCPI-to-target analysis.

    Fieldset 1 — Project Budget (required):        bac
    Fieldset 2 — Status Date Values (required):    pv, ac
    Fieldset 3 — Earned Value (enter exactly one): ev OR percent_complete
    Fieldset 4 — Additional Analysis (optional):   target_eac
    """

    # --- Project Budget ---
    bac = forms.FloatField(
        label="Budget at Completion — BAC ($)",
        help_text="Total authorized budget for the project.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "250000",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "0.01",
            "min": "0.01",           # Prevents zero/negative budgets
        }),
        validators=[MinValueValidator(0.01, message="BAC must be at least $0.01.")],
    )

    # --- Status Date Values ---
    pv = forms.FloatField(
        label="Planned Value — PV ($)",
        help_text="Budgeted cost of the work scheduled through the status date.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "125000",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="PV must be at least $0.01.")],
    )
    ac = forms.FloatField(
        label="Actual Cost — AC ($)",
        help_text="Actual cost incurred through the status date.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "130000",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="AC must be at least $0.01.")],
    )

    # --- Earned Value (enter EV directly OR percent complete) ---
    ev = forms.FloatField(
        label="Earned Value — EV ($)",
        required=False,
        help_text="Budgeted cost of the work actually performed. Leave blank if entering % complete below.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "110000",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",              # 0 is legal: started, nothing earned yet
        }),
        validators=[MinValueValidator(0, message="EV cannot be negative.")],
    )
    percent_complete = forms.FloatField(
        label="Percent Complete (%)",
        required=False,
        help_text="Alternative to EV: physical % of total scope completed. EV = % × BAC.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "44",
            "inputmode": "decimal",
            "step": "0.1",
            "min": "0",
            "max": "100",
        }),
        validators=[
            MinValueValidator(0, message="Percent complete cannot be negative."),
            # NOTE: literal % must be escaped as %% — Django runs validator
            # messages through %-interpolation with the limit_value param.
            MaxValueValidator(100, message="Percent complete cannot exceed 100%%."),
        ],
    )

    # --- Optional: Management EAC Target ---
    target_eac = forms.FloatField(
        label="Management EAC Target ($)",
        required=False,
        help_text="(Optional) Your own Estimate at Completion. Shows the TCPI needed to hit it.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "300000",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="EAC target must be at least $0.01.")],
    )

    # --- Cross-Field Validation ---
    def clean(self):
        """
        Enforces the relationships between EVM inputs:
          1. Exactly one of EV / percent complete must be provided.
          2. PV cannot exceed BAC (cumulative planned value caps at BAC).
          3. EV cannot exceed BAC (you can't earn more than the budget).
          4. A management EAC target must exceed AC (money already spent).

        NOTE: comparisons use `is not None`, never truthiness — 0.0 is a
        legitimate value for both ev and percent_complete.
        """
        cleaned_data = super().clean()

        bac = cleaned_data.get("bac")
        pv = cleaned_data.get("pv")
        ac = cleaned_data.get("ac")
        ev = cleaned_data.get("ev")
        percent_complete = cleaned_data.get("percent_complete")
        target_eac = cleaned_data.get("target_eac")

        # 1. Exactly one path to Earned Value.
        if ev is None and percent_complete is None:
            raise forms.ValidationError(
                "Enter either Earned Value (EV) or Percent Complete."
            )
        if ev is not None and percent_complete is not None:
            raise forms.ValidationError(
                "Enter EV or Percent Complete — not both."
            )

        # 2–3. Values that are definitionally capped at BAC.
        #      (Guard bac for None: field-level validation may have failed.)
        if bac is not None:
            if pv is not None and pv > bac:
                self.add_error(
                    "pv",
                    "Planned Value (PV) cannot exceed the Budget at Completion (BAC).",
                )
            if ev is not None and ev > bac:
                self.add_error(
                    "ev",
                    "Earned Value (EV) cannot exceed the Budget at Completion (BAC).",
                )

        # 4. A target EAC below money already spent is unreachable.
        if target_eac is not None and ac is not None and target_eac <= ac:
            self.add_error(
                "target_eac",
                "Your EAC target must be greater than Actual Cost to date.",
            )

        return cleaned_data


# --- PERT / Three-Point Estimation Calculator ---
class PERTCalculatorForm(forms.Form):
    """
    Accepts the three point estimates (optimistic, most likely,
    pessimistic) plus an optional target value for Z-score / probability
    analysis.

    Fieldset 1 — Three-Point Estimates (required): optimistic,
                 most_likely, pessimistic
    Fieldset 2 — Additional Analysis (optional):   target_value

    All values are unit-agnostic (days, hours, or dollars) as long as
    every field uses the same unit.
    """

    # --- Three-Point Estimates ---
    optimistic = forms.FloatField(
        label="Optimistic Estimate (O)",
        help_text="Best-case value, in any consistent unit — days, hours, or dollars.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "8",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "0.01",
            "min": "0",              # Prevents negative estimates
        }),
        validators=[MinValueValidator(0, message="Optimistic estimate cannot be negative.")],
    )
    most_likely = forms.FloatField(
        label="Most Likely Estimate (M)",
        help_text="The value you'd expect under normal conditions.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "11",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0, message="Most likely estimate cannot be negative.")],
    )
    pessimistic = forms.FloatField(
        label="Pessimistic Estimate (P)",
        help_text="Worst-case value, assuming things go wrong but the work still completes.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "20",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0, message="Pessimistic estimate cannot be negative.")],
    )

    # --- Optional: Target Probability ---
    target_value = forms.FloatField(
        label="Target Value",
        required=False,
        help_text="(Optional) A deadline or budget in the same unit. Shows the probability of coming in at or under it.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "15",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0, message="Target value cannot be negative.")],
    )

    # --- Cross-Field Validation ---
    def clean(self):
        """
        Enforces the three-point ordering O <= M <= P.  Equal values are
        allowed (O == M == P is a legitimate deterministic estimate, and
        the util handles the zero-spread case explicitly).

        NOTE: comparisons guard for None — field-level validation may
        have already failed for any of the three inputs.
        """
        cleaned_data = super().clean()

        optimistic = cleaned_data.get("optimistic")
        most_likely = cleaned_data.get("most_likely")
        pessimistic = cleaned_data.get("pessimistic")

        if optimistic is not None and most_likely is not None and most_likely < optimistic:
            self.add_error(
                "most_likely",
                "Most likely estimate cannot be less than the optimistic estimate.",
            )

        if most_likely is not None and pessimistic is not None and pessimistic < most_likely:
            self.add_error(
                "pessimistic",
                "Pessimistic estimate cannot be less than the most likely estimate.",
            )

        return cleaned_data


# --- Critical Path Method (CPM) Calculator ---
class CriticalPathCalculatorForm(forms.Form):
    """
    Accepts an activity network as free text — one activity per line:

        ID, duration, predecessor(s)

    e.g.  A, 3
          B, 5, A
          F, 4, D, E

    Everything after the duration is treated as predecessor IDs (commas,
    semicolons, or spaces all work as separators).  IDs are matched
    case-insensitively; the casing from each activity's own definition
    line is used for display.

    clean_activities() parses and validates the text, then returns the
    PARSED STRUCTURE as the field's cleaned value — a list of
    {"id", "duration", "predecessors"} dicts in input order — following
    the same convention MultiStopSplitterForm uses to assemble
    route_zips in cleaned_data for its view.  Circular-dependency
    detection is the one check left to pm_calculator_utils (it requires
    running the scheduling algorithm itself).
    """

    # Hard caps — keep parsing, the passes, and the results table sane.
    MAX_ACTIVITIES = 100
    MAX_ID_LENGTH = 30
    MAX_DURATION = 1_000_000_000
    MAX_ERRORS_SHOWN = 10

    activities = forms.CharField(
        label="Activity List",
        max_length=10000,
        help_text=(
            "One activity per line: ID, duration, then any predecessors — "
            "all separated by commas. IDs are case-insensitive."
        ),
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": "8",
            "placeholder": "A, 3\nB, 5, A\nC, 4, A\nD, 6, B\nE, 2, C\nF, 4, D, E",
            "spellcheck": "false",
            "autocapitalize": "off",
            "autocomplete": "off",
        }),
    )

    def clean_activities(self):
        """
        Parses the textarea into a validated activity list.

        Checks performed here (all reported with line numbers, up to
        MAX_ERRORS_SHOWN at once):
          - each line has at least "ID, duration"
          - duration is a non-negative number within bounds
          - IDs are unique (case-insensitively) and within length bounds
          - no activity depends on itself
          - every predecessor reference resolves to a defined activity
          - at least one activity, at most MAX_ACTIVITIES

        Returns:
            list[dict]: [{"id", "duration", "predecessors"}, ...] in
            input order, with predecessor refs rewritten to the
            canonical (as-defined) ID casing.
        """
        raw = self.cleaned_data["activities"]
        errors = []
        parsed = []            # [{"id", "duration", "predecessors", "_line"}]
        canonical_by_fold = {} # casefolded ID → canonical ID

        # --- Pass 1: line-by-line parse ---
        for line_no, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue  # blank lines are fine

            parts = [p.strip() for p in line.split(",")]

            if len(parts) < 2 or not parts[0] or not parts[1]:
                errors.append(
                    f"Line {line_no}: each activity needs at least an ID and "
                    "a duration, separated by a comma."
                )
                continue

            act_id = parts[0]
            if len(act_id) > self.MAX_ID_LENGTH:
                errors.append(
                    f"Line {line_no}: activity ID '{act_id[:self.MAX_ID_LENGTH]}…' "
                    f"is longer than {self.MAX_ID_LENGTH} characters."
                )
                continue

            try:
                duration = float(parts[1])
            except ValueError:
                errors.append(
                    f"Line {line_no} ('{act_id}'): duration '{parts[1]}' "
                    "is not a number."
                )
                continue
            if duration < 0:
                errors.append(
                    f"Line {line_no} ('{act_id}'): duration cannot be negative."
                )
                continue
            if duration > self.MAX_DURATION:
                errors.append(
                    f"Line {line_no} ('{act_id}'): duration is unrealistically large."
                )
                continue

            fold = act_id.casefold()
            if fold in canonical_by_fold:
                errors.append(
                    f"Line {line_no}: duplicate activity ID '{act_id}' "
                    f"(already defined as '{canonical_by_fold[fold]}')."
                )
                continue
            canonical_by_fold[fold] = act_id

            # Everything after the duration is predecessors; be forgiving
            # about separators (commas already split; also allow ; and
            # whitespace inside a token), and drop duplicate references.
            predecessors = []
            for token in parts[2:]:
                for ref in re.split(r"[;\s]+", token):
                    if ref and ref not in predecessors:
                        predecessors.append(ref)

            parsed.append({
                "id": act_id,
                "duration": duration,
                "predecessors": predecessors,
                "_line": line_no,
            })

        # --- Whole-list checks ---
        if not parsed and not errors:
            errors.append("Enter at least one activity.")
        if len(parsed) > self.MAX_ACTIVITIES:
            errors.append(
                f"Too many activities ({len(parsed)}). The maximum is "
                f"{self.MAX_ACTIVITIES}."
            )

        # --- Pass 2: resolve predecessor references (case-insensitive) ---
        if not errors:
            for act in parsed:
                resolved = []
                for ref in act["predecessors"]:
                    canonical = canonical_by_fold.get(ref.casefold())
                    if canonical is None:
                        errors.append(
                            f"Line {act['_line']} ('{act['id']}'): unknown "
                            f"predecessor '{ref}'. Every predecessor must be "
                            "defined as an activity."
                        )
                    elif canonical == act["id"]:
                        errors.append(
                            f"Line {act['_line']} ('{act['id']}'): an activity "
                            "cannot depend on itself."
                        )
                    elif canonical not in resolved:
                        resolved.append(canonical)
                act["predecessors"] = resolved

        if errors:
            shown = errors[:self.MAX_ERRORS_SHOWN]
            hidden = len(errors) - len(shown)
            if hidden > 0:
                shown.append(f"…and {hidden} more issue{'s' if hidden != 1 else ''}.")
            raise forms.ValidationError(shown)

        # Strip the parser-internal line tracker before handing to the view.
        for act in parsed:
            del act["_line"]

        return parsed