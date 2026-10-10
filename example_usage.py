#!/usr/bin/env python3
"""
Example usage and integration patterns for the web crawler.
Shows how to use the crawler in various scenarios.
"""

import asyncio
import json
import os
from crawler_async import AsyncCrawler


async def example_basic_crawl():
    """Basic crawl of a single domain."""
    print("=== Example 1: Basic Crawl ===\n")

    crawler = AsyncCrawler(
        start_urls=["https://example.com"],
        allowed_domains=["example.com"],
        num_workers=4,
        requests_per_second=1.0,
        max_depth=2
    )

    stats = await crawler.run()
    print(f"Crawl complete!")
    print(f"  URLs crawled: {stats['crawled']}")
    print(f"  URLs failed: {stats['failed']}")
    print(f"  Total links found: {stats['total_links']}")
    print(f"  Start time: {stats['start_time']}")
    print(f"  End time: {stats['end_time']}\n")

    # Get results
    results = crawler.db.get_results(limit=5)
    print("Sample results:")
    for result in results:
        print(f"  - {result['url']} ({result['status_code']}) [{result['response_time']}s]")


async def example_multiple_domains():
    """Crawl multiple related domains."""
    print("\n=== Example 2: Multiple Domains ===\n")

    crawler = AsyncCrawler(
        start_urls=[
            "https://example.com",
            "https://docs.example.com",
        ],
        allowed_domains=["example.com", "docs.example.com"],
        num_workers=6,
        requests_per_second=1.5,
        max_depth=3
    )

    stats = await crawler.run()
    print(f"Multi-domain crawl complete!")
    print(f"  Total URLs crawled: {stats['crawled']}")


async def example_slow_server():
    """Crawl a slow-responding server with adjusted settings."""
    print("\n=== Example 3: Slow Server Crawl ===\n")

    crawler = AsyncCrawler(
        start_urls=["https://slowserver.example.com"],
        allowed_domains=["slowserver.example.com"],
        num_workers=2,  # Fewer workers for slow server
        requests_per_second=0.5,  # Slower rate
        timeout=60,  # Longer timeout
        max_depth=2
    )

    stats = await crawler.run()
    print(f"Slow server crawl complete!")
    print(f"  URLs crawled: {stats['crawled']}")


async def example_export_results():
    """Crawl and export results to multiple formats."""
    print("\n=== Example 4: Export Results ===\n")

    crawler = AsyncCrawler(
        start_urls=["https://example.com"],
        allowed_domains=["example.com"],
        num_workers=4,
        max_depth=2
    )

    await crawler.run()

    # Get results
    results = crawler.db.get_results()

    # Export to JSON
    with open("crawl_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"✓ Exported {len(results)} results to crawl_results.json")

    # Export to CSV
    import csv
    if results:
        with open("crawl_results.csv", "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"✓ Exported {len(results)} results to crawl_results.csv")


async def example_stats_tracking():
    """Track and display crawl statistics."""
    print("\n=== Example 5: Statistics Tracking ===\n")

    crawler = AsyncCrawler(
        start_urls=["https://example.com"],
        allowed_domains=["example.com"],
        num_workers=4,
        max_depth=2
    )

    print("Starting crawl...")
    stats = await crawler.run()

    print("\n=== Crawl Statistics ===")
    print(f"URLs Crawled:     {stats['crawled']}")
    print(f"URLs Failed:      {stats['failed']}")
    print(f"URLs Skipped:     {stats['skipped']}")
    print(f"Total Links:      {stats['total_links']}")
    print(f"Start Time:       {stats['start_time']}")
    print(f"End Time:         {stats['end_time']}")

    # Get detailed results
    results = crawler.db.get_results()

    if results:
        import statistics as stats_module

        response_times = [r['response_time'] for r in results if r['response_time']]
        if response_times:
            print(f"\n=== Response Time Stats ===")
            print(f"Min:    {min(response_times):.3f}s")
            print(f"Max:    {max(response_times):.3f}s")
            print(f"Avg:    {stats_module.mean(response_times):.3f}s")
            print(f"Median: {stats_module.median(response_times):.3f}s")

        # Status codes breakdown
        status_counts = {}
        for result in results:
            status = result['status_code']
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f"\n=== Status Codes ===")
        for status, count in sorted(status_counts.items()):
            print(f"{status}: {count}")


async def example_error_handling():
    """Demonstrate error handling and retry logic."""
    print("\n=== Example 6: Error Handling ===\n")

    crawler = AsyncCrawler(
        start_urls=[
            "https://example.com",
            "https://invalid-domain-that-does-not-exist.example.com",
        ],
        allowed_domains=["example.com", "invalid-domain-that-does-not-exist.example.com"],
        num_workers=2,
        timeout=10
    )

    stats = await crawler.run()

    print(f"Crawl complete with errors!")
    print(f"  Successful: {stats['crawled']}")
    print(f"  Failed: {stats['failed']}")

    # Show failed URLs
    results = crawler.db.get_results()
    failed_results = [r for r in results if r['error']]

    if failed_results:
        print(f"\n=== Failed URLs ===")
        for result in failed_results[:5]:
            print(f"  - {result['url']}")
            print(f"    Error: {result['error']}")


async def main():
    """Run all examples. They contact the hosts named in each function."""
    print("=" * 60)
    print("Web Crawler - Usage Examples")
    print("=" * 60 + "\n")
    if os.environ.get("ASYNC_SPIDER_LIVE_EXAMPLES") != "1":
        print("Refusing to crawl. These examples contact third-party hosts.")
        print("Set ASYNC_SPIDER_LIVE_EXAMPLES=1 only for a target you are allowed to crawl.")
        return

    examples = [
        example_basic_crawl,
        example_multiple_domains,
        example_slow_server,
        example_export_results,
        example_stats_tracking,
        example_error_handling,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
