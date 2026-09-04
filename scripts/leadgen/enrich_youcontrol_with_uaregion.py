import json
import re
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(r"D:\Codex\redactor\atlas-industry-engine")
YOUCONTROL_DIR = ROOT / "data" / "raw" / "youcontrol"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
IGNORE_DOMAINS = {"ua-region", "youcontrol", "opendatabot", "clarity", "w3.org", "schema", "example", "domain", "sentry"}

def search_uaregion_for_email(edrpou: str, name: str) -> tuple[str, str, str]:
    query = edrpou if edrpou and len(edrpou) >= 6 else name
    if not query:
        return edrpou, "", ""
        
    try:
        url = f"https://www.ua-region.com.ua/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            emails = [e.lower() for e in RE_EMAIL.findall(r.text) if not any(x in e.lower() for x in IGNORE_DOMAINS)]
            if emails:
                return edrpou, emails[0], url
    except Exception:
        pass
    return edrpou, "", ""

def main():
    records = []
    
    # Load 47.65 data
    for file_name in ["fop_47_65.jsonl", "kved_47_65.jsonl"]:
        file_path = YOUCONTROL_DIR / file_name
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
                            
    print(f"Loaded {len(records)} records from YouControl 47.65.")
    
    found_emails = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {
            executor.submit(search_uaregion_for_email, 
                            r.get("edrpou", "").strip().lstrip("0"), 
                            r.get("name", "").strip()): r 
            for r in records
        }
        
        for future in as_completed(future_map):
            r = future_map[future]
            ed, email, url = future.result()
            if email:
                found_emails += 1
                print(f"✅ Found email for {r.get('name')} ({ed}): {email}")
                
    print(f"\nTotal emails found via UA-Region for KVED 47.65: {found_emails}")

if __name__ == "__main__":
    main()
