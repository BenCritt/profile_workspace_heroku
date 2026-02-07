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