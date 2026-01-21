"""
Demo script showing Idealo Scraper capabilities.
Run: python demo.py
"""
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idealo_scraper import IdealoScraper, COUNTRIES


def main():
    print("=" * 70)
    print("🔍 IDEALO SCRAPER DEMO")
    print("=" * 70)
    print(f"\nSupported countries: {', '.join(COUNTRIES.keys())}\n")
    
    # Initialize scraper
    scraper = IdealoScraper(default_country="fr", delay_seconds=0.5)
    
    try:
        # Example 1: Scrape by URL
        print("📦 EXAMPLE 1: Scrape product by URL (FR)")
        print("-" * 50)
        
        url = "https://www.idealo.fr/prix/204101930/kingston-fury-beast-rgb-32gb-kit-ddr5-6000-cl30.html"
        result = scraper.get_product_by_url(url)
        
        print(f"Product: {result.product.name}")
        print(f"ID: {result.product.product_id}")
        print(f"Country: {result.country}")
        print(f"\n💰 Price range: {result.lowest_price}€ - {result.highest_price}€")
        print(f"📊 Number of offers: {result.offer_count}")
        
        if result.offers:
            print(f"\n🏆 Top 5 cheapest offers:")
            for i, offer in enumerate(result.offers[:5], 1):
                shipping = f" (+{offer.shipping_cost}€ ship)" if offer.shipping_cost else ""
                seller = f" via {offer.marketplace_seller}" if offer.marketplace_seller else ""
                shop = offer.shop_name if offer.shop_name else "Unknown shop"
                print(f"  {i}. {shop}: {offer.price}€{shipping}{seller}")
        
        # Example 2: Scrape by ID for different country
        print("\n" + "=" * 70)
        print("📦 EXAMPLE 2: Scrape same product on idealo.de")
        print("-" * 50)
        
        result_de = scraper.get_product_by_id("204101930", country="de")
        print(f"Product: {result_de.product.name}")
        print(f"Country: {result_de.country}")
        print(f"Price range: {result_de.lowest_price}€ - {result_de.highest_price}€")
        print(f"Offers: {result_de.offer_count}")
        
        # Example 3: Search
        print("\n" + "=" * 70)
        print("🔎 EXAMPLE 3: Search for products")
        print("-" * 50)
        
        search_results = scraper.search("PlayStation 5", country="fr", limit=5)
        print(f"Found {len(search_results)} products:\n")
        for i, item in enumerate(search_results, 1):
            print(f"  {i}. {item.name[:50]}...")
            print(f"     ID: {item.product_id}")
            print(f"     URL: {item.url}")
        
        # Example 4: JSON export
        print("\n" + "=" * 70)
        print("📄 EXAMPLE 4: Export to JSON")
        print("-" * 50)
        
        data = result.to_dict()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:800] + "...")
        
        print("\n" + "=" * 70)
        print("✅ DEMO COMPLETE!")
        print("=" * 70)
        
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
