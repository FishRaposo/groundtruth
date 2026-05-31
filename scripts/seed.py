"""Seed script for loading sample data into GroundTruth."""

import argparse
import sys
import time
from pathlib import Path

import httpx

SUPPORTED_EXTENSIONS = {".md", ".html", ".pdf", ".docx"}
POLL_INTERVAL = 2
POLL_TIMEOUT = 300


def discover_files(data_dir: Path) -> list[Path]:
    """Find all supported document files in the data directory."""
    files: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(sorted(data_dir.glob(f"*{ext}")))
    return files


def clean_existing(api_url: str, client: httpx.Client) -> None:
    """Delete all existing documents via the API."""
    response = client.get(f"{api_url}/api/documents", params={"limit": 1000})
    response.raise_for_status()
    data = response.json()
    documents = data.get("documents", [])
    for doc in documents:
        doc_id = doc["id"]
        print(f"  Deleting {doc['title']} ({doc_id})...")
        delete_response = client.delete(f"{api_url}/api/documents/{doc_id}")
        delete_response.raise_for_status()
    print(f"  Deleted {len(documents)} existing documents.")


def upload_file(api_url: str, file_path: Path, client: httpx.Client) -> str | None:
    """Upload a single file and return its document ID."""
    with open(file_path, "rb") as f:
        files = {"files": (file_path.name, f)}
        response = client.post(f"{api_url}/api/documents/upload", files=files)
    if response.status_code != 200:
        print(f"  FAILED to upload {file_path.name}: {response.text}")
        return None
    data = response.json()
    documents = data.get("documents", [])
    if not documents:
        print(f"  No document returned for {file_path.name}")
        return None
    return str(documents[0]["id"])


def poll_until_ready(
    api_url: str, document_id: str, client: httpx.Client
) -> str:
    """Poll document status until ready or error, with timeout."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        response = client.get(f"{api_url}/api/documents/{document_id}")
        if response.status_code != 200:
            print(f"  Warning: status check failed for {document_id}")
            return "error"
        status = response.json().get("status", "unknown")
        if status in ("ready", "error"):
            return status
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    print(f"  Timeout waiting for document {document_id}")
    return "timeout"


def main() -> int:
    """Run the seed script."""
    parser = argparse.ArgumentParser(description="Seed GroundTruth with sample data")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the GroundTruth API",
    )
    parser.add_argument(
        "--data-dir",
        default="./data/sample",
        help="Directory containing sample documents",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete existing documents before seeding",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"Data directory not found: {data_dir}")
        return 1

    files = discover_files(data_dir)
    if not files:
        print(f"No supported files found in {data_dir}")
        return 1

    print(f"Found {len(files)} file(s) to seed.")
    api_url = args.api_url.rstrip("/")

    with httpx.Client(timeout=30) as client:
        health = client.get(f"{api_url}/api/health")
        if health.status_code != 200:
            print(f"API not healthy at {api_url}")
            return 1
        print("API is healthy.")

        if args.clean:
            print("Cleaning existing documents...")
            clean_existing(api_url, client)

        succeeded: list[str] = []
        failed: list[str] = []

        for file_path in files:
            print(f"\nUploading {file_path.name}...")
            doc_id = upload_file(api_url, file_path, client)
            if doc_id is None:
                failed.append(file_path.name)
                continue

            print(f"  Document ID: {doc_id}")
            print(f"  Waiting for processing...")
            status = poll_until_ready(api_url, doc_id, client)
            if status == "ready":
                print(f"  Done: {file_path.name} -> ready")
                succeeded.append(file_path.name)
            else:
                print(f"  Failed: {file_path.name} -> {status}")
                failed.append(file_path.name)

    print(f"\n{'=' * 50}")
    print(f"Seed complete: {len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        print(f"Failed files: {', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
