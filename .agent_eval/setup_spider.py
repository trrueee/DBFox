import os
import re
import zipfile
import shutil
from pathlib import Path
import requests

def download_large_gdrive_file(file_id, destination):
    print(f"Downloading from Google Drive ID: {file_id}...")
    url = f"https://docs.google.com/uc?export=download&id={file_id}"
    session = requests.Session()
    r = session.get(url)
    
    # Parse inputs from the warning form
    action_match = re.search(r'action="([^"]+)"', r.text)
    action_url = action_match.group(1) if action_match else "https://drive.usercontent.google.com/download"
    
    inputs = re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', r.text)
    params = {name: val for name, val in inputs}
    
    if "id" not in params:
        params["id"] = file_id
    if "export" not in params:
        params["export"] = "download"
    if "confirm" not in params:
        params["confirm"] = "t"
        
    print(f"Submitting warning confirmation to {action_url}...")
    resp = session.get(action_url, params=params, stream=True)
    
    CHUNK_SIZE = 32768
    with open(destination, "wb") as f:
        for chunk in resp.iter_content(CHUNK_SIZE):
            if chunk:
                f.write(chunk)
    print("Download complete.")

def main():
    eval_dir = Path(__file__).parent
    spider_dir = eval_dir / "spider"
    zip_path = eval_dir / "spider.zip"

    # Create directories
    spider_dir.mkdir(parents=True, exist_ok=True)

    # Check if tables.json already exists to avoid re-downloading
    if (spider_dir / "tables.json").exists() and (spider_dir / "dev.json").exists():
        print("Spider dataset already exists. Skipping download.")
        return

    # Download dataset
    download_large_gdrive_file("1TqleXec_OykOYFREKKtschzY29dUcVAQ", zip_path)

    # Unzip the dataset
    print(f"Extracting {zip_path} to {eval_dir}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(eval_dir)

    # Clean up zip
    if zip_path.exists():
        zip_path.unlink()

    # The zip might extract to a folder named "spider" or similar.
    # Let's inspect the files and move them if necessary so that they end up in .agent_eval/spider/
    extracted_spider_dir = eval_dir / "spider"
    if not (extracted_spider_dir / "tables.json").exists():
        # Check if there is another directory inside
        subdirs = [x for x in eval_dir.iterdir() if x.is_dir() and "spider" in x.name.lower()]
        for subdir in subdirs:
            if (subdir / "tables.json").exists():
                print(f"Moving files from {subdir} to {extracted_spider_dir}...")
                for item in subdir.iterdir():
                    target = extracted_spider_dir / item.name
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    item.rename(target)
                subdir.rmdir()
                break

    print("Spider dataset setup finished successfully!")

if __name__ == "__main__":
    main()
