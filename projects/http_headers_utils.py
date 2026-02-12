import requests

def fetch_http_headers(url: str):
    """
    Fetches the HTTP response headers for a given URL.
    Uses stream=True to avoid downloading the response body.
    """
    # Ensure scheme is present
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # User Agent is important; some servers block requests without one.
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) BenCritt-Header-Inspector/1.0'
        }
        
        # stream=True initiates the request but doesn't download the content
        # timeout=5 ensures we don't hang the Heroku worker
        response = requests.get(url, headers=headers, stream=True, timeout=5)
        
        # Explicitly close to release the connection back to the pool immediately
        response.close()
        
        return {
            "status_code": response.status_code,
            "reason": response.reason,
            "final_url": response.url,
            "headers": dict(response.headers),
            "protocol": "HTTPS" if response.url.startswith("https") else "HTTP"
        }

    except requests.Timeout:
        return {"error": "Connection timed out (5s limit). The server took too long to respond."}
    except requests.ConnectionError:
        return {"error": "Connection failed. Please check the domain name and try again."}
    except requests.TooManyRedirects:
        return {"error": "Too many redirects. The URL entered resulted in an infinite loop."}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}