# Core site views: homepage, all-projects listing, 404 handler, PWA manifest,
# and file-serving views (llms.txt, robots.txt, requirements.txt).
# Also includes privacy_cookies, which is a simple static render.
#
# Relative imports use ".." because this module lives inside the views/ package,
# one level below the main app directory.

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from ..decorators import trim_memory_after
import os


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

def home(request):
    return render(request, "projects/home.html")


# ---------------------------------------------------------------------------
# 404 Handler
# ---------------------------------------------------------------------------

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def view_404(request, exception):
    return render(request, "404.html", status=404)


# ---------------------------------------------------------------------------
# PWA Web Manifest
# ---------------------------------------------------------------------------

def manifest(request):
    manifest_json = {
        "short_name": "BenCritt",
        "name": "Ben Crittenden's PWA",
        "icons": [
            {
                "src": "https://www.bencritt.net/static/img/pwa/pwa-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "https://www.bencritt.net/static/img/pwa/pwa-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
        "start_url": "/",
        "display": "standalone",
        "theme_color": "#000000",
        "background_color": "#000000",
    }
    return JsonResponse(manifest_json)


# ---------------------------------------------------------------------------
# Static file-serving views
# ---------------------------------------------------------------------------

def llms_txt(request):
    llms_path = os.path.join(settings.BASE_DIR, "llms.txt")
    try:
        with open(llms_path, "r", encoding="utf-8") as f:
            return HttpResponse(f.read(), content_type="text/markdown; charset=utf-8")
    except FileNotFoundError:
        return HttpResponseNotFound("llms.txt not found")


def robots_txt(request):
    robots_txt_path = os.path.join(settings.BASE_DIR, "robots.txt")
    with open(robots_txt_path, "r") as f:
        robots_txt_content = f.read()
    return HttpResponse(robots_txt_content, content_type="text/plain")


def requirements_txt(request):
    requirements_txt_path = os.path.join(settings.BASE_DIR, "requirements.txt")
    with open(requirements_txt_path, "r") as f:
        requirements_txt_content = f.read()
    return HttpResponse(requirements_txt_content, content_type="text/plain")


# ---------------------------------------------------------------------------
# Privacy & Cookies page
# ---------------------------------------------------------------------------

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def privacy_cookies(request):
    return render(request, "privacy_cookies.html")


# ---------------------------------------------------------------------------
# All Projects listing
# ---------------------------------------------------------------------------

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def all_projects(request):
    projects_data = [
        {
            "title": "QR Code Generator",
            "url_name": "projects:qr_code_generator",
            "image": "qr-code-generator.webp",
            "description": "Easily generate QR codes with the user-friendly QR Code Generator. Whether you need a QR code for a website link, contact information, or any text, this app provides a fast and efficient solution. Simply enter your desired data, and with one click, you'll have a high-quality QR code ready to download and use. Perfect for teachers, businesses, marketers, event organizers, and individuals."
        },
        {
            "title": "Monte Carlo Simulator",
            "url_name": "projects:monte_carlo_simulator",
            "image": "monte-carlo-simulator.webp",
            "description": "Run quick what-if simulations. Set your ranges (single or dual) and an optional target, then export an easy-to-read probability chart to PDF for stakeholders."
        },
        {
            "title": "Weather Forecast App",
            "url_name": "projects:weather",
            "image": "weather.webp",
            "description": "Stay prepared with the Weather Forecast App, which provides precise and up-to-date weather information tailored to your location. By simply entering your ZIP code, you can receive detailed weather forecasts, including current conditions, daily highs and lows, humidity levels, wind speeds, and more."
        },
        {
            "title": "Grade Level Text Analyzer",
            "url_name": "projects:grade_level_analyzer",
            "image": "grade-level-text-analyzer.webp",
            "description": "Improve the readability of your content with the Grade Level Text Analyzer. This intuitive tool evaluates your text using the Flesch-Kincaid Grade Level, Gunning Fog Index, and Coleman-Liau Index, providing insights into how easily your writing can be understood by different audiences."
        },
        {
            "title": "DNS Lookup Tool",
            "url_name": "projects:dns_tool",
            "image": "dns-lookup.webp",
            "description": "Perform comprehensive DNS lookups with the DNS Lookup Tool, designed to provide quick access to vital DNS records for any domain. This tool is ideal for webmasters, network administrators, and SEO professionals who need detailed DNS information for troubleshooting, optimization, or security purposes."
        },
        {
            "title": "IP Address Lookup Tool",
            "url_name": "projects:ip_tool",
            "image": "ip-tool.webp",
            "description": "Uncover vital details about any IP address with the IP Address Lookup Tool, designed for IT professionals seeking in-depth information, including PTR (reverse DNS) records, geolocation data, ISP details, and organization information. This useful app also conducts DNS-based blacklist checks."
        },
        {
            "title": "SSL Verification Tool",
            "url_name": "projects:ssl_check",
            "image": "ssl-check.webp",
            "description": "Ensure the security and validity of your website's SSL certificate with the SSL Verification Tool. This app provides detailed information about SSL certificates, including the certificate's issuer, expiration dates, and validity period. Whether you're a website owner, developer, or security professional, this tool helps you maintain a secure online presence."
        },
        {
            "title": "Freight Carrier Safety Reporter",
            "url_name": "projects:freight_safety",
            "image": "freight-safety.webp",
            "description": "Gain critical insights into freight carrier safety and compliance with the Freight Carrier Safety Reporter. Designed for freight brokers, safety managers, and logistics professionals, this app provides essential details about motor carriers using their USDOT numbers. The tool leverages FMCSA's QCMobile API to retrieve vital safety data."
        },
        {
            "title": "SEO Head Checker",
            "url_name": "projects:seo_head_checker",
            "image": "seo-head-checker.webp",
            "description": "Uncover opportunities to enhance your website's search engine performance with the SEO Head Checker. This tool analyzes the head section of webpages, identifying the presence or absence of essential SEO elements such as title tags, meta descriptions, canonical tags, Open Graph tags, Twitter Card tags, and more."
        },
        {
            "title": "ISS Tracker",
            "url_name": "projects:iss_tracker",
            "image": "iss-tracker.webp",
            "description": "Monitor the International Space Station (ISS) in real-time with the ISS Tracker. This web-based app provides dynamic tracking of the ISS, including its current latitude, longitude, altitude, velocity, and regional position. Users can also project upcoming pass times over their location with precise timing and geolocation."
        },
        {
            "title": "XML Splitter",
            "url_name": "projects:xml_splitter",
            "image": "xml-splitter.webp",
            "description": "Convert a single, nested XML export into a clean ZIP of one-file-per-record. Many e-commerce platforms bundle orders, products, and customers into one large XML, while ERPs prefer individual XML files. Upload your source XML and the app splits it into well-formed, per-entry XML documents."
        },
        {
            "title": "Ham Radio Call Sign Lookup",
            "url_name": "projects:ham_radio_call_sign_lookup",
            "image": "ham-radio-call-sign-lookup.webp",
            "description": "Look up any U.S. amateur (ham) radio call sign to verify license status and view key details such as licensee name, class, and expiration. Designed for operators, clubs, and event coordinators, this tool provides quick identity checks before on-air contacts or during registration and logging."
        },
        {
            "title": "Font Inspector",
            "url_name": "projects:font_inspector",
            "image": "font-inspector.webp",
            "description": "Identify the fonts used on any website and where they're loaded from. The Font Inspector scans page HTML and linked stylesheets to detect local and web-hosted fonts (e.g. Google Fonts, Adobe Fonts, Font Awesome), and offers licensing guidance. Export results to CSV for design audits."
        },
        {
            "title": "Cookie Audit",
            "url_name": "projects:cookie_audit",
            "image": "cookie-audit.webp",
            "description": "Scan any public webpage to identify cookies in use and review key attributes such as domain, expiration, HttpOnly, Secure, and SameSite flags. The Cookie Audit tool distinguishes between first-party and third-party cookies, identifies how cookies are set, and displays results in a clear, audit-ready table."
        },
        {
            "title": "Stained Glass Materials Calculator",
            "url_name": "projects:stained_glass_materials",
            "image": "glass-materials.webp",
            "description": "Estimate exactly how much copper foil, lead came, solder, and flux is needed for a stained glass project based on dimensions and piece count."
        },
        {
            "title": "Glass Volume & Weight Calculator",
            "url_name": "projects:glass_volume_calculator",
            "image": "glass-calc.webp",
            "description": "Calculate the exact amount of glass needed for pot melts, casting molds, or thick fused slabs using standard glass density."
        },
        {
            "title": "Kiln Firing Schedule Generator",
            "url_name": "projects:kiln_schedule_generator",
            "image": "kiln-schedule.webp",
            "description": "Generate safe firing schedules for fused glass projects (COE 90, 96, 104, 33). Automatically adjusts ramp rates for Borosilicate, Soft Glass, and Standard fusing."
        },
        {
            "title": "Kiln Controller Utilities",
            "url_name": "projects:kiln_controller_utils",
            "image": "kiln-utils.webp",
            "description": "Quick math helpers for programming digital kiln controllers, including temperature conversion (F/C) and ramp segment duration calculations."
        },
        {
            "title": "Stained Glass Cost Estimator",
            "url_name": "projects:stained_glass_cost_estimator",
            "image": "stained-glass-calc.webp",
            "description": "Calculate a fair price for stained glass art by factoring in hidden costs like waste glass, solder, foil, and labor time."
        },
        {
            "title": "Lampwork Glass Calculator",
            "url_name": "projects:lampwork_materials",
            "image": "lampwork-glass-calculator.webp",
            "description": "Calculate the precise weight of glass stock needed for your next project. This calculator supports Borosilicate (COE 33), Soft Glass (COE 104), Satake, and Lead Crystal. Simply input the dimensions of your solid rods or hollow tubing to instantly get the required weight in grams or pounds. Essential for lampworkers, glassblowers, and inventory planning."
        },
        {
            "title": "Freight Class Calculator",
            "url_name": "projects:freight_class_calculator",
            "image": "freight-class-calculator.webp",
            "description": "Avoid costly re-bills by accurately estimating the NMFC Freight Class for LTL shipments. Simply input dimensions and weight to calculate density (PCF) and determine the correct class based on the standard density scale."
        },
        {
            "title": "Fuel Surcharge Calculator",
            "url_name": "projects:fuel_surcharge_calculator",
            "image": "fuel-surcharge-calculator.webp",
            "description": "Instantly calculate the Fuel Surcharge (FSC) for truckload shipments. Input your trip miles, current diesel price, and base peg to generate the exact surcharge amount per mile and total trip cost. Essential for freight brokers and owner-operators negotiating rates."
        },
        {
            "title": "HOS Trip Planner",
            "url_name": "projects:hos_trip_planner",
            "image": "hos-trip-planner.webp",
            "description": "Plan realistic truck trips compliant with FMCSA Hours of Service (HOS) rules. Input your miles and start time to generate a step-by-step itinerary that automatically calculates mandatory 30-minute breaks and 10-hour daily resets."
        },
        {
            "title": "Glass Reaction Checker",
            "url_name": "projects:glass_reaction_checker",
            "image": "glass-reaction-checker.webp",
            "description": "Prevent accidental discoloration and dark lines in your fused glass projects. This tool checks for chemical reactions between different glass families (Sulfur, Copper, Lead, and Silver) so you can plan your glass combinations safely."
        },
        {
            "title": "Enamel & Frit Mixing Calculator",
            "url_name": "projects:frit_mixing_calculator",
            "image": "frit-mixing-calculator.webp",
            "description": "Stop guessing your mix. Calculate the exact amount of liquid medium needed for your glass powders and enamels based on your application style (brush painting, screen printing, palette knife, or airbrush)."
        },
        {
            "title": "Circle & Oval Cutter Calculator",
            "url_name": "projects:circle_cutter_calculator",
            "image": "circle-cutter-calculator.webp",
            "description": "Calculate the exact radius setting for your glass circle cutter rig. This tool factors in the cutting wheel offset and your desired edge-grinding allowance to prevent ruined glass."
        },
        {
            "title": "FMCSA Tie-Down Calculator",
            "url_name": "projects:tie_down_calculator",
            "image": "tie-down-calculator.webp",
            "description": "Stay compliant with FMCSA regulations. Calculate the minimum number of tie-downs required for your cargo based on weight, length, and Working Load Limit (WLL). This tool automatically applies the stricter of the § 393.102 and § 393.106 rules."
        },
        {
            "title": "Cost Per Mile (CPM) Calculator",
            "url_name": "projects:cost_per_mile_calculator",
            "image": "cost-per-mile-calculator.webp",
            "description": "Calculate your true Break-Even Rate Per Mile. This owner-operator CPM calculator factors in fixed costs (insurance, truck payments) and variable costs (fuel, tires, driver pay) to help you negotiate profitable freight rates."
        },
        {
            "title": "LTL Linear Foot & Density Visualizer",
            "url_name": "projects:linear_foot_calculator",
            "image": "linear-foot-calculator.webp",
            "description": "Avoid massive LTL rate hikes. Calculate exactly how many linear feet your shipment will take up in a trailer and check if you are violating the 'Linear Foot Rule' density limits."
        },
        {
            "title": "Detention & Layover Fee Calculator",
            "url_name": "projects:detention_layover_fee_calculator",
            "image": "detention-layover-fee-calculator.webp",
            "description": "Stop arguing over waiting time. Calculate exact billable detention hours and fees by subtracting standard free time from your total facility time."
        },
        {
            "title": "Warehouse Pallet Storage Estimator",
            "url_name": "projects:warehouse_storage_calculator",
            "image": "warehouse-storage-calculator.webp",
            "description": "Calculate the exact maximum pallet capacity for any warehouse footprint. This tool automatically tests both standard and rotated pallet orientations to maximize your square footage."
        },
        {
            "title": "Freight Partial & Volume LTL Rate Calculator",
            "url_name": "projects:partial_rate_calculator",
            "image": "partial-rate-calculator.webp",
            "description": "Calculate Volume LTL and Partial Truckload estimates based on exact trailer utilization, ZIP-to-ZIP road distance, and custom brokerage margins. Essential for determining if a large shipment is cheaper to move via LTL or dedicated Full Truckload (FTL)."
        },
        {
            "title": "Deadhead Mileage & Cost Calculator",
            "url_name": "projects:deadhead_calculator",
            "image": "deadhead-calculator.webp",
            "description": "Calculate the true cost of running empty using exact "
                    "Google Maps road miles and your all-in operating CPM. "
                    "Optionally plug in a load's offered rate and delivery "
                    "ZIP to instantly see whether that load is profitable "
                    "after deadhead, your effective rate per mile, deadhead "
                    "ratio, and break-even minimum."
        },
        {
            "title": "Multi-Stop Route Mileage Splitter",
            "url_name": "projects:multi_stop_splitter",
            "image": "multi-stop-mileage-splitter.webp",
            "description": "Split any multi-stop freight route into individual "
                    "leg mileages using exact Google Maps road miles. "
                    "See per-leg distances, percentage of total, cumulative "
                    "miles, and optional stop-off charges for invoicing."
        },
        {
            "title": "Freight Lane Rate-Per-Mile Analyzer",
            "url_name": "projects:lane_rate_analyzer",
            "image": "freight-lane-rate-analyzer.webp",
            "description": "Analyze any quoted freight rate against exact "
                    "Google Maps road miles. See effective Rate Per Mile "
                    "(RPM), rate context against market benchmarks, "
                    "optional all-in RPM with fuel surcharge, and margin "
                    "analysis against your operating cost per mile."
        },
        {
            "title": "Freight Margin & Gross Profit Calculator",
            "url_name": "projects:freight_margin_calculator",
            "image": "freight-margin-calculator.webp",
            "description": "Calculate brokerage gross profit and margin on "
                    "any freight load. Enter customer and carrier rates, "
                    "optional FSC and accessorials on each side, and "
                    "optional lane ZIPs for per-mile profitability metrics."
        },
        {
            "title": "Band Plan Checker",
            "url_name": "projects:band_plan_checker",
            "image": "band-plan-checker.webp",
            "description": "Check any US amateur radio band plan against current FCC allocations and restrictions."
        },
        {
            "title": "Repeater Finder",
            "url_name": "projects:repeater_finder",
            "image": "repeater-finder.webp",
            "description": "Find nearby amateur radio repeaters based on your location."
        },
        {
            "title": "Antenna Length Calculator",
            "url_name": "projects:antenna_calculator",
            "image": "antenna-length-calculator.webp",
            "description": "Calculate the length of various types of antennas based on frequency."
        },
        {
            "title": "Grid Square Converter",
            "url_name": "projects:grid_square_converter",
            "image": "grid-square-converter.webp",
            "description": "Convert between grid square coordinates and latitude/longitude."
        },
        {
            "title": "RF Exposure Calculator",
            "url_name": "projects:rf_exposure_calculator",
            "image": "rf-exposure-calculator.webp",
            "description": "Evaluate your amateur radio station's compliance with FCC Maximum Permissible Exposure (MPE) limits per OET Bulletin 65. Required by FCC Part 97.13(c)(1) for all amateur stations."
        },
        {
            "title": "Coax Cable Loss Calculator",
            "url_name": "projects:coax_cable_loss_calculator",
            "image": "coax-cable-loss-calculator.webp",
            "description": "Calculate feed line attenuation, SWR mismatch loss, and power delivered to the antenna for RG-58, RG-213, LMR-400, and more."
        },
        {
            "title": "Subnet / CIDR Calculator",
            "url_name": "projects:subnet_calculator",
            "image": "subnet-calculator.webp",
            "description": "Calculate network ranges, broadcast addresses, and wildcard masks. Simply enter an IP and CIDR (e.g., /24) to get a breakdown of usable hosts, binary netmasks, and IP classes."
        },
        {
            "title": "SPF, DKIM & DMARC Validator",
            "url_name": "projects:email_auth_validator",
            "image": "email-auth-validator.webp",
            "description": "Verify your email security configuration. Check SPF records for authorized senders, DMARC policies for compliance instructions, and DKIM public keys to ensure your emails are properly signed."
        },
        {
            "title": "WHOIS Lookup Tool",
            "url_name": "projects:whois_lookup",
            "image": "whois-lookup.webp",
            "description": "Perform domain registration lookups to find ownership details, expiration dates, registrars, and nameservers. Includes a safe timeout to ensure fast performance."
        },
        {
            "title": "HTTP Header Inspector",
            "url_name": "projects:http_header_inspector",
            "image": "http-header-inspector.webp",
            "description": "Inspect the HTTP response headers of any website. Reveal server software, caching policies, cookies, and security headers like HSTS and CSP."
        },
        {
            "title": "Redirect Chain Checker",
            "url_name": "projects:redirect_checker",
            "image": "redirect-checker.webp",
            "description": "Trace the full path of HTTP redirects for any URL. Detect redirect loops, identify temporary vs. permanent redirects (301, 302, 307, 308), and analyze hop-by-hop latency and server headers."
        },
        {
            "title": "Structured Data / JSON-LD Validator",
            "url_name": "projects:jsonld_validator",
            "image": "jsonld-validator.webp",
            "description": "Enter any URL to extract and validate its JSON-LD structured data. Checks for valid JSON syntax, required and recommended schema.org properties, and common SEO issues."
        },
        {
            "title": "Robots.txt Analyzer",
            "url_name": "projects:robots_analyzer",
            "image": "robots-analyzer.webp",
            "description": "Fetch and parse any domain's robots.txt file. View user-agent groups, allow/disallow rules, sitemap references, and crawl-delay directives. Optionally test a specific path to see which bots can access it."
        },
        {
            "title": "Satellite Pass Predictor",
            "url_name": "projects:satellite_pass_predictor",
            "image": "satellite-pass-predictor.webp",
            "description": "Predict upcoming visible passes for 25+ satellites, including the ISS, Hubble, Landsat, and amateur radio transponders. Calculates rise/set times in your local timezone."
        },
        {
            "title": "AI Token & API Cost Estimator",
            "url_name": "projects:ai_api_cost_estimator",
            "image": "ai-api-cost-estimator.webp",
            "description": "Paste any text, prompt, or code snippet to calculate its exact token count and compare API costs across leading models — including GPT-5.2, Claude Sonnet/Opus 4.6, and Gemini 3.1 Pro. Estimates both input and output costs based on your selected task type."
        },
        {
            "title": "Cron Expression Builder & Parser",
            "url_name": "projects:cron_builder",
            "image": "cron-builder.webp",
            "description": "Validate any 5-field cron expression and get a plain-English description of its schedule. Preview the next N run times in any timezone, explore a one-click preset library, and review a field-by-field breakdown with valid ranges."
        },
        {
            "title": "Unix Timestamp Converter",
            "url_name": "projects:timestamp_converter",
            "image": "unix-timestamp-converter.webp",
            "description": "Convert Unix epoch timestamps to human-readable datetimes — and back. Auto-detects seconds vs. milliseconds, shows results across all major timezones, outputs ISO 8601 format, and includes a live epoch ticker."
        },
        {
            "title": "Open Graph & Social Card Previewer",
            "url_name": "projects:og_previewer",
            "image": "og-previewer.webp",
            "description": "Preview how your page appears when shared on Google, Twitter/X, Facebook, and LinkedIn. Audits all Open Graph, Twitter Card, and core meta tags in one place with a visual health score."
        },
        {
            "title": "Lunar Phase Calendar",
            "url_name": "projects:lunar_phase_calendar",
            "image": "lunar-phase-calendar.webp",
            "description": "Monthly moon phase calendar with illumination percentages, rise/set times by ZIP code, and countdowns to the next New Moon, First Quarter, Full Moon, and Last Quarter."
        },
        {
            "title": "Night Sky Planner",
            "url_name": "projects:night_sky_planner",
            "image": "night-sky-planner.webp",
            "description": "Plan your stargazing session tonight. Get astronomical twilight times, dark sky window, moon phase, visible satellite passes, and an overall stargazing quality rating for your location."
        },
    ]

    context = {
        "projects": projects_data
    }

    return render(request, "projects/all_projects.html", context)