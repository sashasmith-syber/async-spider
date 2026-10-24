#!/usr/bin/env python3
"""
CLI management tool for web crawler - manage runs, export data, monitor status.
"""

import json
import sqlite3
import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlsplit
import sys


class CrawlerCLI:
    """CLI interface for crawler management."""

    def __init__(self, db_path: str = "data/crawl_results.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_stats(self) -> Dict:
        """Display crawl statistics."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed,
                    AVG(response_time) as avg_response_time,
                    MAX(response_time) as max_response_time,
                    MIN(response_time) as min_response_time,
                    SUM(CASE WHEN error IS NULL THEN 0 ELSE 1 END) as errors
                FROM crawl_results
            """)

            row = cursor.fetchone()
            stats = {
                "total_crawled": row["total"] or 0,
                "successful": row["success"] or 0,
                "failed": row["failed"] or 0,
                "avg_response_time": round(row["avg_response_time"] or 0.0, 3),
                "max_response_time": round(row["max_response_time"] or 0.0, 3),
                "min_response_time": round(row["min_response_time"] or 0.0, 3),
                "errors": row["errors"] or 0,
            }

            conn.close()
            return stats

        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}

    def list_results(self, limit: int = 10, failed_only: bool = False):
        """List recent crawl results."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if failed_only:
                cursor.execute("""
                    SELECT url, status_code, error, response_time, crawled_at
                    FROM crawl_results
                    WHERE status_code != 200 OR error IS NOT NULL
                    ORDER BY crawled_at DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT url, status_code, title, response_time, crawled_at
                    FROM crawl_results
                    ORDER BY crawled_at DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            conn.close()

            print(f"\n{'URL':<60} {'Status':<8} {'Time (s)':<10} {'Crawled':<20}")
            print("-" * 100)

            for row in rows:
                url = row["url"][:55] + "..." if len(row["url"]) > 55 else row["url"]
                status = row["status_code"]
                response_time = row["response_time"] or 0.0
                crawled_at = row["crawled_at"]

                print(f"{url:<60} {status:<8} {response_time:<10.3f} {crawled_at:<20}")

        except Exception as e:
            print(f"Error listing results: {e}")

    def export_json(self, output_file: str):
        """Export results to JSON."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crawl_results ORDER BY crawled_at DESC")

            rows = cursor.fetchall()
            results = [dict(row) for row in rows]

            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)

            print(f"Exported {len(results)} results to {output_file}")
            conn.close()

        except Exception as e:
            print(f"Error exporting JSON: {e}")

    def export_csv(self, output_file: str):
        """Export results to CSV."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crawl_results ORDER BY crawled_at DESC")

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            with open(output_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))

            print(f"Exported {len(rows)} results to {output_file}")
            conn.close()

        except Exception as e:
            print(f"Error exporting CSV: {e}")

    def domain_summary(self) -> Optional[List[Dict]]:
        """Show summary by domain. Returns the rows, or None on error."""
        try:
            conn = self._get_connection()
            try:
                rows = conn.execute("SELECT url, status_code, response_time FROM crawl_results").fetchall()
            finally:
                conn.close()

            # SQLite has no URL parser, so group by host in Python.
            domains: Dict[str, Dict] = {}
            for row in rows:
                domain = urlsplit(row["url"]).netloc.lower() or "(invalid url)"
                entry = domains.setdefault(domain, {"domain": domain, "count": 0, "success": 0, "times": []})
                entry["count"] += 1
                if row["status_code"] == 200:
                    entry["success"] += 1
                if row["response_time"] is not None:
                    entry["times"].append(row["response_time"])

            summary = []
            for entry in sorted(domains.values(), key=lambda e: (-e["count"], e["domain"])):
                times = entry.pop("times")
                entry["avg_time"] = sum(times) / len(times) if times else 0.0
                summary.append(entry)

            print(f"\n{'Domain':<40} {'Count':<10} {'Success':<10} {'Avg Time':<10}")
            print("-" * 70)

            for entry in summary:
                print(f"{entry['domain']:<40} {entry['count']:<10} {entry['success']:<10} {entry['avg_time']:<10.3f}")

            return summary

        except Exception as e:
            print(f"Error getting domain summary: {e}", file=sys.stderr)
            return None

    def clear_old(self, days: int = 30):
        """Clear old results."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cutoff = datetime.utcnow() - timedelta(days=days)
            cursor.execute(
                "DELETE FROM crawl_results WHERE crawled_at < ?",
                (cutoff.isoformat(),)
            )

            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            print(f"Deleted {deleted} results older than {days} days")

        except Exception as e:
            print(f"Error clearing old results: {e}")

    def reset_database(self):
        """Reset database (remove all data)."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM crawl_results")
            cursor.execute("DELETE FROM crawled_links")

            conn.commit()
            conn.close()

            print("Database cleared")

        except Exception as e:
            print(f"Error resetting database: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Web Crawler CLI Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawler_cli.py stats              # Show statistics
  python crawler_cli.py list               # List recent crawls
  python crawler_cli.py list --failed      # List failed crawls only
  python crawler_cli.py export-json data.json  # Export to JSON
  python crawler_cli.py export-csv data.csv    # Export to CSV
  python crawler_cli.py domains            # Show domain summary
  python crawler_cli.py clear 30           # Clear crawls older than 30 days
  python crawler_cli.py reset              # Reset database (careful!)
        """
    )

    parser.add_argument('--db', default='data/crawl_results.db', help='Database path')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Stats command
    subparsers.add_parser('stats', help='Show crawl statistics')

    # List command
    list_parser = subparsers.add_parser('list', help='List recent results')
    list_parser.add_argument('--limit', type=int, default=10, help='Limit results')
    list_parser.add_argument('--failed', action='store_true', help='Show failed only')

    # Export JSON
    export_json = subparsers.add_parser('export-json', help='Export to JSON')
    export_json.add_argument('output', help='Output file path')

    # Export CSV
    export_csv = subparsers.add_parser('export-csv', help='Export to CSV')
    export_csv.add_argument('output', help='Output file path')

    # Domain summary
    subparsers.add_parser('domains', help='Show domain summary')

    # Clear old
    clear = subparsers.add_parser('clear', help='Clear old results')
    clear.add_argument('days', type=int, help='Clear results older than N days')

    # Reset
    subparsers.add_parser('reset', help='Reset database (removes all data)')

    args = parser.parse_args()

    cli = CrawlerCLI(db_path=args.db)

    if args.command == 'stats':
        stats = cli.get_stats()
        print("\n=== Crawl Statistics ===")
        for key, value in stats.items():
            print(f"{key}: {value}")

    elif args.command == 'list':
        cli.list_results(limit=args.limit, failed_only=args.failed)

    elif args.command == 'export-json':
        cli.export_json(args.output)

    elif args.command == 'export-csv':
        cli.export_csv(args.output)

    elif args.command == 'domains':
        if cli.domain_summary() is None:
            sys.exit(1)

    elif args.command == 'clear':
        cli.clear_old(days=args.days)

    elif args.command == 'reset':
        confirm = input("Are you sure? This will delete all crawl data. Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            cli.reset_database()
        else:
            print("Cancelled")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
