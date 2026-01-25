import math

def calculate_glass_volume_weight(shape, glass_type, waste_factor, data):
    """
    Calculates volume and weight for the Glass Volume Calculator based on specific glass densities.
    """
    # Define precise densities (g/cm³)
    DENSITIES = {
        "boro": 2.23, "soft": 2.59, "satake": 3.55,
        "coe90": 2.57, "coe96": 2.51, "crystal": 3.10, "quartz": 2.20,
    }
    
    # Get the specific density or fallback to 2.50
    density = DENSITIES.get(glass_type, 2.50)

    units = data.get("units")
    depth = data.get("depth", 0)
    
    # Normalize to Centimeters (1 inch = 2.54 cm)
    scale = 2.54 if units == "inches" else 1.0
    depth_cm = depth * scale
    volume_cm3 = 0.0

    if shape == "cylinder":
        diameter = data.get("diameter", 0) * scale
        radius = diameter / 2
        # V = π * r² * h
        volume_cm3 = math.pi * (radius ** 2) * depth_cm
        
    elif shape == "rectangle":
        length = data.get("length", 0) * scale
        width = data.get("width", 0) * scale
        # V = l * w * h
        volume_cm3 = length * width * depth_cm

    # Apply the specific density
    weight_grams = volume_cm3 * density
    
    # Apply dynamic waste factor (e.g., 15% becomes 1.15)
    waste_multiplier = 1 + (waste_factor / 100.0)
    
    return {
        "volume_cc": round(volume_cm3, 2),
        "weight_g": round(weight_grams, 1),
        "weight_oz": round(weight_grams / 28.3495, 2),
        "weight_kg": round(weight_grams / 1000, 3),
        "glass_needed": round(weight_grams * waste_multiplier, 1),
        "density_used": density,
        "waste_percent": waste_factor
    }

def generate_kiln_schedule(brand, project, thickness):
    """
    Generates a 5-step firing schedule based on glass brand, project type, and layers.
    """
    # 1. Define Base Temperatures (Fahrenheit)
    glass_specs = {
        "bullseye": {"anneal": 900, "strain": 800},
        "verre":    {"anneal": 900, "strain": 800},
        "system96": {"anneal": 950, "strain": 850},
        "soft":     {"anneal": 960, "strain": 840},
        "boro":     {"anneal": 1050, "strain": 950},
    }
    
    specs = glass_specs.get(brand, glass_specs["bullseye"])
    anneal_temp = specs["anneal"]
    strain_point = specs["strain"]
    
    if brand == "boro":
        process_temps = {
            "full_fuse": 1650,
            "contour_fuse": 1575,
            "tack_fuse": 1500,
            "slump": 1300,
            "fire_polish": 1375,
        }
    else:
        process_temps = {
            "full_fuse": 1490,
            "contour_fuse": 1410,
            "tack_fuse": 1350,
            "slump": 1225,
            "fire_polish": 1325,
        }
        
    top_temp = process_temps.get(project, 1490)

    # 2. Define Rates and Holds based on Layers/Thickness
    if thickness == "multi_layer": # 3+ Layers / 9mm+
        rate_1, squeeze_hold = 150, 45
        rate_2 = 250
        anneal_hold = 120
        anneal_cool = 50
        cool_down = 100
        seg_1_name = "Bubble Squeeze"
    elif thickness == "two_layer": # 2 Layers / 6mm
        rate_1, squeeze_hold = 250, 30
        rate_2 = 400
        anneal_hold = 60
        anneal_cool = 80
        cool_down = 150
        seg_1_name = "Bubble Squeeze"
    else: # Single Layer / Standard
        rate_1, squeeze_hold = 400, 20
        rate_2 = 600
        anneal_hold = 30
        anneal_cool = 150
        cool_down = 300
        seg_1_name = "Initial Heat"

    # 3. Construct Segments
    segments = [
        {"step": 1, "name": seg_1_name, "rate": rate_1, "temp": 1225, "hold": squeeze_hold},
        {"step": 2, "name": "Process Heat", "rate": rate_2, "temp": top_temp, "hold": 10 if project in ["full_fuse", "contour_fuse"] else 20},
        {"step": 3, "name": "Rapid Cool", "rate": 9999, "temp": anneal_temp, "hold": anneal_hold},
        {"step": 4, "name": "Anneal Cool", "rate": anneal_cool, "temp": strain_point, "hold": 0},
        {"step": 5, "name": "Final Cool", "rate": cool_down, "temp": 70, "hold": 0},
    ]

    # Calculate Total Time
    total_minutes = 0
    current_temp = 70
    for seg in segments:
        dist = abs(seg["temp"] - current_temp)
        if seg["rate"] == 9999: 
            hours = 0.25 # 15 mins for crash cool
        else:
            hours = dist / seg["rate"]
        total_minutes += (hours * 60) + seg["hold"]
        current_temp = seg["temp"]

    hours = int(total_minutes // 60)
    mins = int(total_minutes % 60)

    return {
        "schedule": segments,
        "total_time": f"{hours} hours, {mins} minutes"
    }

def estimate_stained_glass_cost(w, h, pieces, glass_price, rate, user_hours, markup):
    """
    Calculates cost estimate for stained glass projects.
    """
    area_sqft = (w * h) / 144.0
    glass_cost = area_sqft * glass_price * 1.35 # 35% waste factor
    consumables_cost = pieces * 0.65

    if user_hours:
        hours = user_hours
        labor_method = "User Input"
    else:
        hours = pieces * 0.25
        labor_method = "Auto-Estimated (15m/piece)"
    
    labor_cost = hours * rate
    total_cost = glass_cost + consumables_cost + labor_cost
    
    retail_price = total_cost * markup

    return {
        "area_sqft": round(area_sqft, 2),
        "glass_cost": round(glass_cost, 2),
        "consumables_cost": round(consumables_cost, 2),
        "labor_hours": round(hours, 1),
        "labor_cost": round(labor_cost, 2),
        "labor_method": labor_method,
        "total_base_cost": round(total_cost, 2),
        "retail_price": round(retail_price, 2),
        "markup_used": markup
    }

def convert_temperature(temp, unit):
    if unit == "F":
        return {"val": (temp - 32) * 5/9, "unit": "°C", "orig": "°F"}
    else:
        return {"val": (temp * 9/5) + 32, "unit": "°F", "orig": "°C"}


def calculate_ramp_details(start, target, rate):
    if rate <= 0:
        return None
    diff = abs(target - start)
    hours_decimal = diff / rate
    hours_int = int(hours_decimal)
    minutes_int = int((hours_decimal - hours_int) * 60)
    
    return {
        "delta": round(diff, 1),
        "duration": f"{hours_int} hr {minutes_int} min",
        "total_decimal": round(hours_decimal, 2)
    }


def estimate_stained_glass_materials(w, h, pieces, method, waste_factor):
    waste_percent = 1 + (waste_factor / 100.0)
    area = w * h
    # Geometric estimation: Line_Length approx 2 * sqrt(Area * Pieces)
    estimated_line_length = 2.0 * math.sqrt(area * pieces)

    if method == "foil":
        raw_foil_inches = estimated_line_length * 2.0
        total_foil_inches = raw_foil_inches * waste_percent
        solder_needed_lbs = (estimated_line_length * 2) / 1500.0

        return {
            "material_name": "Copper Foil",
            "length_feet": round(total_foil_inches / 12, 1),
            "rolls_needed": math.ceil(total_foil_inches / 1296), # UPDATED: 36 yards * 36 inches
            "solder_lbs": round(solder_needed_lbs, 2),
            "flux_oz": round(solder_needed_lbs * 2, 1),
        }
    else: # Lead Came
        total_came_inches = estimated_line_length * waste_percent
        solder_needed_lbs = pieces * 0.01

        return {
            "material_name": "Lead Came",
            "length_feet": round(total_came_inches / 12, 1),
            "sticks_needed": math.ceil(total_came_inches / 72),
            "solder_lbs": round(solder_needed_lbs, 2),
            "putty_lbs": round(area / 144.0 * 0.5, 1),
        }

def calculate_lampwork_weight(glass_type, shape, dia_mm, length_in, qty, wall_mm=0):
    DENSITIES = {
        "boro": 2.23, "soft": 2.59, "satake": 3.55,
        "coe90": 2.57, "coe96": 2.51, "crystal": 3.10, "quartz": 2.20,
    }
    
    radius_cm = (dia_mm / 2) / 10.0
    length_cm = length_in * 2.54
    
    # Mathematical logic remains unchanged (Volume of a Cylinder/Annulus)
    if shape == "rod":
        vol_per_piece = math.pi * (radius_cm ** 2) * length_cm
    else:
        inner_radius_cm = ((dia_mm - (2 * wall_mm)) / 2) / 10.0
        vol_per_piece = math.pi * (radius_cm**2 - inner_radius_cm**2) * length_cm

    total_vol = vol_per_piece * qty
    density = DENSITIES.get(glass_type, 2.50) # Fallback to 2.50 if type not found
    total_weight_g = total_vol * density
    
    return {
        "weight_g": round(total_weight_g, 1),
        "weight_lb": round(total_weight_g / 453.592, 3), # Precise conversion factor
        "total_len_in": round(length_in * qty, 1),
        "density": density,
    }

def check_glass_reaction(type_a, type_b):
    """
    Checks for chemical reactions between two glass families.
    Returns a dictionary with result, severity, and details.
    """
    # Reaction Matrix: Define what reacts with what.
    # Key = The category, Value = List of categories it reacts with.
    REACTION_RULES = {
        'sulfur': ['copper', 'lead', 'reactive_clear', 'silver'],
        'copper': ['sulfur', 'reactive_clear', 'silver'],
        'lead': ['sulfur'],
        'reactive_clear': ['sulfur', 'copper', 'silver'],
        'silver': ['sulfur', 'copper', 'reactive_clear'],
        'none': []
    }

    # Family display names
    NAMES = {
        'sulfur': 'Sulfur/Selenium (Warm Colors)',
        'copper': 'Copper (Cool Colors)',
        'lead': 'Lead (Cranberries/Pinks)',
        'reactive_clear': 'Reactive Ice/Cloud',
        'silver': 'Silver Foil/Leaf',
        'none': 'Non-Reactive (Clears/Blacks)'
    }

    name_a = NAMES.get(type_a, type_a)
    name_b = NAMES.get(type_b, type_b)

    if type_b in REACTION_RULES.get(type_a, []):
        return {
            "status": "Reaction Detected",
            "severity": "danger",
            "message": f"{name_a} reacts with {name_b}.",
            "detail": "This combination will likely develop a dark gray or brownish line where the glasses meet.",
            "tip": "Tip: You can prevent this reaction by placing a layer of Clear glass (Non-Reactive) between these two colors."
        }
    elif type_a == type_b:
        return {
            "status": "Safe (Same Family)",
            "severity": "success",
            "message": "Both selections are from the same chemical family.",
            "detail": "Mixing glass from the same chemical family is safe."
        }
    else:
        return {
            "status": "Safe Combination",
            "severity": "success",
            "message": "These glass families typically do not react with one another.",
            "detail": ""
        }
    
def calculate_frit_medium_ratio(powder_weight, application_style):
    """
    Calculates the required medium weight and consistency profile for mixing glass powder/enamel.
    Returns a dictionary of calculated results.
    """
    # Define standard medium-to-powder ratios based on application style
    # These are industry standard guidelines for typical water-based or oil-based mediums
    RATIOS = {
        'paste': 0.15,        # 15% medium by weight (stiff paste for palette knife)
        'screen_print': 0.25, # 25% medium by weight (thick cream for silkscreen)
        'painting': 0.35,     # 35% medium by weight (fluid for brushwork)
        'airbrush': 0.50,     # 50% medium by weight (watery for spraying)
    }

    # Style display names and tooltips
    STYLE_INFO = {
        'paste': {
            'name': 'Stiff Paste (Palette Knife)',
            'desc': 'Ideal for creating texture, impasto effects, or filling deep crevices.'
        },
        'screen_print': {
            'name': 'Screen Printing (Squeegee)',
            'desc': 'Thick cream consistency. Won\'t bleed under the mesh but flows easily.'
        },
        'painting': {
            'name': 'Fluid Painting (Brush)',
            'desc': 'Smooth consistency for traditional brushwork. Should flow off the brush without dripping.'
        },
        'airbrush': {
            'name': 'Airbrush / Spraying',
            'desc': 'Watery consistency that passes through an airbrush nozzle without clogging.'
        },
    }

    ratio = RATIOS.get(application_style, 0.35) # Default to painting
    info = STYLE_INFO.get(application_style, STYLE_INFO['painting'])

    medium_weight = powder_weight * ratio
    total_weight = powder_weight + medium_weight

    # A rough conversion: 1 gram of medium is approx. 20 drops
    drops = int(medium_weight * 20)

    return {
        "powder_g": round(powder_weight, 1),
        "medium_g": round(medium_weight, 1),
        "medium_drops": drops,
        "total_g": round(total_weight, 1),
        "ratio_percent": int(ratio * 100),
        "style_name": info['name'],
        "style_desc": info['desc']
    }