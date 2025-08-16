import requests
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import csv
import gc
from django.core.cache import cache

# This variable is used to limit the number of URLs processed by SEO Head Checker.
sitemap_limit = 25

def fetch_sitemap_urls(sitemap_url):
    """
    Fetches all URLs listed in a sitemap or processes a single webpage URL.

    - Sends an HTTP GET request to the sitemap URL or webpage URL.
    - If the URL points to a sitemap, parses the sitemap content to extract all <loc> tags.
    - If the URL points to a webpage, validates whether it has a valid <head> section.

    Args:
        sitemap_url (str): The URL of the sitemap or webpage to fetch.

    Returns:
        list: A list of URLs (str) extracted from the sitemap or containing the single webpage URL.

    Raises:
        ValueError: If the URL is invalid, inaccessible, or cannot be processed.
        Exception: If the sitemap content cannot be parsed.
    """
    headers = {
        # Identifies my app so admins know who is crawling their website.
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        # Tells websites what the app is looking for.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    try:
        # Send an HTTP GET request to fetch the sitemap or webpage content with a custom User-Agent.
        response = requests.get(sitemap_url, headers=headers, timeout=10)
        response.raise_for_status()  # Check for HTTP errors (e.g., 404, 500).
    except requests.exceptions.Timeout:
        raise ValueError("The request timed out. Please try again later.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Failed to connect to the URL. Please check the URL.")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"HTTP error occurred: {e}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"An error occurred while fetching the URL: {e}")

    # Check the content type of the response to determine if it's a sitemap
    content_type = response.headers.get("Content-Type", "")
    if "xml" in content_type or sitemap_url.endswith(".xml"):
        try:
            # Parse the sitemap content as XML using BeautifulSoup.
            soup = BeautifulSoup(response.content, "lxml-xml")
            # Extract and return all URLs found in <loc> tags.
            urls = [loc.text for loc in soup.find_all("loc")]
            if not urls:
                raise ValueError("The provided sitemap is empty or invalid.")
            return urls
        except Exception as e:
            raise ValueError(
                f"Failed to parse the sitemap. Ensure it's a valid XML file. Error: {e}"
            )
    else:
        # If not a sitemap, assume it's a single webpage URL
        return [sitemap_url]


def process_sitemap_urls(urls, max_workers=5, task_id=None):
    """
    Processes URLs from a sitemap in parallel, up to a specified limit.

    - Utilizes a thread pool to process URLs concurrently for improved efficiency.
    - Updates task progress in the cache if a task ID is provided.
    - Returns the results of processing each URL.

    Args:
        urls (list): List of URLs to process.
        max_workers (int, optional): Number of threads to use for concurrent processing. Set to 5.
        task_id (str, optional): Unique identifier for tracking progress in the cache. Defaults to None.

    Returns:
        list: A list of results from processing each URL.
    """
    # Ensure the global sitemap_limit variable is accessible.
    global sitemap_limit

    # Initialize an empty list to store the results.
    results = []

    # Determine the actual number of URLs to process (limited by sitemap_limit).
    total_urls = min(len(urls), sitemap_limit)

    # Use a thread pool to process URLs concurrently.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Process URLs in parallel and enumerate results to track progress.
        for i, result in enumerate(
            executor.map(process_single_url, urls[:sitemap_limit])
        ):
            # Append the result of processing each URL to the results list.
            results.append(result)

            # If a task ID is provided, update the progress in the cache.
            if task_id:
                cache.set(
                    task_id,
                    {
                        # Indicate that the task is still processing.
                        "status": "processing",
                        # Calculate progress percentage.
                        "progress": int((i + 1) / total_urls * 100),
                    },
                    # Cache entry expiration time (30 minutes).
                    timeout=1800,
                )
    # Explicit cleanup.
    del urls
    gc.collect()

    # Return the list of results after processing all URLs.
    return results


def process_single_url(url):
    """
    Processes a single URL to extract and check the presence of SEO-related elements in the <head> section.

    Args:
        url (str): The URL to process.

    Returns:
        dict: A dictionary containing the URL, status, and results for SEO element checks.
    """
    headers = {
        # Identifies my app so admins know who is crawling their website.
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        # Tells websites what the app is looking for.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    soup = None  # Initialize soup to avoid uninitialized reference in finally block

    try:
        # Send an HTTP GET request to the URL with a 10-second timeout.
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Check for HTTP errors (e.g., 404, 500).
    except requests.exceptions.Timeout:
        return {"URL": url, "Status": "Error: Request timed out"}
    except requests.exceptions.ConnectionError:
        return {"URL": url, "Status": "Error: Failed to connect to the URL"}
    except requests.exceptions.HTTPError as e:
        return {"URL": url, "Status": f"HTTP error occurred: {e}"}
    except requests.exceptions.RequestException as e:
        return {"URL": url, "Status": f"Request error: {e}"}

    try:
        # Parse the HTML content of the response using BeautifulSoup.
        soup = BeautifulSoup(response.text, "html.parser")
        # Extract the <head> section from the parsed HTML.
        head = soup.find("head")
        if not head:
            return {"URL": url, "Status": "No <head> section"}

        # Helper function to check for the presence of specific tags in the <head>.
        def is_present(tag_name, **attrs):
            return "Present" if head.find(tag_name, attrs=attrs) else "Missing"

        # Count structured data scripts in the <head>.
        structured_data_scripts = head.find_all("script", type="application/ld+json")
        structured_data_count = (
            len(structured_data_scripts) if structured_data_scripts else 0
        )

        # Open Graph and Twitter Tags
        open_graph_present = bool(
            head.find("meta", attrs={"property": lambda p: p and p.startswith("og:")})
        )
        twitter_card_present = bool(
            head.find("meta", attrs={"name": lambda p: p and p.startswith("twitter:")})
        )

        # Return the results dictionary.
        return {
            "URL": url,
            "Status": "Success",
            "Title Tag": "Present" if head.title else "Missing",
            "Meta Description": is_present("meta", name="description"),
            "Canonical Tag": is_present("link", rel="canonical"),
            "Meta Robots Tag": is_present("meta", name="robots"),
            "Open Graph Tags": "Present" if open_graph_present else "Missing",
            "Twitter Card Tags": "Present" if twitter_card_present else "Missing",
            "Hreflang Tags": (
                "Present"
                if head.find("link", rel="alternate", hreflang=True)
                else "Missing"
            ),
            "Structured Data": (
                f"Present ({structured_data_count} scripts)"
                if structured_data_count > 0
                else "Missing"
            ),
            "Charset Declaration": is_present("meta", charset=True),
            "Viewport Tag": is_present("meta", name="viewport"),
            "Favicon": is_present("link", rel="icon"),
        }
    except Exception as e:
        # Return a dictionary indicating an error occurred and include the exception message.
        return {"URL": url, "Status": f"Error while processing content: {e}"}
    finally:
        # Safely release memory for the parsed HTML.
        if soup:
            del soup
        gc.collect()  # Force garbage collection


def save_results_to_csv(results, task_id):
    """
    Saves the results of sitemap processing to a CSV file.

    - Creates a CSV file named using the task ID to ensure uniqueness.
    - Writes the results, including headers and data rows, to the CSV file.
    - Returns the file path for further use (e.g., download or cleanup).

    Args:
        results (list): A list of dictionaries containing the processing results for each URL.
        task_id (str): A unique identifier for the task, used to name the CSV file.

    Returns:
        str: The file path of the generated CSV file.
    """
    # Define the file path using the task ID for uniqueness.
    file_path = f"seo_report_{task_id}.csv"

    # Open the file in write mode with UTF-8 encoding.
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:

        # Define the field names (column headers) for the CSV file.
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                # The URL of the processed page.
                "URL",
                # The processing status (e.g., Success, Error).
                "Status",
                # Presence of the <title> tag.
                "Title Tag",
                # Presence of the meta description.
                "Meta Description",
                # Presence of the canonical link tag.
                "Canonical Tag",
                # Presence of the meta robots tag.
                "Meta Robots Tag",
                # Presence of Open Graph meta tags.
                "Open Graph Tags",
                # Presence of Twitter card meta tags.
                "Twitter Card Tags",
                # Presence of hreflang link tags.
                "Hreflang Tags",
                # Presence of structured data (JSON-LD scripts).
                "Structured Data",
                # Presence of the charset declaration.
                "Charset Declaration",
                # Presence of the viewport meta tag.
                "Viewport Tag",
                # Presence of the favicon link tag.
                "Favicon",
            ],
        )

        # Write the column headers to the CSV file.
        writer.writeheader()

        # Write the rows of data to the CSV file.
        writer.writerows(results)

    # Return the file path of the generated CSV file.
    return file_path