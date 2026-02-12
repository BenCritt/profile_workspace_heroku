import dns.resolver

def get_txt_record(hostname):
    """
    Helper to fetch all TXT records for a hostname.
    Returns a list of strings.
    """
    try:
        answers = dns.resolver.resolve(hostname, 'TXT')
        results = []
        for rdata in answers:
            # dnspython returns bytes for TXT strings; join them and decode
            txt_string = b''.join(rdata.strings).decode('utf-8')
            results.append(txt_string)
        return results
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        return []
    except Exception:
        return []

def analyze_spf(domain):
    """
    Finds and analyzes the SPF record on the root domain.
    """
    records = get_txt_record(domain)
    spf_record = next((r for r in records if r.lower().startswith('v=spf1')), None)

    if not spf_record:
        return {"status": "missing", "record": None, "message": "No SPF record found."}

    # Basic Analysis
    analysis = "Valid"
    details = "Standard SPF record."
    
    if "+all" in spf_record:
        analysis = "Insecure"
        details = "The '+all' mechanism allows ANY server to send email on your behalf."
    elif "-all" in spf_record:
        analysis = "Strict"
        details = "Hard Fail: Unauthorized emails should be rejected (-all)."
    elif "~all" in spf_record:
        analysis = "Soft Fail"
        details = "Soft Fail: Unauthorized emails may be marked as spam (~all)."
    elif "?all" in spf_record:
        analysis = "Neutral"
        details = "Neutral: No policy on unauthorized emails (?all)."

    return {
        "status": "found",
        "record": spf_record,
        "analysis": analysis,
        "details": details
    }

def analyze_dmarc(domain):
    """
    Finds and analyzes the DMARC record at _dmarc.domain.com.
    """
    dmarc_host = f"_dmarc.{domain}"
    records = get_txt_record(dmarc_host)
    dmarc_record = next((r for r in records if r.lower().startswith('v=dmarc1')), None)

    if not dmarc_record:
        return {"status": "missing", "record": None, "message": "No DMARC record found at _dmarc." + domain}

    # Parse tags roughly
    tags = {}
    parts = dmarc_record.split(';')
    for part in parts:
        if '=' in part:
            k, v = part.strip().split('=', 1)
            tags[k.lower()] = v

    policy = tags.get('p', 'none')
    
    if policy == 'reject':
        analysis = "Strict (Reject)"
        details = "Emails failing authentication are rejected."
    elif policy == 'quarantine':
        analysis = "Protective (Quarantine)"
        details = "Emails failing authentication are sent to spam."
    else:
        analysis = "Monitoring (None)"
        details = "Policy is set to 'none'. No action is taken against failing emails."

    return {
        "status": "found",
        "record": dmarc_record,
        "analysis": analysis,
        "details": details,
        "policy": policy
    }

def analyze_dkim(domain, selector):
    """
    Finds DKIM record at selector._domainkey.domain.com.
    """
    if not selector:
        return {"status": "skipped", "message": "No selector provided."}

    dkim_host = f"{selector}._domainkey.{domain}"
    records = get_txt_record(dkim_host)
    dkim_record = next((r for r in records if "k=" in r or "v=DKIM1" in r), None)

    if not dkim_record:
        # Fallback: sometimes it's just a raw key without v=DKIM1
        if records:
            dkim_record = records[0]
        else:
            return {"status": "missing", "record": None, "message": f"No record found at {dkim_host}"}

    return {
        "status": "found",
        "record": dkim_record,
        "host": dkim_host,
        "analysis": "Public Key Found",
        "details": "A public key is published at this selector."
    }

def validate_email_auth(domain, selector=None):
    return {
        "spf": analyze_spf(domain),
        "dmarc": analyze_dmarc(domain),
        "dkim": analyze_dkim(domain, selector)
    }