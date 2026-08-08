#!/usr/bin/env python3
"""
Bulk document ingestion script for Ultra Doc-Intelligence.

Recursively scans a directory for eligible documents (PDF, DOCX, TXT) and ingests them
into the system via the backend API.

Usage:
    python scripts/bulk_ingest.py <directory_path> [--api-url http://localhost:8000]
    python scripts/bulk_ingest.py /path/to/documents
    python scripts/bulk_ingest.py /path/to/documents --api-url http://192.168.1.100:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BulkIngester:
    """Handles bulk ingestion of documents via the backend API."""

    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        timeout: float = 300.0,
        max_concurrent: int = 3,
    ):
        """
        Initialize the bulk ingester.

        Args:
            api_url: Base URL of the backend API
            timeout: Timeout for each upload request in seconds
            max_concurrent: Maximum concurrent uploads
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.max_concurrent = max_concurrent
        self.session: Optional[httpx.AsyncClient] = None
        self.stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
        }

    async def __aenter__(self) -> BulkIngester:
        """Context manager entry."""
        self.session = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self.session:
            await self.session.aclose()

    def _find_documents(self, directory: Path) -> list[Path]:
        """
        Recursively find eligible documents in the directory.

        Args:
            directory: Path to search

        Returns:
            List of eligible document paths
        """
        documents = []
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.ALLOWED_EXTENSIONS:
                documents.append(path)
        return sorted(documents)

    async def _upload_document(self, file_path: Path) -> dict:
        """
        Upload a single document to the backend.

        Args:
            file_path: Path to the document file

        Returns:
            Response dict with status and details
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                logger.info(
                    f"Uploading: {file_path.name} ({file_size_mb:.2f} MB) ...",
                )

                response = await self.session.post(
                    f"{self.api_url}/upload",
                    files=files,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"  ✓ Success: {file_path.name} "
                        f"(doc_id={data.get('doc_id', 'unknown')[:8]}..., "
                        f"chunks={data.get('num_chunks', 0)}, "
                        f"type={data.get('doc_type', 'unknown')})"
                    )
                    return {
                        "status": "success",
                        "file": file_path.name,
                        "doc_id": data.get("doc_id"),
                        "num_chunks": data.get("num_chunks"),
                        "doc_type": data.get("doc_type"),
                        "processing_time_ms": data.get("processing_time_ms"),
                    }
                else:
                    error_msg = response.text or response.reason_phrase
                    logger.error(
                        f"  ✗ Failed: {file_path.name} "
                        f"(HTTP {response.status_code}: {error_msg[:100]})"
                    )
                    return {
                        "status": "failed",
                        "file": file_path.name,
                        "error": f"HTTP {response.status_code}",
                    }

        except FileNotFoundError:
            logger.error(f"  ✗ File not found: {file_path}")
            return {
                "status": "failed",
                "file": file_path.name,
                "error": "File not found",
            }
        except httpx.RequestError as e:
            logger.error(f"  ✗ Request error for {file_path.name}: {str(e)}")
            return {
                "status": "failed",
                "file": file_path.name,
                "error": f"Request error: {str(e)}",
            }
        except httpx.HTTPError as e:
            logger.error(f"  ✗ HTTP error for {file_path.name}: {str(e)}")
            return {
                "status": "failed",
                "file": file_path.name,
                "error": f"HTTP error: {str(e)}",
            }
        except Exception as e:
            logger.error(f"  ✗ Unexpected error for {file_path.name}: {str(e)}")
            return {
                "status": "failed",
                "file": file_path.name,
                "error": f"Unexpected error: {str(e)}",
            }

    async def ingest_directory(self, directory: Path) -> dict:
        """
        Ingest all eligible documents from a directory.

        Args:
            directory: Path to the directory to scan

        Returns:
            Summary statistics and results
        """
        directory = Path(directory)

        if not directory.is_dir():
            logger.error(f"Not a directory: {directory}")
            raise ValueError(f"Not a directory: {directory}")

        documents = self._find_documents(directory)

        if not documents:
            logger.warning(f"No eligible documents found in {directory}")
            return self.stats

        self.stats["total"] = len(documents)
        logger.info(
            f"Found {len(documents)} document(s) to ingest "
            f"(max concurrent: {self.max_concurrent})"
        )
        logger.info("-" * 80)

        results = []

        # Process documents with concurrency limit using semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def limited_upload(file_path: Path) -> dict:
            async with semaphore:
                return await self._upload_document(file_path)

        # Upload all documents concurrently
        tasks = [limited_upload(doc) for doc in documents]
        results = await asyncio.gather(*tasks)

        # Update statistics
        for result in results:
            if result["status"] == "success":
                self.stats["successful"] += 1
            elif result["status"] == "failed":
                self.stats["failed"] += 1
            else:
                self.stats["skipped"] += 1

        return results, self.stats

    def print_summary(self, stats: dict) -> None:
        """Print a summary of the ingestion results."""
        logger.info("-" * 80)
        logger.info("=" * 80)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total documents scanned:    {stats['total']}")
        logger.info(f"Successfully ingested:      {stats['successful']}")
        logger.info(f"Failed:                     {stats['failed']}")
        logger.info(f"Skipped:                    {stats['skipped']}")
        logger.info(f"Success rate:               {stats['successful']}/{stats['total']}")
        logger.info("=" * 80)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bulk ingest documents into Ultra Doc-Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/bulk_ingest.py ./documents
  python scripts/bulk_ingest.py /path/to/docs --api-url http://localhost:8000
  python scripts/bulk_ingest.py ./shipment-docs --api-url http://192.168.1.100:8000 --timeout 600
        """,
    )

    parser.add_argument(
        "directory",
        help="Directory containing documents to ingest",
        type=str,
    )
    parser.add_argument(
        "--api-url",
        help="Base URL of the backend API (default: http://localhost:8000)",
        default="http://localhost:8000",
        type=str,
    )
    parser.add_argument(
        "--timeout",
        help="Timeout for each upload in seconds (default: 300)",
        default=300,
        type=float,
    )
    parser.add_argument(
        "--max-concurrent",
        help="Maximum concurrent uploads (default: 3)",
        default=3,
        type=int,
    )
    parser.add_argument(
        "--output",
        help="Save results to JSON file",
        type=str,
        default=None,
    )

    args = parser.parse_args()

    directory = Path(args.directory)

    # Validate directory
    if not directory.exists():
        logger.error(f"Directory does not exist: {directory}")
        sys.exit(1)

    if not directory.is_dir():
        logger.error(f"Not a directory: {directory}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("ULTRA DOC-INTELLIGENCE: BULK DOCUMENT INGESTION")
    logger.info("=" * 80)
    logger.info(f"Directory:    {directory.resolve()}")
    logger.info(f"API URL:      {args.api_url}")
    logger.info(f"Timeout:      {args.timeout}s")
    logger.info(f"Concurrency:  {args.max_concurrent}")
    logger.info("=" * 80)

    try:
        async with BulkIngester(
            api_url=args.api_url,
            timeout=args.timeout,
            max_concurrent=args.max_concurrent,
        ) as ingester:
            results, stats = await ingester.ingest_directory(directory)

            # Save results if requested
            if args.output:
                output_path = Path(args.output)
                with open(output_path, "w") as f:
                    json.dump(
                        {
                            "stats": stats,
                            "results": results,
                        },
                        f,
                        indent=2,
                        default=str,
                    )
                logger.info(f"Results saved to: {output_path}")

            ingester.print_summary(stats)

            # Exit with error code if any failed
            if stats["failed"] > 0:
                sys.exit(1)

    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
