import urllib.robotparser
from file_scraper import setup_robot_parser, can_fetch

def debug_robots_detailed():
    """Debug robots.txt parsing in detail"""
    
    # Test with direct urllib.robotparser
    print("=== Direct urllib.robotparser test ===")
    parser1 = urllib.robotparser.RobotFileParser()
    parser1.set_url("https://github.com/robots.txt")
    parser1.read()
    
    test_urls = [
        'https://github.com/user/repo/pulse',
        'https://github.com/search',
        'https://github.com/user/repo/archive/main.zip',
        'https://github.com/user/repo/commits/',
    ]
    
    for url in test_urls:
        result = parser1.can_fetch("*", url)
        print(f"Direct parser - {url}: {'ALLOWED' if result else 'DISALLOWED'}")
    
    print("\n=== Using your setup_robot_parser function ===")
    try:
        parser2 = setup_robot_parser('https://github.com/user/repo')
        for url in test_urls:
            result = can_fetch(parser2, url)
            print(f"Your function - {url}: {'ALLOWED' if result else 'DISALLOWED'}")
    except Exception as e:
        print(f"Error with your function: {e}")
    
    print(f"\n=== Parser comparison ===")
    print(f"Direct parser type: {type(parser1)}")
    if 'parser2' in locals():
        print(f"Your parser type: {type(parser2)}")
        print(f"Parsers are same: {parser1 is parser2}")

if __name__ == "__main__":
    debug_robots_detailed()