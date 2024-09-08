import ssl
import socket
from OpenSSL import crypto
from urllib.parse import urlparse


def verify_ssl(url):
    try:
        # Parse URL to get the hostname
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Create an SSL context and wrap a socket
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET), server_hostname=hostname
        )

        # Set a timeout for the connection
        conn.settimeout(3.0)
        conn.connect((hostname, 443))

        # Retrieve the certificate from the server
        cert = conn.getpeercert(True)
        conn.close()

        # Load the certificate using pyOpenSSL
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert)

        # Extract certificate details
        cert_info = {
            "subject": dict(x509.get_subject().get_components()),
            "issuer": dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": x509.get_notBefore().decode("utf-8"),
            "not_after": x509.get_notAfter().decode("utf-8"),
        }

        return cert_info

    except Exception as e:
        return {"error": str(e)}