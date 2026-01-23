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