"""Data models for Idealo Scraper."""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class Offer:
    """Represents a single merchant offer for a product."""
    
    # Pricing
    price: float
    currency: str = "EUR"
    shipping_cost: Optional[float] = None
    total_price: Optional[float] = None  # price + shipping
    
    # Merchant info
    shop_name: str = ""
    shop_id: Optional[str] = None
    shop_logo_url: Optional[str] = None
    shop_rating: Optional[float] = None
    shop_reviews_count: Optional[int] = None
    is_marketplace: bool = False
    marketplace_seller: Optional[str] = None
    
    # Availability
    availability: Optional[str] = None  # "in stock", "2-3 days", etc.
    delivery_time: Optional[str] = None
    
    # Links
    offer_url: Optional[str] = None
    
    # Payment
    payment_methods: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate total price if not set."""
        if self.total_price is None and self.shipping_cost is not None:
            self.total_price = self.price + self.shipping_cost
        elif self.total_price is None:
            self.total_price = self.price


@dataclass
class Product:
    """Represents an Idealo product."""
    
    # Identifiers
    product_id: str
    url: str
    
    # Basic info
    name: str
    brand: Optional[str] = None
    description: Optional[str] = None
    
    # Images
    image_url: Optional[str] = None
    image_urls: List[str] = field(default_factory=list)
    
    # Category
    category: Optional[str] = None
    category_id: Optional[str] = None
    
    # Specs (key-value pairs)
    specifications: dict = field(default_factory=dict)
    
    # EAN/GTIN
    ean: Optional[str] = None
    gtin: Optional[str] = None
    mpn: Optional[str] = None  # Manufacturer Part Number


@dataclass
class SearchResult:
    """Represents a product search result."""
    
    product_id: str
    name: str
    url: str
    image_url: Optional[str] = None
    ean: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for backwards compatibility."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "url": self.url,
            "image_url": self.image_url,
            "ean": self.ean,
        }


@dataclass 
class ScrapeResult:
    """Complete result of scraping a product page."""
    
    # Product info
    product: Product
    
    # All offers from different merchants
    offers: List[Offer] = field(default_factory=list)
    
    # Pricing summary
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    offer_count: int = 0
    
    # Metadata
    country: str = ""
    currency: str = "EUR"
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Raw data (for debugging)
    raw_json_ld: Optional[dict] = None
    
    def __post_init__(self):
        """Calculate pricing summary."""
        if self.offers:
            prices = [o.price for o in self.offers if o.price]
            if prices:
                self.lowest_price = min(prices)
                self.highest_price = max(prices)
            self.offer_count = len(self.offers)
    
    def get_best_offer(self) -> Optional[Offer]:
        """Get the offer with the lowest total price."""
        if not self.offers:
            return None
        return min(self.offers, key=lambda o: o.total_price or o.price)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "product": {
                "id": self.product.product_id,
                "name": self.product.name,
                "brand": self.product.brand,
                "url": self.product.url,
                "image_url": self.product.image_url,
                "category": self.product.category,
                "ean": self.product.ean,
            },
            "pricing": {
                "lowest_price": self.lowest_price,
                "highest_price": self.highest_price,
                "offer_count": self.offer_count,
                "currency": self.currency,
            },
            "offers": [
                {
                    "shop_name": o.shop_name,
                    "price": o.price,
                    "shipping_cost": o.shipping_cost,
                    "total_price": o.total_price,
                    "delivery_time": o.delivery_time,
                    "shop_rating": o.shop_rating,
                    "shop_reviews_count": o.shop_reviews_count,
                    "shop_logo_url": o.shop_logo_url,
                    "is_marketplace": o.is_marketplace,
                    "marketplace_seller": o.marketplace_seller,
                    "offer_url": o.offer_url,
                    "payment_methods": o.payment_methods,
                }
                for o in self.offers
            ],
            "metadata": {
                "country": self.country,
                "scraped_at": self.scraped_at.isoformat(),
            }
        }

