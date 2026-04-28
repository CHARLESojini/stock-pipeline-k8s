"""
API configuration and logging setup.

Reads Alpha Vantage / RapidAPI credentials from environment variables
(injected via K8s Secret in production).
"""

import os
import logging

# Try to load .env file for local development; ignore if not present (K8s case)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

BASEURL = "alpha-vantage.p.rapidapi.com"
url = f"https://{BASEURL}/query"

headers = {
    "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"),
    "x-rapidapi-host": BASEURL,
    "Content-Type": "application/json"
}