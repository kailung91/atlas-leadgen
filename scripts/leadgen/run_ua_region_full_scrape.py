import sys
import json
import time
import duckdb
from datetime import datetime, UTC
from pathlib import Path
from typing import List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atlas_bootstrap  # noqa: F401,E402  корінь repo + atlas-maps
from importers.ua_region_scraper import UARegionScraper

def load_catalog(catalog_path: str = "config/kved_catalog.json") -> Dict:
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_group_scraping(group_id: str = None, output_dir: str = "data/raw/ua_region_full", temp_dir: str = "data/raw/ua_region_full/temp"):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    catalog = load_catalog()
    groups = catalog.get("priority_groups", [])
    
    target_groups = []
    if group_id:
        target_groups = [g for g in groups if g["id"] == group_id]
    else:
        target_groups = groups

    out_path = Path(output_dir)
    tmp_path = Path(temp_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    tmp_path.mkdir(parents=True, exist_ok=True)

    print("==================================================================")
    print("START SCRAPING UA-REGION")
    print(f"Target dir: {out_path.resolve()}")
    print(f"Temp dir: {tmp_path.resolve()}")
    print("==================================================================\n")

    total_scraped_records = 0
    start_time = datetime.now()

    for grp in target_groups:
        grp_name = grp["name"]
        codes = grp["codes"]
        print(f"\n[GROUP] {grp_name} ({len(codes)} KVED codes)")
        print(f"   Codes: {', '.join(codes[:10])}{'...' if len(codes) > 10 else ''}")

        scraper = UARegionScraper(
            kveds=codes,
            output_dir=str(out_path),
            temp_dir=str(tmp_path)
        )
        scraper.run()

    # Register snapshot in DuckDB
    con = duckdb.connect('dal_warehouse.duckdb')
    snapshot_id = f"snap_ua_region_full_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    
    total_records = 0
    total_size = 0
    
    for jsonl_file in out_path.glob("kved_*.jsonl"):
        total_size += jsonl_file.stat().st_size
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            total_records += sum(1 for _ in f)

    con.execute("""
        INSERT INTO operations.source_snapshots 
        (snapshot_id, source_id, provider_version, url, size_bytes, record_count, downloaded_at)
        VALUES (?, 'ua_region_priority_catalog', 'v2_full', 'https://www.ua-region.com.ua/', ?, ?, current_timestamp)
    """, [snapshot_id, total_size, total_records])

    elapsed = datetime.now() - start_time
    print("\n==================================================================")
    print(f"SCRAPING COMPLETED IN {elapsed}")
    print(f"Registered snapshot_id: {snapshot_id}")
    print(f"Total saved records: {total_records}")
    print(f"Total data size: {total_size / (1024*1024):.2f} MB")
    print("==================================================================")

if __name__ == "__main__":
    group_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_group_scraping(group_arg)
