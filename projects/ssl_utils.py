import ssl
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

def verify_ssl(url):
    from OpenSSL import crypto
    try:
        # 1) Parse and validate input
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        if not hostname:
            return {"error": "Invalid URL. Please ensure the URL is correctly formatted."}
        port = parsed_url.port or 443

        # 2) CONNECT (context manager auto-closes the socket)
        context = ssl.create_default_context()
        with context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=hostname) as conn:
            conn.settimeout(3.0)
            conn.connect((hostname, port))
            der_cert = conn.getpeercert(True)

        # 3) PARSE CERT (ASN.1 / DER)
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, der_cert)

        # Helpers: decode bytes to str for template friendliness
        def _b2s_dict(items):
            return {
                (k.decode("utf-8", "replace") if isinstance(k, (bytes, bytearray)) else str(k)):
                (v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else str(v))
                for k, v in items
            }

        nb_raw = x509.get_notBefore().decode("ascii")  # e.g. "20250101000000Z"
        na_raw = x509.get_notAfter().decode("ascii")

        # Make them timezone-aware UTC datetimes so {{ result.not_before|date:"..." }} works
        not_before = datetime.strptime(nb_raw, "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
        not_after  = datetime.strptime(na_raw, "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)

        cert_info = {
            "subject": _b2s_dict(x509.get_subject().get_components()),
            "issuer":  _b2s_dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": not_before,   # <-- datetime, not string
            "not_after":  not_after,    # <-- datetime, not string
        }
        return cert_info

    except socket.timeout:
        return {"error": "Connection timed out. Please try again with a valid URL."}
    except ssl.SSLError as ssl_error:
        return {"error": f"SSL error: {ssl_error}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}
