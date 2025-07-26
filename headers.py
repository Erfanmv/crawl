# headers.py
"""HTTP headers pool used by the crawler."""

headers_list = [
    {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9,fa;q=0.8,tr;q=0.7,ru;q=0.6",
        # Replace with a valid token if required by the API
        "authorization": "Bearer YOUR_BEARER_TOKEN",
        "referer": "https://snappfood.ir/grocery/menu/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
    }
]

# Add more dictionaries to this list if you want to rotate headers.
