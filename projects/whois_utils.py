import whois
import concurrent.futures
from datetime import datetime

def format_value(value):
    """
    Helper to clean up WHOIS values which can be lists, strings, or dates.
    """
    if value is None:
        return "N/A"
    
    if isinstance(value, list):
        # Filter Nones and join
        items = [str(v) for v in value if v]
        return ", ".join(items)
    
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
        
    return str(value)

def perform_whois_lookup(domain: str, timeout: int = 10):
    """
    Performs a WHOIS lookup with a strict timeout to prevent Heroku H12 errors.
    Returns a dictionary of results or raises an exception.
    """
    def _do_lookup():
        # python-whois performs the network socket call here
        return whois.whois(domain)

    # Use a ThreadPoolExecutor to enforce a timeout
    # This prevents the view from hanging forever if the WHOIS server is unresponsive
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(_do_lookup)
            w = future.result(timeout=timeout)
            
            # Normalize the data for the template
            return {
                "domain_name": format_value(w.domain_name),
                "registrar": format_value(w.registrar),
                "whois_server": format_value(w.whois_server),
                "creation_date": format_value(w.creation_date),
                "expiration_date": format_value(w.expiration_date),
                "updated_date": format_value(w.updated_date),
                "name_servers": format_value(w.name_servers),
                "status": format_value(w.status),
                "emails": format_value(w.emails),
                "org": format_value(w.org),
                "raw_text": w.text if w.text else "Raw text unavailable."
            }
        except concurrent.futures.TimeoutError:
            return {"error": "The lookup timed out. The registrar's server may be slow or blocking requests."}
        except Exception as e:
            return {"error": f"Lookup failed: {str(e)}"}