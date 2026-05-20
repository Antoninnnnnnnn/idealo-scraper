# Idealo Scraper

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-36%20passed-brightgreen.svg)]()

Modern Python scraper for [Idealo](https://www.idealo.fr) - Europe's leading price comparison website.

> 🤖 **Full disclosure**: This project was built by [@Antoninnnnnnnn](https://github.com/Antoninnnnnnnn) who freely admits he doesn't understand a single line of this code. The real MVP here is AI pair programming. Turns out you don't need to know how to code to ship code. Welcome to 2026.

## Features

- 🌍 **Multi-country support**: FR, DE, UK, ES, IT, AT
- 🔍 **Multiple search methods**: text, EAN/GTIN, URL, product ID
- 💰 **Detailed offer extraction**: prices, shipping, ratings, delivery times
- ⚡ **Async support**: parallel scraping with `AsyncIdealoScraper`
- 🔧 **Proxy support**: built-in proxy configuration
- 🛡️ **TLS bypass**: Chrome fingerprint via `curl_cffi`
- 📦 **Rich data models**: Product, Offer, ScrapeResult dataclasses

## Installation

```bash
pip install curl-cffi beautifulsoup4
```

## Quick Start

```python
from idealo_scraper import IdealoScraper

# Initialize scraper
scraper = IdealoScraper(default_country='fr')

# Search for products
results = scraper.search('iPhone 15', limit=10)
for product in results:
    print(f"{product['name']} - ID: {product['product_id']}")

# Get full product details
result = scraper.get_product_by_url(
    'https://www.idealo.fr/prix/203235721/apple-iphone-15.html'
)
print(f"Product: {result.product.name}")
print(f"Lowest price: {result.lowest_price}€")
print(f"Offers: {len(result.offers)}")

# Search by EAN
result = scraper.get_product_by_ean('8806094733358')

scraper.close()
```

## API Reference

### IdealoScraper

```python
scraper = IdealoScraper(
    default_country='fr',    # fr, de, uk, es, it, at
    delay_seconds=1.0,       # Rate limiting
    max_retries=3,
    timeout=30,
    proxy_url=None,          # 'http://user:pass@host:port'
)
```

#### Methods

| Method | Description |
|--------|-------------|
| `search(query, country, limit)` | Search products by text |
| `search_by_ean(ean, country)` | Search by EAN code |
| `get_product_by_url(url)` | Scrape product page |
| `get_product_by_id(id, country)` | Get product by Idealo ID |
| `get_product_by_ean(ean, country)` | Full product data by EAN |

### AsyncIdealoScraper

```python
async with AsyncIdealoScraper(max_workers=5) as scraper:
    # Parallel URL scraping
    results = await scraper.get_products_by_urls([url1, url2, url3])
    
    # Parallel EAN search
    results = await scraper.get_products_by_eans(['ean1', 'ean2'])
```

### Data Models

```python
# ScrapeResult
result.product          # Product dataclass
result.offers           # List[Offer]
result.lowest_price     # float
result.highest_price    # float
result.to_dict()        # Serialize to dict

# Product
product.product_id      # str
product.name            # str
product.brand           # Optional[str]
product.ean             # Optional[str]
product.specifications  # dict

# Offer
offer.price             # float
offer.shop_name         # str
offer.shop_rating       # Optional[float]
offer.shipping_cost     # Optional[float]
offer.delivery_time     # Optional[str]
offer.offer_url         # Optional[str]
```

## Supported Countries

| Code | Domain | Search Path |
|------|--------|-------------|
| `fr` | idealo.fr | `/prechcat.html?q=` |
| `de` | idealo.de | `/preisvergleich/MainSearchProductCategory.html?q=` |
| `uk` | idealo.co.uk | `/mscat.html?q=` |
| `es` | idealo.es | `/resultados.html?q=` |
| `it` | idealo.it | `/risultati.html?q=` |
| `at` | idealo.at | `/preisvergleich/MainSearchProductCategory.html?q=` |

## Using Proxy

```python
# With proxy
scraper = IdealoScraper(
    proxy_url='http://username:password@proxy.example.com:8080'
)
```

## Testing

```bash
# Unit tests only (no network)
pytest tests/test_scraper.py -m "not integration"

# All tests including live API calls
pytest tests/test_scraper.py -v
```

## Project Structure

```
idealo_scraper/
├── __init__.py          # Package exports
├── scraper.py           # Main IdealoScraper class
├── async_scraper.py     # AsyncIdealoScraper wrapper
├── models.py            # Product, Offer, ScrapeResult
├── config.py            # Country configurations
├── exceptions.py        # Custom exceptions
└── tests/
    └── test_scraper.py  # Pytest tests (22 cases)
```

## License

MIT
