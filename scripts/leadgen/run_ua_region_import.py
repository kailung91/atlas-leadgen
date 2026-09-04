import asyncio
import os
import sys
import uuid
import duckdb
from datetime import datetime, UTC
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import atlas_bootstrap  # noqa: F401,E402  корінь repo + atlas-maps
from importers.ua_region_scraper import UARegionScraper

def main():
    target_kveds = [
        '26.20', 
        '27.11', 
        '28.15', '28.22', '28.29', '28.30', '28.41', 
        '29.10', '29.32', 
        '30.30'
    ]
    output_dir = "data/raw/ua_region"
    
    print(f"Запуск скрапера для КВЕДів: {target_kveds}")
    scraper = UARegionScraper(kveds=target_kveds, output_dir=output_dir)
    scraper.run()
    
    print("\nЗбір завершено. Реєстрація SourceSnapshot...")
    
    con = duckdb.connect('dal_warehouse.duckdb')
    snapshot_id = f"snap_ua_region_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    
    total_records = 0
    total_size = 0
    
    for kved in target_kveds:
        file_path = Path(output_dir) / f"kved_{kved}.jsonl"
        if file_path.exists():
            total_size += file_path.stat().st_size
            with open(file_path, 'r', encoding='utf-8') as f:
                total_records += sum(1 for _ in f)
    
    con.execute("""
        INSERT INTO operations.source_snapshots 
        (snapshot_id, source_id, provider_version, url, size_bytes, record_count, downloaded_at)
        VALUES (?, 'ua_region_catalog', 'v1', 'https://www.ua-region.com.ua/', ?, ?, current_timestamp)
    """, [snapshot_id, total_size, total_records])
    
    print(f"Успішно зареєстровано SourceSnapshot: {snapshot_id}")
    print(f"Всього компаній: {total_records}")

if __name__ == "__main__":
    main()
