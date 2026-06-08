import json
from pathlib import Path

def main():
    dev_path = Path(__file__).parent / "spider" / "dev.json"
    with open(dev_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Let's see some concert_singer and pets_1 cases
    target_dbs = ["concert_singer", "pets_1"]
    filtered = [c for c in cases if c["db_id"] in target_dbs]
    
    # Print them grouped by db_id
    dbs = {}
    for c in filtered:
        dbs.setdefault(c["db_id"], []).append(c)
        
    for db, list_cases in dbs.items():
        print(f"\n================ DB: {db} (Total cases: {len(list_cases)}) ================")
        # Print first 20 cases with index
        for idx, c in enumerate(list_cases[:20]):
            print(f"Index {idx}: Q: {c['question']}")
            print(f"         SQL: {c['query']}")

if __name__ == "__main__":
    main()
