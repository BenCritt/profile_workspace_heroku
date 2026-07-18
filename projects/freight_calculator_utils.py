import requests
import os
from datetime import timedelta

# ==============================================================================
# FMCSA CARRIER SAFETY API UTILITIES
# ==============================================================================

"""
Freight Carrier Safety Reporter API Documentation
https://mobile.fmcsa.dot.gov/QCDevsite/docs/qcApi
"""

def replace_none_with_na(data):
    """Recursively replaces None values in a dict/list with 'N/A'."""
    if isinstance(data, dict):
        return {key: replace_none_with_na(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [replace_none_with_na(item) for item in data]
    elif data is None:
        return "N/A"
    else:
        return data


def get_fmcsa_carrier_data_by_usdot(usdot_number):
    """
    Fetches carrier safety data from the FMCSA QCMobile API using a USDOT number.
    Returns a cleaned dictionary of carrier information or None if not found/error.
    """
    fcsr_webkey = os.environ.get("FMCSA_KEY")
    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/{usdot_number}?webKey={fcsr_webkey}"

    try:
        response = requests.get(url, timeout=10)
        # Raise an exception for bad status codes.
        response.raise_for_status()

        response_data = response.json()

        # Ensure 'content' exists and contains 'carrier'.
        content_data = response_data.get("content")
        if not content_data:
            return None  # 'content' missing, return None.

        carrier_data = content_data.get("carrier")
        if not carrier_data:
            return None  # 'carrier' missing, return None.

        # Apply the helper function to replace None values with "N/A."
        cleaned_carrier_data = replace_none_with_na(carrier_data)

        # Parse and clean relevant fields from the cleaned JSON data.
        carrier_info = {
            "name": cleaned_carrier_data.get("legalName", "N/A"),
            "dotNumber": cleaned_carrier_data.get("dotNumber", "N/A"),
            "mcNumber": cleaned_carrier_data.get("mcNumber", "N/A"),
            "allowedToOperate": cleaned_carrier_data.get("allowedToOperate", "N/A"),
            "bipdInsuranceOnFile": cleaned_carrier_data.get("bipdInsuranceOnFile", "N/A"),
            "bipdInsuranceRequired": cleaned_carrier_data.get("bipdInsuranceRequired", "N/A"),
            "bondInsuranceOnFile": cleaned_carrier_data.get("bondInsuranceOnFile", "N/A"),
            "brokerAuthorityStatus": cleaned_carrier_data.get("brokerAuthorityStatus", "N/A"),
            "cargoInsuranceOnFile": cleaned_carrier_data.get("cargoInsuranceOnFile", "N/A"),
            "carrierOperationCode": (
                cleaned_carrier_data.get("carrierOperation", {}).get("carrierOperationCode", "N/A")
                if isinstance(cleaned_carrier_data.get("carrierOperation"), dict)
                else "N/A"
            ),
            "carrierOperationDesc": (
                cleaned_carrier_data.get("carrierOperation", {}).get("carrierOperationDesc", "N/A")
                if isinstance(cleaned_carrier_data.get("carrierOperation"), dict)
                else "N/A"
            ),
            "commonAuthorityStatus": cleaned_carrier_data.get("commonAuthorityStatus", "N/A"),
            "contractAuthorityStatus": cleaned_carrier_data.get("contractAuthorityStatus", "N/A"),
            "crashTotal": cleaned_carrier_data.get("crashTotal", "N/A"),
            "driverInsp": cleaned_carrier_data.get("driverInsp", "N/A"),
            "driverOosInsp": cleaned_carrier_data.get("driverOosInsp", "N/A"),
            "driverOosRate": cleaned_carrier_data.get("driverOosRate", "N/A"),
            "ein": cleaned_carrier_data.get("ein", "N/A"),
            "fatalCrash": cleaned_carrier_data.get("fatalCrash", "N/A"),
            "hazmatInsp": cleaned_carrier_data.get("hazmatInsp", "N/A"),
            "hazmatOosInsp": cleaned_carrier_data.get("hazmatOosInsp", "N/A"),
            "hazmatOosRate": cleaned_carrier_data.get("hazmatOosRate", "N/A"),
            "injCrash": cleaned_carrier_data.get("injCrash", "N/A"),
            "phyCity": cleaned_carrier_data.get("phyCity", "N/A"),
            "phyState": cleaned_carrier_data.get("phyState", "N/A"),
            "phyStreet": cleaned_carrier_data.get("phyStreet", "N/A"),
            "phyZipcode": cleaned_carrier_data.get("phyZipcode", "N/A"),
            "reviewDate": cleaned_carrier_data.get("reviewDate", "N/A"),
            "safetyRating": cleaned_carrier_data.get("safetyRating", "N/A"),
            "safetyRatingDate": cleaned_carrier_data.get("safetyRatingDate", "N/A"),
            "totalDrivers": cleaned_carrier_data.get("totalDrivers", "N/A"),
            "totalPowerUnits": cleaned_carrier_data.get("totalPowerUnits", "N/A"),
            "towawayCrash": cleaned_carrier_data.get("towawayCrash", "N/A"),
            "vehicleInsp": cleaned_carrier_data.get("vehicleInsp", "N/A"),
            "vehicleOosInsp": cleaned_carrier_data.get("vehicleOosInsp", "N/A"),
            "vehicleOosRate": cleaned_carrier_data.get("vehicleOosRate", "N/A"),
        }

        return carrier_info

    except requests.exceptions.RequestException as e:
        print(f"There was an error fetching data for USDOT {usdot_number}: {e}")
        return None

# ==============================================================================
# FREIGHT RATE & LOGISTICS CALCULATORS
# ==============================================================================

def calculate_freight_class(length, width, height, weight_per_unit, quantity):
    """
    Calculates total weight, total volume (cubic feet), density (PCF), 
    and estimates the NMFC Freight Class based on the standard density scale.
    """
    # 1. Calculate Totals
    # Volume of one unit in cubic feet (1728 cubic inches = 1 cubic foot)
    vol_cubic_inches = length * width * height
    vol_cubic_feet = vol_cubic_inches / 1728.0
    
    total_cubic_feet = vol_cubic_feet * quantity
    total_weight = weight_per_unit * quantity
    
    # 2. Calculate Density (PCF: Pounds per Cubic Foot)
    density = (total_weight / total_cubic_feet) if total_cubic_feet > 0 else 0

    # 3. Determine Estimated Freight Class (Standard NMFC Density Scale)
    if density < 1: est_class = 400
    elif density < 2: est_class = 300
    elif density < 4: est_class = 250
    elif density < 6: est_class = 150
    elif density < 8: est_class = 125
    elif density < 10: est_class = 100
    elif density < 12: est_class = 92.5
    elif density < 15: est_class = 85
    elif density < 22.5: est_class = 70
    elif density < 30: est_class = 65
    elif density < 35: est_class = 60
    elif density < 50: est_class = 55
    else: est_class = 50

    return {
        "density": round(density, 2),
        "estimated_class": est_class,
        "total_weight": round(total_weight, 2),
        "total_cubic_feet": round(total_cubic_feet, 2),
        "qty": quantity
    }


def calculate_fuel_surcharge(miles, current_price, base_price, mpg):
    """
    Calculates the Fuel Surcharge (FSC) per mile and total for the trip.
    """
    price_diff = current_price - base_price
    
    # Formula: (Current - Base) / MPG
    fsc_per_mile = (price_diff / mpg) if mpg > 0 else 0.0
    total_fsc = fsc_per_mile * miles

    return {
        "fsc_per_mile": round(fsc_per_mile, 3), # Standard 3 decimal places for rate/mile
        "total_fsc": round(total_fsc, 2),
        "price_diff": round(price_diff, 2),
        "is_negative": price_diff < 0 # Indicates a credit rather than a surcharge
    }


def generate_hos_itinerary(miles_remaining, speed, start_datetime):
    """
    Simulates a truck trip to generate an itinerary compliant with 
    FMCSA Hours of Service (11-hr drive limit, 10-hr reset, 8-hr/30-min break).
    """
    current_time = start_datetime
    itinerary = []
    
    # HOS Counters
    shift_drive_time = 0.0
    continuous_drive_time = 0.0
    
    iterations = 0
    max_iterations = 50 # Safety catch

    while miles_remaining > 0 and iterations < max_iterations:
        iterations += 1
        
        # 1. Determine constraints for this leg
        time_left_in_shift = 11.0 - shift_drive_time
        time_left_continuous = 8.0 - continuous_drive_time
        time_to_finish = miles_remaining / speed

        # Leg duration is the smallest of these constraints
        leg_duration = min(time_to_finish, time_left_in_shift, time_left_continuous)
        
        # Avoid tiny floating point fragments
        if leg_duration < 0.01:
            leg_duration = 0

        # 2. "Drive" this leg
        dist_covered = leg_duration * speed
        start_leg_time = current_time
        current_time += timedelta(hours=leg_duration)
        
        miles_remaining -= dist_covered
        shift_drive_time += leg_duration
        continuous_drive_time += leg_duration

        if leg_duration > 0:
            itinerary.append({
                "event": "Drive",
                "start": start_leg_time,
                "end": current_time,
                "duration": f"{int(leg_duration)}h {int((leg_duration*60)%60)}m",
                "note": f"Covered {round(dist_covered, 1)} miles"
            })

        # 3. Check Logic for Breaks/Resets
        # A) Trip Finished?
        if miles_remaining <= 0.1:
            itinerary.append({
                "event": "Arrived", "start": current_time, "end": "", "duration": "",
                "note": "Destination Reached", "is_highlight": True
            })
            break

        # B) 11-Hour Limit Hit? -> 10 Hour Reset
        if shift_drive_time >= 11.0:
            start_break = current_time
            current_time += timedelta(hours=10)
            itinerary.append({
                "event": "10-Hour Reset", "start": start_break, "end": current_time,
                "duration": "10h 00m", "note": "Mandatory Daily Reset (11hr limit reached)",
                "is_break": True
            })
            shift_drive_time = 0
            continuous_drive_time = 0
            continue # Skip 30-min break check if resetting

        # C) 8-Hour Limit Hit? -> 30 Minute Break
        if continuous_drive_time >= 8.0:
            start_break = current_time
            current_time += timedelta(minutes=30)
            itinerary.append({
                "event": "30-Min Break", "start": start_break, "end": current_time,
                "duration": "0h 30m", "note": "Mandatory FMCSA Break (8hr continuous limit)",
                "is_break": True
            })
            continuous_drive_time = 0

    return {
        "itinerary": itinerary,
        "arrival_time": current_time
    }

def _fmt_hos_duration(hours):
    """
    Formats a decimal hour value as 'Xh YYm' (e.g. 2.5 → '2h 30m').
    Guards against float rounding pushing minutes to 60.
    """
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:  # e.g. 1.9999 hours rounding up
        h += 1
        m = 0
    return f"{h}h {m:02d}m"

def _fmt_miles(miles):
    """
    Formats a mileage value for display.  Whole-number distances render
    without a decimal ("186", "2,502"); clock-limited drive chunks that
    genuinely land on a fraction keep one decimal ("247.5").  Prevents
    "186.0 of 2502.0" float noise from Google Maps leg values.
    """
    rounded = round(miles, 1)
    if rounded == int(rounded):
        return f"{int(rounded):,}"
    return f"{rounded:,}"

def _fmt_txt_time(dt):
    """
    Formats a datetime as 'Tue 7:23 PM' for plain-text output.
    strftime's zero-stripped hour flag is platform-specific (%-I on
    POSIX, %#I on Windows), so the leading zero is stripped manually to
    behave identically on Heroku (Linux) and a Windows dev machine.
    """
    text = dt.strftime("%a %I:%M %p")   # 'Tue 07:23 PM'
    return text.replace(" 0", " ", 1)   # first ' 0' is always the hour slot


def generate_multi_stop_hos_itinerary(
    stops, legs, 
    speed, start_datetime, 
    cycle_hours_used=0.0,
    shift_drive_used=0.0,    # hrs driven since last 10-hr reset  (11-hr clock)
    window_used=0.0,         # hrs since coming on duty this shift (14-hr clock)
    drive_since_break=0.0,   # hrs driven since last 30+ min non-driving
    lookahead_miles=0.0,     # est. empty miles to an unbooked next pickup (0 = off)
):
    """
    Simulates a multi-stop truck trip under FMCSA property-carrying HOS
    rules (49 CFR 395.3), chaining drive legs and on-duty service/dwell
    stops while the HOS clocks run continuously.

    Extends generate_hos_itinerary() with:
      - Multiple legs with exact Google Maps miles per leg
      - On-duty (not driving) service/dwell time at each route point
      - The 14-hour driving window (binding once dwell time exists —
        pure-drive trips can never reach it, which is why the single-leg
        planner omits it)
      - The Sept 2020 break rule: ANY 30+ consecutive non-driving minutes
        (including on-duty loading/unloading) satisfies the 30-minute
        break requirement
      - Optional 70-hour/8-day cycle tracking (driving + on-duty service
        accumulate; a marker event is inserted when the plan crosses 70h)
      - Optional next-load lookahead: estimated deadhead miles appended
        as a hypothetical leg after destination service.  The clocks
        keep running and next_pickup_arrival reports when the driver is
        on site.  Metric boundaries: header capacity (drivable hours /
        miles) is snapshotted at driver-free time BEFORE the lookahead
        spends it; cycle figures INCLUDE the lookahead (cycle-left is
        only useful net of everything the plan draws); route totals and
        the summary footer EXCLUDE it (hypothetical miles must never
        leak into anything invoice-shaped)

    NOT modeled in v1 (stated on the tool page): sleeper-berth splits
    (8/2, 7/3), the 60-hr/7-day cycle, the 34-hour restart, adverse
    driving conditions, and the short-haul exception.

    Args:
        stops (list[dict]): Ordered route points, len >= 2.  Each dict:
            - "zip"           (str):   ZIP code of the point.
            - "service_hours" (float): On-duty dwell at that point
              (loading, unloading, lumper, etc.).  0 for rolling stops.
        legs (list[dict]): Consecutive-pair legs, len == len(stops) - 1.
            Each dict: "from_zip", "to_zip", "miles" (exact road miles
            from Google Maps, built by the view).
        speed (float): Average speed in mph (miles → drive hours).
        start_datetime (datetime): When the driver comes on duty.  The
            14-hour window starts here.
        cycle_hours_used (float): On-duty hours already used in the prior
            8 days (70-hr cycle).  0 disables nothing — tracking always
            runs — it just starts the counter at zero.
        lookahead_miles (float): Estimated empty road miles from the
            final destination to a next pickup that isn't booked yet.
            0 (the default) disables the lookahead entirely.

    Returns:
        dict: Itinerary rows plus summary metrics.  Row dicts use the
        same keys as generate_hos_itinerary() ("event", "start", "end",
        "duration", "note", "is_break", "is_highlight") with two new
        optional flags: "is_service" (dwell rows) and "is_warning"
        (70-hr cycle crossing marker).
    """
    # --- HOS rule constants (property-carrying CMV, 49 CFR 395.3) ---
    MAX_DRIVE_HOURS     = 11.0  # 395.3(a)(3)(i)  — driving per shift
    MAX_WINDOW_HOURS    = 14.0  # 395.3(a)(2)     — no driving after 14th hr
    BREAK_TRIGGER_HOURS = 8.0   # 395.3(a)(3)(ii) — break after 8 hrs driving
    BREAK_HOURS         = 0.5   # 30-minute break
    RESET_HOURS         = 10.0  # 395.3(a)(1)     — off-duty reset
    CYCLE_LIMIT_HOURS   = 70.0  # 395.3(b)(2)     — 70-hr/8-day cycle

    # --- Simulation state ---
    current_time    = start_datetime
    # Backdate the 14-hr anchor so window_elapsed() starts at window_used
    # instead of zero.  A driver 8 hrs into his day has 6 hrs of window left,
    # not 14 — this is the line that makes mid-shift replanning legal.
    window_start     = start_datetime - timedelta(hours=window_used or 0.0)
    shift_drive      = float(shift_drive_used or 0.0)
    continuous_drive = float(drive_since_break or 0.0)
    cycle_on_duty    = float(cycle_hours_used or 0.0)
    cycle_flagged   = False           # only insert one 70-hr crossing marker

    itinerary = []

    # --- Next-load lookahead setup --------------------------------------
    # A nonzero lookahead_miles appends a synthetic "est. deadhead" leg
    # after the final destination so the ONE tested drive loop handles
    # its chunking, breaks, resets, and cycle-crossing marker.  Local
    # copies keep the caller's lists unmutated; the real_* counts pin
    # every route-level metric (totals, leg numbering, the SMS route
    # string) to the REAL route so hypothetical miles never leak into
    # anything invoice-shaped.
    stops = list(stops)
    legs  = [dict(leg) for leg in legs]
    real_stop_count = len(stops)
    real_leg_count  = len(legs)
    lookahead_miles = float(lookahead_miles or 0.0)
    has_lookahead   = lookahead_miles > 0
    if has_lookahead:
        stops.append({
            "zip": "Next Pickup (Est.)",
            "service_hours": 0.0,
            "is_lookahead": True,
        })
        legs.append({
            "from_zip": stops[real_stop_count - 1]["zip"],
            "to_zip": "Next Pickup (Est.)",
            "miles": lookahead_miles,
            "is_lookahead": True,
        })

    # Outcome slots.  arrival_time / driver_free_time are set when the
    # real route completes (or by the post-loop fallbacks on truncation);
    # the driver-free capacity slots are filled by snapshot_driver_free().
    arrival_time             = None
    driver_free_time         = None
    next_pickup_arrival      = None
    lookahead_reset_required = False
    drive_remaining = window_remaining = drivable_now = reachable_miles = 0.0
    real_drive_hours = real_service_hours = real_rest_hours = 0.0

    # Totals for the summary footer (REAL legs only — see above).
    total_drive_hours   = 0.0
    total_service_hours = 0.0
    total_rest_hours    = 0.0  # 30-min breaks + 10-hr resets
    total_miles         = sum(leg["miles"] for leg in legs[:real_leg_count])
    cumulative_miles    = 0

    iterations = 0
    max_iterations = 300  # global safety catch (~50 per leg on a full route)
    truncated = False

    # ------------------------------------------------------------------
    # Internal helpers (closures over the state above)
    # ------------------------------------------------------------------
    def window_elapsed():
        """Hours elapsed in the current 14-hour window."""
        return (current_time - window_start).total_seconds() / 3600.0

    def check_cycle_crossing(chunk_start, cycle_before, hours_added):
        """
        Inserts a one-time marker row at the exact moment the plan crosses
        the 70-hour cycle limit inside a drive or service chunk.  The row
        is appended after the chunk's own row, timestamped mid-chunk.
        """
        nonlocal cycle_flagged
        if cycle_flagged:
            return
        if cycle_before < CYCLE_LIMIT_HOURS <= cycle_before + hours_added:
            hours_in = CYCLE_LIMIT_HOURS - cycle_before
            crossing = chunk_start + timedelta(hours=hours_in)
            itinerary.append({
                "event": "70-Hour Cycle Exceeded",
                "start": crossing, "end": "", "duration": "",
                "note": (
                    "The driver's 70-hr/8-day on-duty limit is crossed here. "
                    "A 34-hour restart or recap hours are required — "
                    "not modeled in this version."
                ),
                "is_warning": True,
            })
            cycle_flagged = True

    def snapshot_driver_free():
        """
        Freeze the driver-free moment and the clock capacity available at
        it, BEFORE any lookahead driving spends those clocks.  The
        Next-Load Answer header reports this state; the lookahead (if
        requested) then consumes it to produce next_pickup_arrival.
        """
        nonlocal driver_free_time, drive_remaining, window_remaining
        nonlocal drivable_now, reachable_miles
        nonlocal real_drive_hours, real_service_hours, real_rest_hours
        driver_free_time = current_time
        drive_remaining  = max(0.0, MAX_DRIVE_HOURS - shift_drive)
        window_remaining = max(0.0, MAX_WINDOW_HOURS - window_elapsed())
        cycle_left       = max(0.0, CYCLE_LIMIT_HOURS - cycle_on_duty)
        drivable_now     = min(drive_remaining, window_remaining, cycle_left)
        # Reachable distance is an UPPER BOUND: a mid-stretch 30-minute
        # break consumes window time when the window is the binding
        # clock — hence the "~" / "up to" phrasing in the template and
        # SMS.  Rounded to 5 mi so it reads as the estimate it is.
        reachable_miles  = 5 * round((drivable_now * speed) / 5)
        # Footer totals freeze here too, so lookahead drive/rest time
        # never bleeds into the real route's summary line.
        real_drive_hours   = total_drive_hours
        real_service_hours = total_service_hours
        real_rest_hours    = total_rest_hours

    def perform_reset(reason):
        """10 consecutive off-duty hours: restarts the 11-hr, 14-hr, and
        break clocks.  The fresh 14-hr window anchors to the return to
        duty (the end of the reset)."""
        nonlocal current_time, window_start, shift_drive, continuous_drive
        nonlocal total_rest_hours
        start_break = current_time
        current_time += timedelta(hours=RESET_HOURS)
        itinerary.append({
            "event": "10-Hour Reset",
            "start": start_break, "end": current_time,
            "duration": "10h 00m",
            "note": f"Mandatory Daily Reset ({reason})",
            "is_break": True,
        })
        shift_drive      = 0.0
        continuous_drive = 0.0
        window_start     = current_time
        total_rest_hours += RESET_HOURS

    def perform_service(zip_code, hours, label, has_more_driving):
        """
        On-duty (not driving) dwell: loading, unloading, lumper, etc.
        Consumes the 14-hr window and the 70-hr cycle, but NOT the 11-hr
        driving clock.  A dwell of 30+ minutes satisfies the 30-minute
        break requirement (FMCSA Sept 2020 final rule — the break may be
        on-duty/not-driving, not only off-duty).
        """
        nonlocal current_time, continuous_drive, cycle_on_duty
        nonlocal total_service_hours
        if hours <= 0:
            return
        start_service = current_time
        cycle_before  = cycle_on_duty
        current_time += timedelta(hours=hours)
        cycle_on_duty += hours
        total_service_hours += hours

        note_parts = [f"On-duty (not driving) at {zip_code}"]
        if hours >= BREAK_HOURS:
            continuous_drive = 0.0
            note_parts.append("satisfies the 30-minute break requirement")
        # Legal to work past the 14th hour — but driving is then prohibited
        # until a reset, which the pre-drive limit check below will insert.
        if window_elapsed() > MAX_WINDOW_HOURS and has_more_driving:
            note_parts.append(
                "extends past the 14-hour window; a 10-hour reset is "
                "required before driving resumes"
            )

        itinerary.append({
            "event": label,
            "start": start_service, "end": current_time,
            "duration": _fmt_hos_duration(hours),
            "note": " · ".join(note_parts),
            "is_service": True,
        })
        check_cycle_crossing(start_service, cycle_before, hours)

    # ------------------------------------------------------------------
    # 1. Service at the origin (loading), if any.
    # ------------------------------------------------------------------
    origin = stops[0]
    perform_service(
        origin["zip"], origin.get("service_hours") or 0.0,
        f"Load / Service — Origin {origin['zip']}",
        has_more_driving=True,
    )

    # ------------------------------------------------------------------
    # 2. Drive each leg, inserting breaks/resets as the clocks demand,
    #    then handle arrival + service at the leg's destination point.
    # ------------------------------------------------------------------
    for leg_index, leg in enumerate(legs):
        miles_remaining   = float(leg["miles"])
        dest_point        = stops[leg_index + 1]
        is_lookahead_leg  = bool(leg.get("is_lookahead"))
        is_final_real_leg = leg_index == real_leg_count - 1

        while miles_remaining > 0.1 and iterations < max_iterations:
            iterations += 1

            time_left_shift      = MAX_DRIVE_HOURS - shift_drive
            time_left_window     = MAX_WINDOW_HOURS - window_elapsed()
            time_left_continuous = BREAK_TRIGGER_HOURS - continuous_drive

            # --- A) Daily driving clocks exhausted? → 10-hour reset. ---
            if time_left_shift <= 0.01 or time_left_window <= 0.01:
                reason = (
                    "11-hour driving limit reached"
                    if time_left_shift <= 0.01
                    else "14-hour on-duty window reached"
                )
                perform_reset(reason)
                if is_lookahead_leg:
                    lookahead_reset_required = True
                continue

            # --- B) 8 hours driving since last break? → 30-min break,
            #        unless the window can't fit driving after it. ---
            if time_left_continuous <= 0.01:
                if time_left_window <= BREAK_HOURS + 0.01:
                    # A break would eat the rest of the window; go
                    # straight to the reset instead of wasting 30 min.
                    perform_reset("14-hour on-duty window reached")
                    if is_lookahead_leg:
                        lookahead_reset_required = True
                else:
                    start_break = current_time
                    current_time += timedelta(hours=BREAK_HOURS)
                    itinerary.append({
                        "event": "30-Min Break",
                        "start": start_break, "end": current_time,
                        "duration": "0h 30m",
                        "note": "Mandatory FMCSA break (8 hours driving "
                                "since last qualifying break)",
                        "is_break": True,
                    })
                    continuous_drive = 0.0
                    total_rest_hours += BREAK_HOURS
                continue

            # --- C) Drive the largest chunk the clocks allow. ---
            time_to_finish = miles_remaining / speed
            leg_duration = min(
                time_to_finish,
                time_left_shift,
                time_left_window,
                time_left_continuous,
            )
            if leg_duration < 0.01:  # avoid float fragments
                continue

            dist_covered   = leg_duration * speed
            start_leg_time = current_time
            cycle_before   = cycle_on_duty
            current_time  += timedelta(hours=leg_duration)

            miles_remaining  -= dist_covered
            shift_drive      += leg_duration
            continuous_drive += leg_duration
            cycle_on_duty    += leg_duration
            total_drive_hours += leg_duration

            if is_lookahead_leg:
                drive_note = (
                    f"Covered {_fmt_miles(dist_covered)} mi · "
                    "Est. deadhead toward next pickup"
                )
            else:
                drive_note = (
                    f"Covered {_fmt_miles(dist_covered)} mi · "
                    f"{leg['from_zip']} → {leg['to_zip']} "
                    f"(Leg {leg_index + 1} of {real_leg_count})"
                )
            drive_row = {
                "event": "Drive",
                "start": start_leg_time, "end": current_time,
                "duration": _fmt_hos_duration(leg_duration),
                "note": drive_note,
            }
            if is_lookahead_leg:
                # Event name stays "Drive" — the driver_text builder
                # keys on it to append the note.  The flag drives the
                # muted row styling in the template instead.
                drive_row["is_lookahead"] = True
            itinerary.append(drive_row)
            check_cycle_crossing(start_leg_time, cycle_before, leg_duration)

        if iterations >= max_iterations:
            truncated = True
            break

        # --- Arrival at this leg's destination point. ---
        if is_lookahead_leg:
            # Hypothetical arrival at the unbooked next pickup.  No
            # service dwell — loading time is unknown until it's booked —
            # and no cumulative-miles line, because lookahead miles are
            # not route miles.
            next_pickup_arrival = current_time
            itinerary.append({
                "event": "Next Pickup Reached (Est.)",
                "start": current_time, "end": "", "duration": "",
                "note": (
                    f"~{_fmt_miles(lookahead_miles)} est. deadhead mi beyond "
                    "the route · time shown is arrival, before loading"
                ),
                "is_lookahead": True,
            })
        else:
            cumulative_miles += leg["miles"]
            if is_final_real_leg:
                arrive_event = "Arrive — Final Destination"
            else:
                arrive_event = f"Arrive — Stop {leg_index + 1}"
            itinerary.append({
                "event": arrive_event,
                "start": current_time, "end": "", "duration": "",
                "note": (
                    f"{dest_point['zip']} · "
                    f"{_fmt_miles(cumulative_miles)} of {_fmt_miles(total_miles)} route miles"
                ),
                "is_highlight": True,
            })

            if is_final_real_leg:
                arrival_time = current_time
                # Unloading at the destination happens after the ETA; it
                # affects when the driver is FREE, not when the load arrives.
                perform_service(
                    dest_point["zip"], dest_point.get("service_hours") or 0.0,
                    f"Unload / Service — Destination {dest_point['zip']}",
                    # A lookahead (if any) is more driving: keep the
                    # 14-hr overrun warning and the pre-drive reset
                    # logic armed for it.
                    has_more_driving=has_lookahead,
                )
                # Freeze the driver-free state BEFORE any lookahead
                # driving spends the remaining clocks.
                snapshot_driver_free()
            else:
                perform_service(
                    dest_point["zip"], dest_point.get("service_hours") or 0.0,
                    f"Service — Stop {leg_index + 1} ({dest_point['zip']})",
                    has_more_driving=True,
                )

    if truncated and arrival_time is None:
        # Safety catch tripped before the real destination was reached —
        # return what we have with a flag; the template surfaces a
        # warning instead of an incomplete-looking plan.  (Truncation
        # during a lookahead leaves the real arrival_time intact.)
        arrival_time = current_time
    if driver_free_time is None:
        # The real route never completed (truncation): freeze whatever
        # state the simulation ended in so the header still renders
        # coherent numbers.
        snapshot_driver_free()

    # ------------------------------------------------------------------
    # 2.5 Day separator rows (multi-day readability, esp. printed sheets).
    #     Inserted wherever the calendar date of an event's START differs
    #     from the previous event's. A marker means "rows below begin on
    #     this day" — an event that crosses midnight stays under the day
    #     it started. Markers carry is_day=True; the template renders them
    #     as full-width divider rows and the driver_text builder skips
    #     them (each SMS line already carries its own weekday prefix).
    # ------------------------------------------------------------------
    dated_itinerary = []
    current_day = None
    for row in itinerary:
        row_day = row["start"].date()
        if row_day != current_day:
            current_day = row_day
            dated_itinerary.append({
                # "Friday, July 17" — strip %d's leading zero the same
                # platform-safe way _fmt_txt_time does.
                "event": row["start"].strftime("%A, %B %d").replace(" 0", " "),
                "start": row["start"], "end": "", "duration": "",
                "note": "", "is_day": True,
            })
        dated_itinerary.append(row)
    itinerary = dated_itinerary

    # ------------------------------------------------------------------
    # 3. The "next-load answer" — Max's actual question.
    #    Clock capacity (drive / window / drivable / reachable) comes
    #    from the driver-free snapshot, taken BEFORE any lookahead
    #    driving spent it.  Cycle figures deliberately run post-lookahead:
    #    "cycle left" is only useful net of everything the plan drew.
    # ------------------------------------------------------------------
    cycle_remaining = max(0.0, CYCLE_LIMIT_HOURS - cycle_on_duty)

    fresh_after_reset = driver_free_time + timedelta(hours=RESET_HOURS)
    total_trip_hours = (
        (driver_free_time - start_datetime).total_seconds() / 3600.0
    )

    # ------------------------------------------------------------------
    # 4. Plain-text driver itinerary (Copy button → SMS/WhatsApp handoff).
    #    Kept strictly GSM-7 (plain ASCII) — unicode arrows or bullets
    #    force SMS into UCS-2 encoding, which cuts segments from 160 to
    #    70 characters and multiplies the dispatcher's message count.
    # ------------------------------------------------------------------
    txt_lines = [
        "HOS TRIP PLAN (planning estimate - not an official RODS log)",
        f"Route: {' > '.join(s['zip'] for s in stops[:real_stop_count])} "
        f"({_fmt_miles(total_miles)} mi)",
        "",
    ]
    for row in itinerary:
        if row.get("is_day"):
            continue  # visual divider only — SMS lines already carry the weekday
        line = f"- {_fmt_txt_time(row['start'])}  {row['event']}"
        if row.get("duration"):
            line += f", {row['duration']}"
        if row["event"] == "Drive":
            line += f" ({row['note']})"
        txt_lines.append(line)
    txt_lines += [
        "",
        f"Driver free: {_fmt_txt_time(driver_free_time)}",
        f"Drivable hours left: {_fmt_hos_duration(drivable_now)}",
        # "up to" (not "~"): tilde sits in the GSM-7 extension table and
        # costs a second septet per use.
        f"Drivable miles left: up to {_fmt_miles(reachable_miles)} mi",
        f"Fresh after 10-hr reset: {_fmt_txt_time(fresh_after_reset)}",
    ]
    if next_pickup_arrival is not None:
        txt_lines.append(
            f"At next pickup (est. {_fmt_miles(lookahead_miles)} mi): "
            f"{_fmt_txt_time(next_pickup_arrival)}"
        )
    driver_text = "\n".join(txt_lines)
    # Sanitize unicode that leaks in from event names and drive notes.
    for bad, good in {"—": "-", "·": "-", "→": ">", "➜": ">"}.items():
        driver_text = driver_text.replace(bad, good)

    return {
        "itinerary": itinerary,
        "truncated": truncated,
        "driver_text": driver_text,

        # --- Headline times ---
        "arrival_time": arrival_time,           # ETA at the final stop
        "driver_free_time": driver_free_time,   # after destination service
        "fresh_after_reset": fresh_after_reset, # driver_free + 10 hrs

        # --- Clocks at driver-free time (pre-lookahead snapshot) ---
        "drive_remaining_str": _fmt_hos_duration(drive_remaining),
        "window_remaining_str": _fmt_hos_duration(window_remaining),
        "drivable_now_str": _fmt_hos_duration(drivable_now),
        "can_drive_now": drivable_now > 0.25,   # at least 15 usable minutes
        "reachable_miles_str": _fmt_miles(reachable_miles),

        # --- Next-load lookahead (None / "" / False when not requested) ---
        "next_pickup_arrival": next_pickup_arrival,
        "lookahead_miles_str": _fmt_miles(lookahead_miles) if has_lookahead else "",
        "lookahead_reset_required": lookahead_reset_required,

        # --- 70-hr cycle ---
        "cycle_used": round(cycle_on_duty, 2),
        "cycle_remaining_str": _fmt_hos_duration(cycle_remaining),
        "cycle_exceeded": cycle_on_duty > CYCLE_LIMIT_HOURS,
        "cycle_overage_str": _fmt_hos_duration(
            max(0.0, cycle_on_duty - CYCLE_LIMIT_HOURS)
        ),

        # --- Totals footer ---
        "total_miles": _fmt_miles(total_miles),
        "total_legs": real_leg_count,
        "num_intermediate_stops": max(real_stop_count - 2, 0),
        "total_drive_str": _fmt_hos_duration(real_drive_hours),
        "total_service_str": _fmt_hos_duration(real_service_hours),
        "total_rest_str": _fmt_hos_duration(real_rest_hours),
        "total_trip_str": _fmt_hos_duration(total_trip_hours),
    }

def calculate_required_tie_downs(weight, length, strap_wll):
    """
    Calculates the minimum required tie-downs based on FMCSA § 393.102 (Weight/Aggregate WLL)
    and § 393.106 (Length). Returns the strictest standard.
    """
    strap_wll = float(strap_wll)

    # --- Rule A: Aggregate WLL (Weight Requirement) ---
    # The aggregate WLL must be at least 50% of the cargo weight.
    required_aggregate_wll = weight * 0.50
    tie_downs_by_weight = math.ceil(required_aggregate_wll / strap_wll)

    # --- Rule B: Length Requirement ---
    if length <= 5:
        tie_downs_by_length = 1 if weight <= 1100 else 2
    elif length <= 10:
        tie_downs_by_length = 2
    else:
        # 2 tie-downs for first 10 ft, + 1 for every 10ft (or fraction) beyond.
        extra_length = length - 10
        tie_downs_by_length = 2 + math.ceil(extra_length / 10)

    # The law requires the STRICTER of the two rules.
    final_count = max(tie_downs_by_weight, tie_downs_by_length)

    # Determine which rule was the deciding factor for the UI explanation.
    if tie_downs_by_weight >= tie_downs_by_length:
        reason = "Weight (Aggregate WLL)"
    else:
        reason = "Cargo Length"

    return {
        "final_count": final_count,
        "by_weight": tie_downs_by_weight,
        "by_length": tie_downs_by_length,
        "limiting_factor": reason,
        "cargo_weight": weight,
        "cargo_length": length
    }

def calculate_cost_per_mile(miles, truck_pay, insurance, other_fixed, fuel_cpm, maint_cpm, driver_cpm):
    """
    Calculates the Cost Per Mile (CPM) / Break-Even rate for an owner-operator.
    Returns breakdown of fixed vs. variable costs.
    """
    # 1. Total Monthly Fixed Costs
    total_fixed_monthly = truck_pay + insurance + other_fixed
    fixed_cpm = total_fixed_monthly / miles

    # 2. Total Variable CPM
    variable_cpm = fuel_cpm + maint_cpm + driver_cpm

    # 3. Final Break-Even CPM
    total_cpm = fixed_cpm + variable_cpm

    return {
        "total_cpm": round(total_cpm, 2),
        "fixed_cpm": round(fixed_cpm, 2),
        "variable_cpm": round(variable_cpm, 2),
        "total_fixed_monthly": round(total_fixed_monthly, 2),
        "monthly_miles": miles
    }
import math

def calculate_linear_feet(length, width, height, weight, quantity, is_stackable):
    """
    Calculates Linear Feet occupied in a standard 53' trailer and checks for LTL rule violations.
    Standard trailer width is approx. 96-102 inches.
    """
    # Convert string boolean from form to Python boolean
    is_stackable = is_stackable == 'True'

    # 1. Determine Floor Spaces Needed (Pinwheeling/Turned Pallets Logic)
    # A standard 48x40 pallet can be placed side-by-side (40+40 = 80 inches) in a 96" wide trailer.
    pallets_per_row = 1
    if (width * 2) <= 96:
        pallets_per_row = 2
    elif (width + length) <= 96: # Pinwheeling
        pallets_per_row = 2

    # If stackable, you need half the floor spaces.
    effective_quantity = math.ceil(quantity / 2) if is_stackable else quantity
    
    # Calculate rows required
    rows_required = math.ceil(effective_quantity / pallets_per_row)

    # 2. Calculate Linear Feet
    # If pinwheeled, the math gets complex. For standard LTL estimates, Carriers use the longest dimension per row.
    linear_inches = rows_required * max(length, width) if pallets_per_row == 2 and (width + length) <= 96 else rows_required * length
    linear_feet = linear_inches / 12.0

    # 3. Calculate Density (Total Weight / Total Cubic Feet)
    total_weight = weight * quantity
    total_cubic_feet = (length * width * height * quantity) / 1728.0
    density = total_weight / total_cubic_feet if total_cubic_feet > 0 else 0

    # 4. Check "Linear Foot Rule" (Industry Standard: > 12 feet AND < 6 lbs/cubic ft)
    rule_triggered = linear_feet >= 12.0 and density < 6.0

    return {
        "linear_feet": round(linear_feet, 1),
        "total_weight": round(total_weight, 2),
        "density": round(density, 2),
        "rows": rows_required,
        "is_stackable": is_stackable,
        "rule_triggered": rule_triggered
    }

def calculate_detention_fee(arrival_dt, departure_dt, free_time_hours, hourly_rate):
    """
    Calculates the total time at the facility, the billable detention time,
    and the total fee owed based on the hourly rate.
    """
    # 1. Calculate Total Time (timedelta)
    time_diff = departure_dt - arrival_dt
    total_hours = time_diff.total_seconds() / 3600.0

    # 2. Determine Billable Hours
    billable_hours = max(0, total_hours - free_time_hours)

    # 3. Calculate Fee
    total_fee = billable_hours * hourly_rate

    # Format output for the UI
    total_h = int(total_hours)
    total_m = int((total_hours - total_h) * 60)
    
    billable_h = int(billable_hours)
    billable_m = int((billable_hours - billable_h) * 60)

    return {
        "total_fee": round(total_fee, 2),
        "total_time_str": f"{total_h}h {total_m}m",
        "billable_time_str": f"{billable_h}h {billable_m}m",
        "billable_hours_decimal": round(billable_hours, 2),
        "is_detention_owed": total_fee > 0
    }

import math

def calculate_warehouse_storage(area_length, area_width, p_length, p_width, stack_height):
    """
    Calculates the maximum number of pallets that can fit into a specific warehouse footprint.
    Checks both standard orientation and rotated orientation to maximize space.
    """
    # Convert area feet to inches
    area_l_in = area_length * 12
    area_w_in = area_width * 12

    # Option 1: Standard Orientation (Pallet Length along Area Length)
    rows_1 = math.floor(area_l_in / p_length)
    cols_1 = math.floor(area_w_in / p_width)
    total_floor_1 = rows_1 * cols_1

    # Option 2: Rotated Orientation (Pallet Width along Area Length)
    rows_2 = math.floor(area_l_in / p_width)
    cols_2 = math.floor(area_w_in / p_length)
    total_floor_2 = rows_2 * cols_2

    # Determine optimal orientation
    max_floor_pallets = max(total_floor_1, total_floor_2)
    best_orientation = "Standard (Lengthwise)" if total_floor_1 >= total_floor_2 else "Rotated (Widthwise)"

    # Apply Stacking
    total_capacity = max_floor_pallets * stack_height

    return {
        "max_capacity": total_capacity,
        "floor_capacity": max_floor_pallets,
        "stack_height": stack_height,
        "orientation": best_orientation,
        "total_sq_ft": round(area_length * area_width, 1)
    }

def calculate_partial_rate(origin_zip, dest_zip, distance_miles, trailer_type, pallets, weight, base_ftl_cpm, markup, min_charge):
    """
    Estimates a Volume LTL / Partial rate based on specific trailer utilization.
    Calculates the FTL baseline cost and applies the broker's specific financial parameters.
    """
    # 1. Define Trailer Constraints based on Selection
    TRAILER_SPECS = {
        "dry_van": {"max_pallets": 26, "max_weight": 40000},
        "reefer":  {"max_pallets": 26, "max_weight": 38000}, # Heavy refrigeration unit reduces weight capacity
        "flatbed": {"max_pallets": 24, "max_weight": 45000}  # Flatbeds are usually 48' but carry more weight
    }
    
    max_pallets = TRAILER_SPECS[trailer_type]["max_pallets"]
    max_weight = TRAILER_SPECS[trailer_type]["max_weight"]

    # 2. Use exact road miles directly from Google Maps
    road_miles = distance_miles
    
    # 3. Calculate the Full Truckload (FTL) baseline cost
    ftl_cost = road_miles * base_ftl_cpm
    
    # 4. Determine trailer utilization (take the higher percentage: space or weight)
    space_percentage = pallets / max_pallets
    weight_percentage = weight / max_weight
    trailer_utilization = max(space_percentage, weight_percentage)
    
    # 5. Calculate Final Estimate using the Broker's financial variables
    partial_estimate = ftl_cost * trailer_utilization * markup
    
    # Ensure a minimum charge (user-defined)
    final_rate = max(min_charge, partial_estimate)
    
    # 6. Check if FTL might be cheaper/better
    # Triggers if they use more than 60% of the trailer capacity
    recommend_ftl = trailer_utilization >= 0.60

    return {
        "estimated_rate": round(final_rate, 2),
        "road_miles": int(road_miles),
        "trailer_percentage": round(trailer_utilization * 100, 1),
        "recommend_ftl": recommend_ftl,
        "origin_zip": origin_zip,
        "dest_zip": dest_zip,
        "limiting_factor": "Space" if space_percentage >= weight_percentage else "Weight"
    }

def calculate_deadhead_cost(
    deadhead_miles, operating_cpm,
    load_rate=None, loaded_miles=None
):
    """
    Calculates the cost of running empty (deadhead) miles and, if a load
    is being evaluated, determines whether accepting it is profitable after
    factoring in the deadhead repositioning cost.

    Args:
        deadhead_miles (int): Exact road miles from current position to pickup
                              (sourced from Google Maps via get_road_distance).
        operating_cpm (float): The operator's all-in Cost Per Mile (from CPM tool).
        load_rate (float|None): The flat dollar rate offered for the next load.
        loaded_miles (int|None): Exact road miles for the loaded portion of the
                                 next load (sourced from Google Maps).

    Returns:
        dict: Deadhead cost breakdown plus optional load profitability analysis.
    """
    # --- 1. Core Deadhead Cost ---
    deadhead_cost = deadhead_miles * operating_cpm

    results = {
        "deadhead_miles": deadhead_miles,
        "operating_cpm": operating_cpm,
        "deadhead_cost": round(deadhead_cost, 2),
    }

    # --- 2. Load Profitability Analysis (only if a load is being evaluated) ---
    if load_rate is not None and loaded_miles is not None and loaded_miles > 0:
        # Total miles the truck will actually travel (empty + loaded)
        total_trip_miles = deadhead_miles + loaded_miles

        # Total operating cost for the entire repositioning + haul
        total_operating_cost = total_trip_miles * operating_cpm

        # Net profit/loss after all costs
        net_profit = load_rate - total_operating_cost

        # Effective Rate Per Mile based on ALL miles driven (the real number)
        effective_rpm_all_miles = load_rate / total_trip_miles if total_trip_miles > 0 else 0.0

        # Effective Rate Per Mile based on LOADED miles only (what the rate sheet shows)
        effective_rpm_loaded = load_rate / loaded_miles

        # Minimum flat rate needed to break even on total miles
        break_even_rate = total_operating_cost

        # Minimum Rate Per Loaded Mile the load needs to pay to cover all miles
        min_rpm_loaded = total_operating_cost / loaded_miles

        # Deadhead Ratio: empty miles as a percentage of loaded miles
        # Industry rule of thumb: >15-20% deadhead ratio starts hurting margins
        deadhead_ratio = (deadhead_miles / loaded_miles) * 100

        # Profitability flag
        is_profitable = net_profit > 0

        # How many times over CPM is the effective RPM?
        profit_margin_ratio = effective_rpm_all_miles / operating_cpm if operating_cpm > 0 else 0

        results.update({
            "has_load_analysis": True,
            "load_rate": round(load_rate, 2),
            "loaded_miles": loaded_miles,
            "total_trip_miles": total_trip_miles,
            "total_operating_cost": round(total_operating_cost, 2),
            "net_profit": round(net_profit, 2),
            "abs_net_profit": round(abs(net_profit), 2),
            "effective_rpm_all_miles": round(effective_rpm_all_miles, 3),
            "effective_rpm_loaded": round(effective_rpm_loaded, 3),
            "break_even_rate": round(break_even_rate, 2),
            "min_rpm_loaded": round(min_rpm_loaded, 3),
            "deadhead_ratio": round(deadhead_ratio, 1),
            "is_profitable": is_profitable,
            "profit_margin_ratio": round(profit_margin_ratio, 2),
        })
    else:
        results["has_load_analysis"] = False

    return results

def calculate_multi_stop_route(legs, stop_off_charge=None):
    """
    Aggregates per-leg mileage data produced by the view (which calls
    get_road_distance for each consecutive pair) into a full route
    breakdown suitable for invoicing, driver pay, and stop-off billing.

    Args:
        legs (list[dict]): Ordered list of leg dicts.  Each dict contains:
            - "from_zip"  (str): Origin ZIP for this leg.
            - "to_zip"    (str): Destination ZIP for this leg.
            - "miles"     (int): Exact road miles from Google Maps.
        stop_off_charge (float|None): Optional dollar amount charged per
            intermediate stop (every stop that is NOT the origin or final
            destination).  Common values: $50–$150 per stop.

    Returns:
        dict: Full route breakdown including:
            - legs (list[dict]): Enriched with leg_number, cumulative_miles,
              pct_of_total, and label.
            - total_miles (int): Sum of all leg miles.
            - total_legs (int): Number of legs.
            - num_stops (int): Total route points (origin + stops + dest).
            - num_intermediate_stops (int): Stops between origin and dest.
            - stop_off_charge (float|None): Per-stop charge echoed back.
            - total_stop_off_charges (float): Total stop-off fees.
            - has_stop_off (bool): Whether stop-off billing is active.
    """
    total_miles = sum(leg["miles"] for leg in legs)

    # Enrich each leg with computed fields.
    cumulative = 0
    for i, leg in enumerate(legs):
        cumulative += leg["miles"]
        leg["leg_number"] = i + 1
        leg["cumulative_miles"] = cumulative
        leg["pct_of_total"] = (
            round((leg["miles"] / total_miles) * 100, 1) if total_miles > 0 else 0.0
        )
        leg["label"] = f"Leg {i + 1}: {leg['from_zip']} → {leg['to_zip']}"

    # Stop-off charges: billed for every intermediate stop.
    # Route A → B → C → D has intermediate stops B and C (= total_legs - 1).
    num_intermediate_stops = max(len(legs) - 1, 0)
    total_stop_off = 0.0
    if stop_off_charge and stop_off_charge > 0 and num_intermediate_stops > 0:
        total_stop_off = round(stop_off_charge * num_intermediate_stops, 2)

    # Total unique points on the route (origin + intermediates + destination).
    num_stops = len(legs) + 1

    return {
        "legs": legs,
        "total_miles": total_miles,
        "total_legs": len(legs),
        "num_stops": num_stops,
        "num_intermediate_stops": num_intermediate_stops,
        "stop_off_charge": round(stop_off_charge, 2) if stop_off_charge else None,
        "total_stop_off_charges": total_stop_off,
        "has_stop_off": stop_off_charge is not None and stop_off_charge > 0,
    }

def calculate_lane_rate(
    origin_zip, dest_zip, distance_miles, line_haul_rate,
    fuel_surcharge=None, operating_cpm=None
):
    """
    Analyzes a quoted freight rate against exact Google Maps road miles to
    produce effective Rate Per Mile (RPM) metrics, optional all-in analysis
    with fuel surcharge, and optional margin analysis against operating CPM.

    Args:
        origin_zip (str): Origin ZIP code (for display context).
        dest_zip (str): Destination ZIP code (for display context).
        distance_miles (int): Exact road miles from Google Maps.
        line_haul_rate (float): Flat dollar rate quoted for the load.
        fuel_surcharge (float|None): Total fuel surcharge for the trip ($).
        operating_cpm (float|None): All-in operating Cost Per Mile ($).

    Returns:
        dict: Rate analysis breakdown.
    """
    # --- Core RPM Calculation ---
    line_haul_rpm = line_haul_rate / distance_miles if distance_miles > 0 else 0.0

    results = {
        "origin_zip": origin_zip,
        "dest_zip": dest_zip,
        "distance_miles": distance_miles,
        "line_haul_rate": round(line_haul_rate, 2),
        "line_haul_rpm": round(line_haul_rpm, 3),
    }

    # --- Rate Context (general dry van benchmarks) ---
    # These tiers provide directional context, not authoritative market data.
    if line_haul_rpm < 1.50:
        rate_context = "well_below"
        rate_context_label = "Well Below Average"
        rate_context_note = (
            "This rate is well below typical dry van market rates. "
            "Most carriers cannot operate profitably at this level."
        )
    elif line_haul_rpm < 2.00:
        rate_context = "below"
        rate_context_label = "Below Average"
        rate_context_note = (
            "This rate is below the typical dry van range. "
            "Margins will be tight for most carriers."
        )
    elif line_haul_rpm < 2.75:
        rate_context = "average"
        rate_context_label = "Average Range"
        rate_context_note = (
            "This rate falls within the typical dry van spot market range."
        )
    elif line_haul_rpm < 3.50:
        rate_context = "above"
        rate_context_label = "Above Average"
        rate_context_note = (
            "This is a strong rate, above typical dry van averages."
        )
    else:
        rate_context = "premium"
        rate_context_label = "Premium Rate"
        rate_context_note = (
            "This is a premium rate, typical of specialized, expedited, "
            "or high-demand lanes."
        )

    results["rate_context"] = rate_context
    results["rate_context_label"] = rate_context_label
    results["rate_context_note"] = rate_context_note

    # --- Fuel Surcharge Analysis (optional) ---
    if fuel_surcharge is not None and fuel_surcharge > 0:
        all_in_rate = line_haul_rate + fuel_surcharge
        all_in_rpm = all_in_rate / distance_miles if distance_miles > 0 else 0.0
        fsc_per_mile = fuel_surcharge / distance_miles if distance_miles > 0 else 0.0

        results["has_fsc"] = True
        results["fuel_surcharge"] = round(fuel_surcharge, 2)
        results["all_in_rate"] = round(all_in_rate, 2)
        results["all_in_rpm"] = round(all_in_rpm, 3)
        results["fsc_per_mile"] = round(fsc_per_mile, 3)
    else:
        results["has_fsc"] = False

    # --- Margin Analysis (optional, requires operating CPM) ---
    if operating_cpm is not None and operating_cpm > 0:
        total_operating_cost = operating_cpm * distance_miles

        # Use all-in rate if FSC was provided, otherwise line-haul only.
        revenue = results.get("all_in_rate", line_haul_rate)
        net_profit = revenue - total_operating_cost
        is_profitable = net_profit > 0

        # Margin percentage: (revenue - cost) / revenue * 100
        margin_pct = (net_profit / revenue) * 100 if revenue > 0 else 0.0

        # Net profit per mile
        net_profit_per_mile = net_profit / distance_miles if distance_miles > 0 else 0.0

        results["has_margin"] = True
        results["operating_cpm"] = round(operating_cpm, 2)
        results["total_operating_cost"] = round(total_operating_cost, 2)
        results["net_profit"] = round(net_profit, 2)
        results["abs_net_profit"] = round(abs(net_profit), 2)
        results["is_profitable"] = is_profitable
        results["margin_pct"] = round(margin_pct, 1)
        results["net_profit_per_mile"] = round(net_profit_per_mile, 3)
        results["revenue_label"] = "All-In" if results.get("has_fsc") else "Line-Haul"
    else:
        results["has_margin"] = False

    return results

def calculate_freight_margin(
    customer_rate, carrier_rate,
    customer_fsc=None, carrier_fsc=None,
    customer_accessorials=None, carrier_accessorials=None,
    distance_miles=None, origin_zip=None, dest_zip=None
):
    """
    Calculates brokerage gross profit and margin on a freight load.

    Computes the spread between what the shipper (customer) pays and what the
    carrier receives, including optional fuel surcharges and accessorial costs
    on each side. When ZIPs are provided and Google Maps mileage is available,
    also returns per-mile profitability metrics.

    Args:
        customer_rate (float): Line-haul rate billed to the shipper ($).
        carrier_rate (float): Line-haul rate paid to the carrier ($).
        customer_fsc (float|None): FSC billed to customer ($).
        carrier_fsc (float|None): FSC paid to carrier ($).
        customer_accessorials (float|None): Extra charges billed to customer ($).
        carrier_accessorials (float|None): Extra costs paid to carrier ($).
        distance_miles (int|None): Exact road miles from Google Maps.
        origin_zip (str|None): Origin ZIP (for display context).
        dest_zip (str|None): Destination ZIP (for display context).

    Returns:
        dict: Margin analysis breakdown.
    """
    # --- Revenue Side (what the customer pays the brokerage) ---
    cust_fsc = customer_fsc if customer_fsc and customer_fsc > 0 else 0.0
    cust_acc = customer_accessorials if customer_accessorials and customer_accessorials > 0 else 0.0
    customer_all_in = customer_rate + cust_fsc + cust_acc

    # --- Cost Side (what the brokerage pays the carrier) ---
    carr_fsc = carrier_fsc if carrier_fsc and carrier_fsc > 0 else 0.0
    carr_acc = carrier_accessorials if carrier_accessorials and carrier_accessorials > 0 else 0.0
    carrier_all_in = carrier_rate + carr_fsc + carr_acc

    # --- Core Margin Calculation ---
    gross_profit = customer_all_in - carrier_all_in
    is_profitable = gross_profit > 0

    # Margin %: (Gross Profit / Customer All-In Revenue) * 100
    margin_pct = (gross_profit / customer_all_in) * 100 if customer_all_in > 0 else 0.0

    # --- Line-Haul-Only Spread (always useful to see the base spread) ---
    line_haul_spread = customer_rate - carrier_rate

    # --- FSC Spread (if either side has FSC) ---
    fsc_spread = cust_fsc - carr_fsc

    # --- Margin Health Indicator ---
    if margin_pct < 5:
        margin_health = "critical"
        margin_health_label = "Critical — Below Break-Even Risk"
        margin_health_note = (
            "After overhead (software, insurance, back-office), "
            "margins below 5% often result in a net loss for the brokerage."
        )
    elif margin_pct < 10:
        margin_health = "tight"
        margin_health_label = "Tight Margin"
        margin_health_note = (
            "This covers basic operating costs but leaves little room "
            "for claims, chargebacks, or payment delays."
        )
    elif margin_pct < 18:
        margin_health = "average"
        margin_health_label = "Average Brokerage Margin"
        margin_health_note = (
            "This falls within the typical freight brokerage target range of 10–18%."
        )
    elif margin_pct < 25:
        margin_health = "strong"
        margin_health_label = "Strong Margin"
        margin_health_note = (
            "Above-average margin. Common on contracted lanes, "
            "specialized equipment, or high-service accounts."
        )
    else:
        margin_health = "premium"
        margin_health_label = "Premium Margin"
        margin_health_note = (
            "Exceptional spread, typical of expedited freight, "
            "hot-shot loads, or niche capacity situations."
        )

    results = {
        # --- Core ---
        "customer_rate": round(customer_rate, 2),
        "carrier_rate": round(carrier_rate, 2),
        "customer_all_in": round(customer_all_in, 2),
        "carrier_all_in": round(carrier_all_in, 2),
        "gross_profit": round(gross_profit, 2),
        "abs_gross_profit": round(abs(gross_profit), 2),
        "margin_pct": round(margin_pct, 1),
        "is_profitable": is_profitable,
        "line_haul_spread": round(line_haul_spread, 2),

        # --- Health ---
        "margin_health": margin_health,
        "margin_health_label": margin_health_label,
        "margin_health_note": margin_health_note,

        # --- FSC breakdown (only if at least one side has FSC) ---
        "has_fsc": cust_fsc > 0 or carr_fsc > 0,
        "customer_fsc": round(cust_fsc, 2),
        "carrier_fsc": round(carr_fsc, 2),
        "fsc_spread": round(fsc_spread, 2),

        # --- Accessorials breakdown (only if at least one side has accessorials) ---
        "has_accessorials": cust_acc > 0 or carr_acc > 0,
        "customer_accessorials": round(cust_acc, 2),
        "carrier_accessorials": round(carr_acc, 2),
        "accessorial_spread": round(cust_acc - carr_acc, 2),
    }

    # --- Per-Mile Analysis (optional, requires Google Maps distance) ---
    if distance_miles and distance_miles > 0:
        revenue_per_mile = customer_all_in / distance_miles
        cost_per_mile = carrier_all_in / distance_miles
        profit_per_mile = gross_profit / distance_miles

        results["has_mileage"] = True
        results["distance_miles"] = distance_miles
        results["origin_zip"] = origin_zip or ""
        results["dest_zip"] = dest_zip or ""
        results["revenue_per_mile"] = round(revenue_per_mile, 3)
        results["cost_per_mile"] = round(cost_per_mile, 3)
        results["profit_per_mile"] = round(profit_per_mile, 3)
    else:
        results["has_mileage"] = False

    return results