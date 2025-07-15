import os
import csv
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CSV_FILE = "eliteprospects_active_players.csv"
CHECKPOINT_FILE = "checkpoint.txt"
GITHUB_REPO = "hassanzaidi-rl/elite-scraper"
GITHUB_BRANCH = "main"
GITHUB_PATH = "data/eliteprospects_active_players.csv"

def read_checkpoint():
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 1

def write_checkpoint(page):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(page))

def upload_to_github():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[X] GitHub token not found in environment variables.")
        return

    with open(CSV_FILE, "rb") as f:
        content = f.read()
    encoded_content = content.encode("base64") if hasattr(content, "encode") else content

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"

    # Get SHA if file already exists (for updating)
    sha = None
    get_response = requests.get(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    })
    if get_response.status_code == 200:
        sha = get_response.json().get("sha")

    data = {
        "message": f"Update player CSV: {datetime.utcnow().isoformat()}",
        "content": content.decode("utf-8").encode("base64").decode("utf-8") if isinstance(content, bytes) else encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        data["sha"] = sha

    response = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        },
        json=data
    )

    if response.status_code in [200, 201]:
        print("[✓] CSV uploaded to GitHub.")
    else:
        print("[X] Failed to upload CSV.")
        print(response.status_code, response.text)

def scrape_from_page(start_page):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page_num = start_page

        output_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, mode="a" if output_exists else "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not output_exists:
                writer.writerow([
                    "Name", "Position", "Nationality", "Age", "DOB",
                    "Jersey", "Height", "Weight", "Team", "Profile URL"
                ])

            while True:
                print(f"[→] Navigating to page {page_num}...")
                page.goto(f"https://www.eliteprospects.com/search/player?status=active&page={page_num}", timeout=30000)

                players = page.locator("table tbody tr")

                if players.count() == 0:
                    print("[✓] No more players.")
                    break

                for i in range(players.count()):
                    row = players.nth(i)
                    try:
                        name = row.locator("td:nth-child(1) a").inner_text()
                        position = row.locator("td:nth-child(3)").inner_text()
                        profile_url = row.locator("td:nth-child(1) a").get_attribute("href")
                        full_url = f"https://www.eliteprospects.com{profile_url}"

                        detail_page = browser.new_page()
                        try:
                            detail_page.goto(full_url, timeout=15000)
                            ul = detail_page.locator("ul.PlayerFacts_factsList__Xw_ID")

                            def get_fact(label):
                                li = ul.locator(f"li:has(span:text('{label}'))")
                                if li.count() > 0:
                                    return li.nth(0).inner_text().replace(label, "").strip()
                                return ""

                            def get_team():
                                try:
                                    subheader = detail_page.locator("div.Profile_headerSub__h_FJL h2.Profile_subTitlePlayer__drUwD")
                                    if subheader.count() > 0:
                                        return subheader.inner_text().split("/")[0].split()[-1]
                                    return ""
                                except:
                                    return ""

                            nationality = get_fact("Nation")
                            age = get_fact("Age")
                            dob = get_fact("Date of Birth")
                            jersey = get_fact("Jersey Number")
                            height = get_fact("Height")
                            weight = get_fact("Weight")
                            team = get_team()

                            writer.writerow([
                                name, position, nationality, age, dob,
                                jersey, height, weight, team, full_url
                            ])
                            print(f"[+] {page_num * 100 + i + 1}. Saved: Name: {name} | Position: {position} | Nationality: {nationality} | Age: {age} | DOB: {dob} | Jersey: {jersey} | Height: {height} | Weight: {weight} | Team: {team}")
                        except PlaywrightTimeout:
                            print(f"[!] Timeout for {name} ({position}): {full_url}")
                        finally:
                            detail_page.close()

                write_checkpoint(page_num)
                page_num += 1
        browser.close()

# Main runner
if __name__ == "__main__":
    checkpoint = read_checkpoint()
    scrape_from_page(checkpoint)
    upload_to_github()
