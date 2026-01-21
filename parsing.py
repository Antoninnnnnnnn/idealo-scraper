"""HTML/JSON parsing utilities for Idealo pages."""
import re
import json
import logging
import unicodedata
from typing import List, Optional, Dict, Any, Tuple

# Try to import BeautifulSoup once at module level for performance
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

from .config import CountryConfig
from .models import Offer, Product, SearchResult
from .exceptions import ParseError

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """
    Normalize text by removing soft hyphens, zero-width chars, and normalizing unicode.
    
    This handles various encoding issues in scraped HTML content.
    """
    # Normalize to NFC form
    text = unicodedata.normalize('NFC', text)
    # Remove soft hyphens
    text = text.replace('\xad', '')
    # Remove zero-width characters
    text = text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    # Remove other invisible formatting chars
    text = text.replace('\ufeff', '')  # BOM
    return text.strip()


def extract_product_id(url: str) -> str:
    """
    Extract product ID from Idealo URL.
    
    Args:
        url: Idealo product URL
        
    Returns:
        Product ID string
        
    Raises:
        ParseError: If product ID cannot be extracted
    """
    patterns = [
        r"/prix/(\d+)/",           # FR
        r"/preisvergleich/OffersOfProduct/(\d+)",  # DE
        r"/preisvergleich/(\d+)/",  # DE alternative
        r"/compare/(\d+)/",         # UK
        r"/confronta-prezzi/(\d+)/",  # IT
        r"/precios/(\d+)/",         # ES
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ParseError(f"Could not extract product ID from URL: {url}")


def extract_json_ld(html: str) -> Optional[dict]:
    """Extract JSON-LD Product structured data from HTML."""
    # More robust regex that handles optional attributes and whitespace variations
    pattern = r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        try:
            data = json.loads(match.strip())
            # Handle both direct Product and arrays containing Product
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                # Handle @graph structure
                if "@graph" in data:
                    for item in data["@graph"]:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            return item
        except json.JSONDecodeError:
            continue
    
    return None


def parse_product_info(
    html: str,
    json_ld: Optional[dict],
    product_id: str,
    url: str
) -> Product:
    """Parse product information from HTML and JSON-LD."""
    name = ""
    brand = None
    image_url = None
    image_urls = []
    category = None
    ean = None
    description = None
    specifications = {}
    
    if json_ld:
        name = json_ld.get("name", "")
        brand_data = json_ld.get("brand", {})
        if isinstance(brand_data, dict):
            brand = brand_data.get("name")
        elif isinstance(brand_data, str):
            brand = brand_data
        
        image_url = json_ld.get("image", "")
        if isinstance(image_url, list) and image_url:
            image_urls = image_url
            image_url = image_url[0]
        
        ean = json_ld.get("gtin13") or json_ld.get("gtin")
        description = json_ld.get("description")
    
    # Fallback: extract from HTML
    if not name:
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if title_match:
            name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
    
    # Extract category from breadcrumbs
    breadcrumb_match = re.search(r'"category":"([^"]+)"', html)
    if breadcrumb_match:
        category = breadcrumb_match.group(1)
    
    # Extract specifications
    specifications = extract_specifications(html)
    
    return Product(
        product_id=product_id,
        url=url,
        name=name,
        brand=brand,
        description=description,
        image_url=image_url,
        image_urls=image_urls,
        category=category,
        ean=ean,
        specifications=specifications,
    )


def extract_specifications(html: str) -> dict:
    """Extract product specifications from HTML."""
    specs = {}
    
    if not BS4_AVAILABLE:
        return specs
        
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        spec_patterns = [
            {'class': re.compile(r'datasheet|specification|feature|detail', re.I)},
            {'data-test': re.compile(r'datasheet|spec', re.I)},
        ]
        
        for pattern in spec_patterns:
            spec_sections = soup.find_all(['div', 'section', 'table', 'dl'], attrs=pattern)
            for section in spec_sections:
                # Table rows
                for row in section.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if key and value:
                            specs[key] = value
                
                # Definition lists
                dts = section.find_all('dt')
                dds = section.find_all('dd')
                for dt, dd in zip(dts, dds):
                    key = dt.get_text(strip=True)
                    value = dd.get_text(strip=True)
                    if key and value:
                        specs[key] = value
                
                # Key-value divs
                for item in section.find_all(['div', 'li'], class_=re.compile(r'row|item|line', re.I)):
                    text = item.get_text(strip=True)
                    if ':' in text:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            specs[parts[0].strip()] = parts[1].strip()
        
        # Extract from JSON in page
        data_patterns = [
            r'"specifications"\s*:\s*(\{[^}]+\})',
            r'"specs"\s*:\s*(\{[^}]+\})',
        ]
        for pattern in data_patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    spec_data = json.loads(match.group(1))
                    specs.update(spec_data)
                except json.JSONDecodeError:
                    pass
                    
    except (AttributeError, TypeError, ValueError) as e:
        logger.debug(f"Failed to extract specifications: {e}")
    
    return specs


def parse_offers(html: str, config: CountryConfig) -> List[Offer]:
    """Parse all merchant offers from HTML."""
    if not BS4_AVAILABLE:
        logger.warning("BeautifulSoup not available, using regex fallback")
        return parse_offers_regex_fallback(html, config)
    
    offers = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try multiple selectors for robustness (CSS classes change frequently)
    offer_list_selectors = [
        {'class_': 'productOffers-list'},  # Primary selector
        {'class_': re.compile(r'offer.*list', re.I)},  # Generic offer list
        {'class_': re.compile(r'price.*list', re.I)},  # Price list variant
        {'data-test': re.compile(r'offer', re.I)},  # data-test attribute
        {'id': re.compile(r'offer|price', re.I)},  # ID-based fallback
    ]
    
    offer_list = None
    for selector in offer_list_selectors:
        offer_list = soup.find(['ul', 'div', 'section'], **selector)
        if offer_list:
            logger.debug(f"Found offer list with selector: {selector}")
            break
    
    if not offer_list:
        logger.debug("No offer list found, using regex fallback")
        return parse_offers_regex_fallback(html, config)
    
    # Try multiple selectors for individual offer items
    offer_items = offer_list.find_all('li', recursive=False)
    if not offer_items:
        # Fallback: try divs with offer-related classes
        offer_items = offer_list.find_all(
            ['li', 'div', 'article'],
            class_=re.compile(r'offer|item|row', re.I),
            recursive=False
        )
    
    for item in offer_items:
        item_class = str(item.get('class', []))
        if 'headline' in item_class.lower() or 'header' in item_class.lower():
            continue
        
        offer = parse_offer_item(item, config)
        if offer:
            offers.append(offer)
    
    # Deduplicate by price
    return deduplicate_offers(offers)


def parse_offer_item(item, config: CountryConfig) -> Optional[Offer]:
    """Parse a single offer item using BeautifulSoup."""
    try:
        # Extract price
        price_elem = item.find(class_=re.compile(r'productOffers.*Price'))
        if not price_elem:
            return None
        
        price_text = price_elem.get_text(strip=True)
        price_match = re.search(r'(\d+)[,.](\d{2})', price_text)
        if not price_match:
            return None
        
        price = float(f"{price_match.group(1)}.{price_match.group(2)}")
        
        # Shop info
        shop_elems = item.find_all(attrs={'data-shop-name': True})
        platform = ""
        seller = ""
        
        for se in shop_elems:
            name = se.get('data-shop-name', '').strip()
            if not name:
                continue
            if ' - ' in name and 'Marchand' in name:
                parts = name.split(' - ')
                if len(parts) >= 2:
                    platform = parts[1].strip()
            elif not seller:
                seller = name
        
        if not platform and seller:
            platform = seller
            seller = ""
        
        is_marketplace = 'marketplace' in platform.lower() if platform else False
        
        # Shop logo
        logo_url = None
        logo_img = item.find('img', class_=re.compile(r'logo|shop', re.I))
        if logo_img:
            logo_url = logo_img.get('src') or logo_img.get('data-src')
            if logo_url and logo_url.startswith('//'):
                logo_url = 'https:' + logo_url
        
        # Rating
        rating = None
        rating_elems = item.find_all(class_=re.compile(r'rating', re.I))
        for rating_elem in rating_elems:
            rating_text = rating_elem.get_text()
            rating_match = re.search(r'(\d+)[,.](\d)', rating_text)
            if rating_match:
                try:
                    rating = float(f"{rating_match.group(1)}.{rating_match.group(2)}")
                    break
                except ValueError:
                    pass
        
        # Reviews count
        reviews = None
        for rating_elem in rating_elems:
            text = rating_elem.get_text()
            reviews_match = re.search(r'(\d+)[,.]?\d*\s*[\n\r\s]+(\d+)', text)
            if reviews_match:
                reviews = int(reviews_match.group(2))
                break
        
        # Shipping cost
        shipping_cost = None
        shipping_elems = item.find_all(class_=re.compile(r'shipping|livraison|versand', re.I))
        for se in shipping_elems:
            text = se.get_text(strip=True).lower()
            if 'gratuit' in text or 'free' in text or 'kostenfrei' in text or 'incl' in text:
                shipping_cost = 0.0
                break
            else:
                cost_match = re.search(r'(\d+)[,.](\d{2})', text)
                if cost_match:
                    shipping_cost = float(f"{cost_match.group(1)}.{cost_match.group(2)}")
                    break
        
        if 'livraison incl' in price_text.lower() or 'versand inklusive' in price_text.lower():
            shipping_cost = 0.0
        
        # Delivery time
        delivery_time = None
        delivery_elems = item.find_all(class_=re.compile(r'delivery|livraison|lieferung', re.I))
        for de in delivery_elems:
            text = normalize_text(de.get_text(strip=True))
            if len(text) > 5 and len(text) < 80:
                if text.lower() not in ['delivery', 'livraison', 'lieferung', 'transporteur']:
                    delivery_time = text
                    break
        
        # Offer URL
        offer_url = None
        offer_links = item.find_all('a', href=re.compile(r'relocator|redirect|click', re.I))
        if offer_links:
            href = offer_links[0].get('href', '')
            if href.startswith('/'):
                offer_url = f"https://{config.domain}{href}"
            elif href.startswith('http'):
                offer_url = href
        
        # Payment methods
        payment_methods = []
        payment_elems = item.find_all(class_=re.compile(r'payment|paiement|zahlung', re.I))
        for pe in payment_elems:
            text = pe.get_text(strip=True)
            if text and len(text) < 50:
                payment_methods.append(text)
        
        return Offer(
            price=price,
            currency=config.currency,
            shipping_cost=shipping_cost,
            shop_name=platform,
            shop_logo_url=logo_url,
            shop_rating=rating,
            shop_reviews_count=reviews,
            is_marketplace=is_marketplace,
            marketplace_seller=seller if seller and seller != platform else None,
            availability=delivery_time,
            delivery_time=delivery_time,
            offer_url=offer_url,
            payment_methods=payment_methods,
        )
        
    except Exception as e:
        logger.debug(f"Failed to parse offer item: {e}")
        return None


def parse_offers_regex_fallback(html: str, config: CountryConfig) -> List[Offer]:
    """Fallback regex-based offer parsing when BeautifulSoup is unavailable."""
    offers = []
    
    price_pattern = r'"lowPrice"\s*:\s*([0-9.]+)'
    prices = re.findall(price_pattern, html)
    
    for price_str in prices:
        try:
            price = float(price_str)
            offers.append(Offer(
                price=price,
                currency=config.currency,
            ))
        except ValueError:
            continue
    
    return deduplicate_offers(offers)


def deduplicate_offers(offers: List[Offer]) -> List[Offer]:
    """
    Remove duplicate offers based on price AND shop name.
    
    This ensures we don't lose legitimate offers from different merchants
    with the same price point.
    """
    seen = {}
    for offer in offers:
        # Use both price and shop_name as key to avoid losing different merchants
        key = (round(offer.price, 2), offer.shop_name or "")
        if key not in seen:
            seen[key] = offer
        elif offer.shop_name and not seen[key].shop_name:
            # Prefer the one with shop info
            seen[key] = offer
    
    unique_offers = sorted(seen.values(), key=lambda o: o.total_price or o.price)
    return unique_offers


def parse_search_results(html: str, config: CountryConfig) -> List[SearchResult]:
    """Parse search results page for product links."""
    results = []
    
    if not BS4_AVAILABLE:
        return results
        
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        product_link_pattern = re.compile(
            r'/(prix|preisvergleich|compare|confronta-prezzi|precios)/(OffersOfProduct/)?\d+'
        )
        links = soup.find_all('a', href=product_link_pattern)
        seen_ids = set()
        
        for link in links[:20]:
            href = link.get('href', '')
            try:
                product_id = extract_product_id(href)
                if not product_id or product_id in seen_ids:
                    continue
                seen_ids.add(product_id)
                
                name = link.get_text(strip=True)[:100]
                
                if href.startswith('/'):
                    href = f"https://{config.domain}{href}"
                
                results.append(SearchResult(
                    product_id=product_id,
                    name=name,
                    url=href,
                ))
            except (ParseError, ValueError, AttributeError) as e:
                logger.debug(f"Failed to parse link: {e}")
                continue
                
    except (AttributeError, TypeError) as e:
        logger.debug(f"Failed to parse search results: {e}")
    
    return results


def extract_product_name_from_html(html: str) -> str:
    """Extract product name from HTML H1 tag."""
    if not BS4_AVAILABLE:
        return ""
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        h1 = soup.find('h1')
        return h1.get_text(strip=True) if h1 else ""
    except AttributeError:
        return ""


def parse_product_page(
    html: str,
    product_id: str,
    url: str,
    config: CountryConfig,
) -> Tuple[Product, List[Offer]]:
    """
    Parse a complete product page in a single pass.
    
    This is an optimized version that parses HTML once and extracts
    both product info and offers, avoiding multiple BeautifulSoup instantiations.
    
    Args:
        html: Raw HTML content
        product_id: Product ID
        url: Product URL
        config: Country configuration
        
    Returns:
        Tuple of (Product, List[Offer])
    """
    # Extract JSON-LD first (regex-based, doesn't need soup)
    json_ld = extract_json_ld(html)
    
    # Parse HTML once
    soup = None
    if BS4_AVAILABLE:
        soup = BeautifulSoup(html, 'html.parser')
    
    # Extract product info
    product = _parse_product_info_from_soup(html, json_ld, product_id, url, soup)
    
    # Extract offers using same soup
    offers = _parse_offers_from_soup(soup, html, config)
    
    return product, offers


def _parse_product_info_from_soup(
    html: str,
    json_ld: Optional[dict],
    product_id: str,
    url: str,
    soup: Optional['BeautifulSoup'] = None,
) -> Product:
    """Parse product info, optionally using pre-parsed soup."""
    name = ""
    brand = None
    image_url = None
    image_urls = []
    category = None
    ean = None
    description = None
    specifications = {}
    
    if json_ld:
        name = json_ld.get("name", "")
        brand_data = json_ld.get("brand", {})
        if isinstance(brand_data, dict):
            brand = brand_data.get("name")
        elif isinstance(brand_data, str):
            brand = brand_data
        
        image_url = json_ld.get("image", "")
        if isinstance(image_url, list) and image_url:
            image_urls = image_url
            image_url = image_url[0]
        
        ean = json_ld.get("gtin13") or json_ld.get("gtin")
        description = json_ld.get("description")
    
    # Fallback: extract from HTML
    if not name:
        if soup:
            h1 = soup.find('h1')
            if h1:
                name = h1.get_text(strip=True)
        else:
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_match:
                name = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
    
    # Extract category from breadcrumbs
    breadcrumb_match = re.search(r'"category":"([^"]+)"', html)
    if breadcrumb_match:
        category = breadcrumb_match.group(1)
    
    # Extract specifications using soup if available
    if soup:
        specifications = _extract_specifications_from_soup(soup, html)
    else:
        specifications = extract_specifications(html)
    
    return Product(
        product_id=product_id,
        url=url,
        name=name,
        brand=brand,
        description=description,
        image_url=image_url,
        image_urls=image_urls,
        category=category,
        ean=ean,
        specifications=specifications,
    )


def _extract_specifications_from_soup(soup: 'BeautifulSoup', html: str) -> dict:
    """Extract specifications using pre-parsed soup."""
    specs = {}
    
    try:
        spec_patterns = [
            {'class': re.compile(r'datasheet|specification|feature|detail', re.I)},
            {'data-test': re.compile(r'datasheet|spec', re.I)},
        ]
        
        for pattern in spec_patterns:
            spec_sections = soup.find_all(['div', 'section', 'table', 'dl'], attrs=pattern)
            for section in spec_sections:
                # Table rows
                for row in section.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if key and value:
                            specs[key] = value
                
                # Definition lists
                dts = section.find_all('dt')
                dds = section.find_all('dd')
                for dt, dd in zip(dts, dds):
                    key = dt.get_text(strip=True)
                    value = dd.get_text(strip=True)
                    if key and value:
                        specs[key] = value
                
                # Key-value divs
                for item in section.find_all(['div', 'li'], class_=re.compile(r'row|item|line', re.I)):
                    text = item.get_text(strip=True)
                    if ':' in text:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            specs[parts[0].strip()] = parts[1].strip()
        
        # Extract from JSON in page
        data_patterns = [
            r'"specifications"\s*:\s*(\{[^}]+\})',
            r'"specs"\s*:\s*(\{[^}]+\})',
        ]
        for pattern in data_patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    spec_data = json.loads(match.group(1))
                    specs.update(spec_data)
                except json.JSONDecodeError:
                    pass
                    
    except (AttributeError, TypeError, ValueError) as e:
        logger.debug(f"Failed to extract specifications: {e}")
    
    return specs


def _parse_offers_from_soup(
    soup: Optional['BeautifulSoup'],
    html: str,
    config: CountryConfig,
) -> List[Offer]:
    """Parse offers using pre-parsed soup."""
    if not soup:
        return parse_offers_regex_fallback(html, config)
    
    offers = []
    offer_list = soup.find(class_='productOffers-list')
    if not offer_list:
        return parse_offers_regex_fallback(html, config)
    
    offer_items = offer_list.find_all('li', recursive=False)
    
    for item in offer_items:
        item_class = str(item.get('class', []))
        if 'headline' in item_class.lower():
            continue
        
        offer = parse_offer_item(item, config)
        if offer:
            offers.append(offer)
    
    return deduplicate_offers(offers)
