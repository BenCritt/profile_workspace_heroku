import ssl
import socket
from OpenSSL import crypto
from datetime import datetime
from urllib.parse import urlparse

def verify_ssl(url):
    try:
        # Parse URL to get the hostname.
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Check if hostname exists.
        if not hostname:
            return {
                "error": "Invalid URL. Please ensure the URL is correctly formatted."
            }

        # Create an SSL context and wrap a socket.
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET), server_hostname=hostname
        )

        # Set a timeout for the connection.
        conn.settimeout(3.0)
        conn.connect((hostname, 443))

        # Retrieve the certificate from the server.
        cert = conn.getpeercert(True)

        # Always close the connection.
        conn.close()

        # Load the certificate using pyOpenSSL.
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert)

        # Convert ASN.1 time format to datetime.
        not_before = datetime.strptime(
            x509.get_notBefore().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )
        not_after = datetime.strptime(
            x509.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )

        # Extract certificate details.
        cert_info = {
            "subject": dict(x509.get_subject().get_components()),
            "issuer": dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": not_before,
            "not_after": not_after,
        }

        return cert_info

    # Error handling.
    except socket.timeout:
        return {"error": "Connection timed out. Please try again with a valid URL."}
    except ssl.SSLError as ssl_error:
        return {"error": f"SSL error: {str(ssl_error)}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}
    finally:
        # Ensure the connection is closed if it wasn't already.
        try:
            conn.close()
        except Exception:
            pass
