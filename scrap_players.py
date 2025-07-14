# scrap_players.py
import csv
import os
import time
from playwright.sync_api import sync_playwright

CSV_FILE = "eliteprospects_active_players.csv"
CHECKPOINT_FILE = "checkpoint.txt"
BASE_URL = "https://www.eliteprospects.com"
RESTART_INTERVAL = 25

def get_checkpoint():
    return int(open(CHECKPOINT_FILE).read().strip()) if os.path.exists(CHECKPOINT_FILE) else 1

def save_checkpoint(page_num):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(page_num))

def extract_profile_data(page):
    jersey = height = weight = age = nationality = position = dob = team = ""

    try:
        # Jersey number & team
        jersey_block = page.query_selector("h2.Profile_subTitlePlayer__drUwD")
        if jersey_block:
            jersey_text = jersey_block.inner_text().strip()
            if jersey_text.startswith("#"):
                jersey = jersey_text.split(" ")[0].replace("#", "")

            # Extract team name from first <a> inside jersey_block
            team_link = jersey_block.query_selector("a")
            if team_link:
                team = team_link.inner_text().strip()

        # Player facts
        facts = page.query_selector_all("ul.PlayerFacts_factsList__Xw_ID > li")
        for fact in facts:
            label_elem = fact.query_selector(".PlayerFacts_factLabel__EqzO5")
            if not label_elem:
                continue

            label = label_elem.inner_text().strip().lower()

            if label == "nation":
                nation_elem = fact.query_selector("div a")
                if nation_elem:
                    nationality = nation_elem.inner_text().strip()

            elif label == "age":
                value = label_elem.evaluate("node => node.nextSibling && node.nextSibling.textContent")
                if value and "premium" not in value.lower():
                    age = value.strip()

            elif label == "position":
                value = label_elem.evaluate("node => node.nextSibling && node.nextSibling.textContent")
                if value:
                    position = value.strip()

            elif label == "height":
                height = fact.inner_text().replace(label_elem.inner_text(), "").strip()

            elif label == "weight":
                weight = fact.inner_text().replace(label_elem.inner_text(), "").strip()

            elif label == "date of birth":
                dob_elem = fact.query_selector("a")
                if dob_elem:
                    dob = dob_elem.inner_text().strip()

    except Exception as e:
        print(f"[!] Failed to extract full profile data: {e}")

    return jersey, height, weight, age, nationality, position, dob, team


def scrape_from_page(start_page):
    scraped_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="storage_state.json")
        page = context.new_page()
        profile_page = context.new_page()

        output_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Position", "Nationality", "Age", "DOB", "Jersey", "Height", "Weight", "Team", "Profile URL"])

            for page_num in range(start_page, 999999):
                print(f"[→] Navigating to page {page_num}...")
                try:
                    page.goto(f"{BASE_URL}/search/player?status=active&page={page_num}", timeout=60000)
                    page.wait_for_selector("table.table", timeout=10000)
                except:
                    print("[✓] No more results or failed to load table.")
                    break

                rows = page.query_selector_all("table tbody tr")
                if not rows:
                    print("[✓] No players on this page. Ending.")
                    break

                for row in rows:

                    cols = row.query_selector_all("td")
                    if len(cols) < 5:
                        continue

                    name_link = cols[0].query_selector("a")
                    if not name_link:
                        continue

                    try:
                        raw_href = name_link.get_attribute("href")
                        profile_url = raw_href if raw_href.startswith("http") else BASE_URL + raw_href
                        name = name_link.inner_text().strip()
                        dob = cols[4].inner_text().strip()
                        list_position = cols[1].inner_text().strip()  # table-listed position
                    except Exception as e:
                        print(f"[!] Failed to parse row: {e}")
                        continue

                    try:
                        profile_page.goto(profile_url, timeout=15000)
                        profile_page.wait_for_selector("h1", timeout=5000)
                        jersey, height, weight, age, nationality, profile_position, dob, team = extract_profile_data(profile_page)
                        position = profile_position or list_position
                    except Exception as e:
                        print(f"[!] Failed to extract player info for {name}: {e}")
                        jersey = height = weight = age = nationality = position = ""
                        dob = team = ""  # ✅ This prevents the crash


                    writer.writerow([name, position, nationality, age, dob, jersey, height, weight, team, profile_url])
                    f.flush()
                    scraped_count += 1
                    print(f"[+] {scraped_count}. Saved: "
                    f"Name: {name} | "
                    f"Position: {position} | "
                    f"Nationality: {nationality} | "
                    f"Age: {age} | "
                    f"DOB: {dob} | "
                    f"Jersey: {jersey} | "
                    f"Height: {height} | "
                    f"Weight: {weight} | "
                    f"Team: {team}")

                    time.sleep(0.2)

                save_checkpoint(page_num)
                time.sleep(1)

                if (page_num - start_page + 1) % RESTART_INTERVAL == 0:
                    print(f"[🔄] Restarting browser at page {page_num + 1} to clear memory.")
                    profile_page.close()
                    page.close()
                    browser.close()
                    return page_num + 1

        profile_page.close()
        page.close()
        browser.close()
        print("[✓] Scraping completed.")
        return None

if __name__ == "__main__":
    while True:
        checkpoint = get_checkpoint()
        next_page = scrape_from_page(checkpoint)
        if not next_page:
            break
        save_checkpoint(next_page)
