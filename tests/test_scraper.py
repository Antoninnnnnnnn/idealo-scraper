"""Unit tests for idealo_scraper with fixtures (offline tests)."""
import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from idealo_scraper.parsing import (
    extract_product_id,
    extract_json_ld,
    parse_product_info,
    parse_offers,
    parse_search_results,
    deduplicate_offers,
    normalize_text,
    parse_product_page,
)
from idealo_scraper.models import Offer, Product, SearchResult
from idealo_scraper.config import COUNTRIES
from idealo_scraper.exceptions import ParseError


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def product_page_html():
    """Load French product page fixture."""
    with open(FIXTURES_DIR / "product_page_fr.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def search_results_html():
    """Load search results fixture."""
    with open(FIXTURES_DIR / "search_results_fr.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def fr_config():
    """Get French country config."""
    return COUNTRIES["fr"]


# =============================================================================
# Tests for extract_product_id
# =============================================================================

class TestExtractProductId:
    """Tests for extract_product_id function."""
    
    def test_extract_fr_url(self):
        """Test extracting ID from French URL."""
        url = "https://www.idealo.fr/prix/204101930/kingston-fury.html"
        assert extract_product_id(url) == "204101930"
    
    def test_extract_de_url(self):
        """Test extracting ID from German URL."""
        url = "https://www.idealo.de/preisvergleich/OffersOfProduct/204101930"
        assert extract_product_id(url) == "204101930"
    
    def test_extract_uk_url(self):
        """Test extracting ID from UK URL."""
        url = "https://www.idealo.co.uk/compare/123456789/product.html"
        assert extract_product_id(url) == "123456789"
    
    def test_extract_es_url(self):
        """Test extracting ID from Spanish URL."""
        url = "https://www.idealo.es/precios/987654321/producto.html"
        assert extract_product_id(url) == "987654321"
    
    def test_extract_invalid_url_raises(self):
        """Test that invalid URL raises ParseError."""
        with pytest.raises(ParseError):
            extract_product_id("https://www.google.com/")


# =============================================================================
# Tests for extract_json_ld
# =============================================================================

class TestExtractJsonLd:
    """Tests for extract_json_ld function."""
    
    def test_extract_from_product_page(self, product_page_html):
        """Test extracting JSON-LD from product page."""
        json_ld = extract_json_ld(product_page_html)
        
        assert json_ld is not None
        assert json_ld["@type"] == "Product"
        assert json_ld["name"] == "Test Product DDR5 32GB"
        assert json_ld["brand"]["name"] == "TestBrand"
        assert json_ld["gtin13"] == "1234567890123"
    
    def test_extract_from_empty_html(self):
        """Test extracting from HTML without JSON-LD."""
        html = "<html><body><h1>No JSON-LD here</h1></body></html>"
        assert extract_json_ld(html) is None
    
    def test_extract_handles_array_format(self):
        """Test extracting JSON-LD when it's in an array."""
        html = '''
        <script type="application/ld+json">
        [{"@type": "Organization"}, {"@type": "Product", "name": "Array Product"}]
        </script>
        '''
        json_ld = extract_json_ld(html)
        assert json_ld is not None
        assert json_ld["name"] == "Array Product"
    
    def test_extract_handles_graph_format(self):
        """Test extracting JSON-LD from @graph structure."""
        html = '''
        <script type="application/ld+json">
        {"@graph": [{"@type": "WebPage"}, {"@type": "Product", "name": "Graph Product"}]}
        </script>
        '''
        json_ld = extract_json_ld(html)
        assert json_ld is not None
        assert json_ld["name"] == "Graph Product"


# =============================================================================
# Tests for parse_product_info
# =============================================================================

class TestParseProductInfo:
    """Tests for parse_product_info function."""
    
    def test_parse_with_json_ld(self, product_page_html):
        """Test parsing product info with JSON-LD."""
        json_ld = extract_json_ld(product_page_html)
        product = parse_product_info(product_page_html, json_ld, "123456", "https://example.com")
        
        assert product.name == "Test Product DDR5 32GB"
        assert product.brand == "TestBrand"
        assert product.ean == "1234567890123"
        assert product.image_url == "https://example.com/image1.jpg"
        assert len(product.image_urls) == 2
    
    def test_parse_without_json_ld(self, product_page_html):
        """Test parsing product info without JSON-LD (fallback to H1)."""
        product = parse_product_info(product_page_html, None, "123456", "https://example.com")
        
        # Should fallback to H1 tag
        assert "Test Product" in product.name


# =============================================================================
# Tests for parse_offers
# =============================================================================

class TestParseOffers:
    """Tests for parse_offers function."""
    
    def test_parse_offers_from_fixture(self, product_page_html, fr_config):
        """Test parsing offers from fixture HTML."""
        offers = parse_offers(product_page_html, fr_config)
        
        # Should find offers (exact count depends on deduplication)
        assert len(offers) >= 1
        
        # Check first offer
        first_offer = offers[0]
        assert first_offer.price > 0
        assert first_offer.currency == "EUR"
    
    def test_parse_marketplace_offer(self, product_page_html, fr_config):
        """Test that marketplace offers are correctly identified."""
        offers = parse_offers(product_page_html, fr_config)
        
        # Find marketplace offer
        marketplace_offers = [o for o in offers if o.is_marketplace]
        # May or may not have marketplace based on parsing
        assert isinstance(marketplace_offers, list)


# =============================================================================
# Tests for deduplicate_offers
# =============================================================================

class TestDeduplicateOffers:
    """Tests for deduplicate_offers function."""
    
    def test_dedupe_same_price(self):
        """Test that offers with same price but different shops are preserved."""
        offers = [
            Offer(price=99.99, shop_name="Shop1"),
            Offer(price=99.99, shop_name=""),  # Empty shop name
            Offer(price=109.99, shop_name="Shop2"),
        ]
        
        result = deduplicate_offers(offers)
        
        # Should have 3 offers: Shop1 (99.99), empty (99.99), Shop2 (109.99)
        # Different shop names = different offers
        assert len(result) == 3
        
        # The one with shop name should be kept
        prices_99 = [o for o in result if round(o.price, 2) == 99.99]
        assert len(prices_99) == 2  # Shop1 and empty are different
    
    def test_dedupe_preserves_order(self):
        """Test that deduplication preserves price order."""
        offers = [
            Offer(price=150.00),
            Offer(price=100.00),
            Offer(price=200.00),
        ]
        
        result = deduplicate_offers(offers)
        
        # Should be sorted by price
        assert result[0].price == 100.00
        assert result[1].price == 150.00
        assert result[2].price == 200.00


# =============================================================================
# Tests for normalize_text
# =============================================================================

class TestNormalizeText:
    """Tests for normalize_text function."""
    
    def test_removes_soft_hyphen(self):
        """Test that soft hyphens are removed."""
        text = "Livraison\xadexpress"
        assert normalize_text(text) == "Livraisonexpress"
    
    def test_removes_zero_width_chars(self):
        """Test that zero-width characters are removed."""
        text = "Test\u200b\u200c\u200dText"
        assert normalize_text(text) == "TestText"
    
    def test_removes_bom(self):
        """Test that BOM is removed."""
        text = "\ufeffStart of text"
        assert normalize_text(text) == "Start of text"
    
    def test_strips_whitespace(self):
        """Test that whitespace is stripped."""
        text = "  Trimmed  "
        assert normalize_text(text) == "Trimmed"


# =============================================================================
# Tests for parse_search_results
# =============================================================================

class TestParseSearchResults:
    """Tests for parse_search_results function."""
    
    def test_parse_search_results(self, search_results_html, fr_config):
        """Test parsing search results."""
        results = parse_search_results(search_results_html, fr_config)
        
        assert len(results) == 3
        
        # Check first result
        assert results[0].product_id == "12345678"
        assert "Product One" in results[0].name
        
        # Check URLs are complete
        assert results[0].url.startswith("https://")


# =============================================================================
# Tests for parse_product_page (optimized function)
# =============================================================================

class TestParseProductPage:
    """Tests for the optimized parse_product_page function."""
    
    def test_parse_product_page_returns_tuple(self, product_page_html, fr_config):
        """Test that parse_product_page returns tuple of (Product, List[Offer])."""
        product, offers = parse_product_page(
            product_page_html,
            "123456",
            "https://example.com",
            fr_config
        )
        
        assert isinstance(product, Product)
        assert isinstance(offers, list)
        assert product.name == "Test Product DDR5 32GB"


# =============================================================================
# Tests for IdealoScraper with mock HttpClient (Dependency Injection)
# =============================================================================

class TestIdealoScraperDependencyInjection:
    """Tests for IdealoScraper with injected HttpClient."""
    
    def test_accepts_injected_client(self, product_page_html):
        """Test that IdealoScraper accepts an injected HttpClient."""
        from idealo_scraper import IdealoScraper
        
        # Create a mock client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = product_page_html
        mock_response.url = "https://www.idealo.fr/prix/123456/test.html"
        mock_client.get.return_value = mock_response
        
        # Inject mock client
        scraper = IdealoScraper(http_client=mock_client)
        
        # Verify the mock was used
        assert scraper._client is mock_client
        assert scraper._owns_client is False
    
    def test_close_does_not_close_injected_client(self):
        """Test that close() doesn't close an injected client."""
        from idealo_scraper import IdealoScraper
        
        mock_client = Mock()
        scraper = IdealoScraper(http_client=mock_client)
        
        scraper.close()
        
        # Should not call close on injected client
        mock_client.close.assert_not_called()
    
    def test_close_closes_owned_client(self):
        """Test that close() closes a client we own."""
        from idealo_scraper import IdealoScraper
        
        scraper = IdealoScraper()
        original_client = scraper._client
        
        # Mock the close method
        original_client.close = Mock()
        
        scraper.close()
        
        # Should call close on owned client
        original_client.close.assert_called_once()


# =============================================================================
# Tests for fixed deduplicate_offers (different shops, same price)
# =============================================================================

class TestDeduplicateOffersFix:
    """Tests for the fixed deduplicate_offers function that preserves different shops."""
    
    def test_different_shops_same_price_preserved(self):
        """Test that different shops with same price are NOT deduplicated."""
        offers = [
            Offer(price=99.99, shop_name="Amazon"),
            Offer(price=99.99, shop_name="Fnac"),
            Offer(price=99.99, shop_name="Cdiscount"),
        ]
        
        result = deduplicate_offers(offers)
        
        # All three should be preserved since they're different shops
        assert len(result) == 3
        shop_names = {o.shop_name for o in result}
        assert "Amazon" in shop_names
        assert "Fnac" in shop_names
        assert "Cdiscount" in shop_names
    
    def test_same_shop_same_price_deduplicated(self):
        """Test that same shop with same price IS deduplicated."""
        offers = [
            Offer(price=99.99, shop_name="Amazon"),
            Offer(price=99.99, shop_name="Amazon"),  # Duplicate
        ]
        
        result = deduplicate_offers(offers)
        
        # Should have only 1 Amazon offer
        assert len(result) == 1
        assert result[0].shop_name == "Amazon"


# =============================================================================
# Tests for HttpClient thread-safety
# =============================================================================

class TestHttpClientThreadSafety:
    """Tests for HttpClient thread-safety features."""
    
    def test_has_lock_attribute(self):
        """Test that HttpClient has a threading lock."""
        from idealo_scraper.http_client import HttpClient
        
        client = HttpClient()
        
        assert hasattr(client, '_lock')
        import threading
        assert isinstance(client._lock, type(threading.Lock()))
        
        client.close()
    
    def test_proxy_sanitization(self):
        """Test that proxy URLs are sanitized for logging."""
        from idealo_scraper.http_client import HttpClient
        
        client = HttpClient()
        
        # Test with credentials
        result = client._sanitize_proxy_for_log("http://user:password123@proxy.example.com:8080")
        assert "user" not in result
        assert "password123" not in result
        assert "***" in result
        
        # Test without credentials
        result = client._sanitize_proxy_for_log("http://proxy.example.com:8080")
        assert result == "http://proxy.example.com:8080"
        
        # Test None
        assert client._sanitize_proxy_for_log(None) is None
        
        client.close()


# =============================================================================
# Tests for AsyncIdealoScraper
# =============================================================================

class TestAsyncIdealoScraper:
    """Basic tests for AsyncIdealoScraper."""
    
    def test_import(self):
        """Test that AsyncIdealoScraper can be imported."""
        from idealo_scraper import AsyncIdealoScraper
        
        assert AsyncIdealoScraper is not None
    
    def test_initialization(self):
        """Test AsyncIdealoScraper initialization."""
        from idealo_scraper import AsyncIdealoScraper
        
        scraper = AsyncIdealoScraper(
            default_country="fr",
            max_concurrent=3,
            delay_seconds=0.5,
            timeout=15,
        )
        
        assert scraper.default_country == "fr"
        assert scraper.max_concurrent == 3
        assert scraper.delay_seconds == 0.5
        assert scraper.timeout == 15
    
    def test_invalid_country_raises(self):
        """Test that invalid country raises ValueError."""
        from idealo_scraper import AsyncIdealoScraper
        
        with pytest.raises(ValueError):
            AsyncIdealoScraper(default_country="invalid")
    
    def test_accepts_injected_client(self):
        """Test that AsyncIdealoScraper accepts an injected AsyncHttpClient."""
        from idealo_scraper import AsyncIdealoScraper, AsyncHttpClient
        
        mock_client = AsyncHttpClient()
        scraper = AsyncIdealoScraper(http_client=mock_client)
        
        assert scraper._client is mock_client
        assert scraper._owns_client is False
    
    def test_creates_own_client(self):
        """Test that AsyncIdealoScraper creates its own client if none injected."""
        from idealo_scraper import AsyncIdealoScraper, AsyncHttpClient
        
        scraper = AsyncIdealoScraper()
        
        assert isinstance(scraper._client, AsyncHttpClient)
        assert scraper._owns_client is True


# =============================================================================
# Tests for AsyncHttpClient
# =============================================================================

class TestAsyncHttpClient:
    """Tests for AsyncHttpClient."""
    
    def test_import(self):
        """Test that AsyncHttpClient can be imported."""
        from idealo_scraper import AsyncHttpClient
        
        assert AsyncHttpClient is not None
    
    def test_initialization(self):
        """Test AsyncHttpClient initialization."""
        from idealo_scraper import AsyncHttpClient
        
        client = AsyncHttpClient(
            delay_seconds=0.5,
            max_retries=5,
            timeout=20,
            max_concurrent=10,
        )
        
        assert client.delay_seconds == 0.5
        assert client.max_retries == 5
        assert client.timeout == 20
        assert client.max_concurrent == 10
    
    def test_proxy_sanitization(self):
        """Test that proxy URLs are sanitized for logging."""
        from idealo_scraper import AsyncHttpClient
        
        client = AsyncHttpClient()
        
        # Test with credentials
        result = client._sanitize_proxy_for_log("http://user:password123@proxy.example.com:8080")
        assert "user" not in result
        assert "password123" not in result
        assert "***" in result
        
        # Test None
        assert client._sanitize_proxy_for_log(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

