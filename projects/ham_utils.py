import requests

CALLOOK_URL = "https://callook.info/{}/json"
HAMDB_URL   = "https://api.hamdb.org/{}/json/djangoapp"

def query_callook(callsign, timeout=6):
    return requests.get(CALLOOK_URL.format(callsign), timeout=timeout).json()

def query_hamdb(callsign, timeout=6):
    return requests.get(HAMDB_URL.format(callsign), timeout=timeout).json()