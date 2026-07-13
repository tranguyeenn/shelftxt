from __future__ import annotations

from urllib.parse import urlparse


PUBLISHER_DOMAINS = {
    "bloomsbury.com",
    "cambridge.org",
    "chroniclebooks.com",
    "hachettebookgroup.com",
    "harpercollins.com",
    "macmillan.com",
    "mitpress.mit.edu",
    "penguinrandomhouse.com",
    "penguin.co.uk",
    "princeton.edu",
    "simonandschuster.com",
    "torpublishinggroup.com",
    "ucpress.edu",
    "upress.umn.edu",
    "wiley.com",
    "wwnorton.com",
    "yupress.yale.edu",
}

RETAILER_DOMAINS = {
    "barnesandnoble.com",
    "bookshop.org",
    "booksamillion.com",
    "indiebound.org",
    "waterstones.com",
}

BLOCKED_DOMAINS = {
    "amazon.com",
    "amazon.co.uk",
    "goodreads.com",
    "google.com",
    "bing.com",
}


def normalize_domain(url_or_domain: str) -> str:
    parsed = urlparse(url_or_domain)
    host = parsed.netloc or url_or_domain
    return host.casefold().split("@")[-1].split(":")[0].removeprefix("www.")


def _matches(domain: str, candidates: set[str]) -> bool:
    return domain in candidates or any(domain.endswith(f".{candidate}") for candidate in candidates)


def is_publisher_domain(domain: str) -> bool:
    return _matches(normalize_domain(domain), PUBLISHER_DOMAINS)


def is_retailer_domain(domain: str) -> bool:
    return _matches(normalize_domain(domain), RETAILER_DOMAINS)


def is_blocked_domain(domain: str) -> bool:
    return _matches(normalize_domain(domain), BLOCKED_DOMAINS)


def is_trusted_domain(domain: str) -> bool:
    normalized = normalize_domain(domain)
    return is_publisher_domain(normalized) or is_retailer_domain(normalized)
