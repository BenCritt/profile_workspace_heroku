import ssl
import socket
from datetime import datetime
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

        # 2) CONNECT (use context manager so the socket always closes)
        context = ssl.create_default_context()
        with context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=hostname) as conn:
            conn.settimeout(3.0)
            conn.connect((hostname, port))
            der_cert = conn.getpeercert(True)

        # 3) PARSE CERT with OpenSSL (ASN.1 / DER)
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, der_cert)

        # NotBefore/NotAfter come back like b"20250101000000Z"
        not_before = datetime.strptime(x509.get_notBefore().decode("ascii"), "%Y%m%d%H%M%SZ")
        not_after  = datetime.strptime(x509.get_notAfter().decode("ascii"),  "%Y%m%d%H%M%SZ")

        cert_info = {
            "subject": dict(x509.get_subject().get_components()),
            "issuer":  dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": not_before.isoformat() + "Z",
            "not_after":  not_after.isoformat() + "Z",
        }
        return cert_info

    except socket.timeout:
        return {"error": "Connection timed out. Please try again with a valid URL."}
    except ssl.SSLError as ssl_error:
        return {"error": f"SSL error: {ssl_error}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}
    # NOTE: no finally: conn.close() needed — the `with` block closes it
