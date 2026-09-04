import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import re

ROOT = Path(r"D:\Codex\redactor\atlas-industry-engine")
YOUCONTROL_DIR = ROOT / "data" / "raw" / "youcontrol"
OUTPUT_DIR = ROOT / "output"

def is_valid_email(email: str) -> bool:
    if not isinstance(email, str) or not email or "@" not in email:
        return False
    email = email.strip().lower()
    if any(email.endswith(sfx) for sfx in ('.ru', '.su', '.by', '.xn--p1ai')):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

def fetch_email_by_edrpou(edrpou: str) -> tuple[str, str]:
    if not edrpou or len(edrpou) < 6:
        return edrpou, ""
    try:
        res = requests.get(f"https://public.api.openprocurement.org/api/2.5/tenders?mode=_all_&opt_fields=procuringEntity&edrpou={edrpou}", timeout=4)
        if res.status_code == 200:
            for item in res.json().get("data", []):
                email = item.get("procuringEntity", {}).get("contactPoint", {}).get("email", "").strip()
                if is_valid_email(email):
                    return edrpou, email
    except Exception:
        pass
    return edrpou, ""

def main():
    edrpous = set()
    records = []
    
    # Load 47.65 data
    for file_name in ["fop_47_65.jsonl", "kved_47_65.jsonl"]:
        file_path = YOUCONTROL_DIR / file_name
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        edrpou = data.get("edrpou", "").strip().lstrip("0")
                        if len(edrpou) >= 6:
                            edrpous.add(edrpou)
                            records.append(data)
                            
    print(f"Loaded {len(edrpous)} unique EDRPOU codes from YouControl 47.65.")
    
    found_emails = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(fetch_email_by_edrpou, ed): ed for ed in edrpous}
        for future in as_completed(future_map):
            ed, email = future.result()
            if email:
                found_emails[ed] = email
                print(f"Found email for {ed}: {email}")
                
    print(f"Total emails found via Prozorro API for KVED 47.65: {len(found_emails)}")

if __name__ == "__main__":
    main()
