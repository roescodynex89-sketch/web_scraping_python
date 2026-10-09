import requests
from bs4 import BeautifulSoup
import re
import urllib3
import pdfplumber
import csv
import sqlite3
import os
import io
from datetime import datetime
from urllib.parse import urljoin


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

CSV_FILE = "rice_market_intelligence.csv"
DB_FILE = "rice_market.db"


def download_and_parse_pdf(pdf_url):
    """PDF ডাউনলোড করে তার ভেতর থেকে ধান/চাল ও শুল্ক সংক্রান্ত টেক্সট এক্সট্র্যাক্ট করে"""
    if not pdf_url or pdf_url == "N/A" or pdfplumber is None:
        return "PDF Parse Skipped or pdfplumber Not Installed"

    try:
        session = requests.Session()
        # NBR সেশন কুকি নেওয়ার জন্য মেইন পেজে ফ্রন্ট রিকোয়েস্ট
        session.get("https://nbr.gov.bd", headers=HEADERS, verify=False, timeout=10)

        pdf_headers = HEADERS.copy()
        pdf_headers["Referer"] = "https://nbr.gov.bd/"

        response = session.get(pdf_url, headers=pdf_headers, verify=False, timeout=25)

        if response.status_code == 200:
            # ইন-মেমোরি থেকে PDF পার্স করা
            with pdfplumber.open(io.BytesIO(response.content)) as pdf:
                full_text = ""
                for page in pdf.pages[:3]:  # প্রথম ৩টি পেজ পড়া হচ্ছে
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"

            # চাল, ধান, শুল্ক, ভ্যাট রিলেটেড লাইন ফিল্টার
            keywords = ["rice", "paddy", "চাল", "ধান", "customs duty", "regulatory duty", "cd", "rd", "vat", "ভ্যাট"]
            matched_lines = []

            for line in full_text.split('\n'):
                line_str = line.strip()
                if any(k in line_str.lower() for k in keywords):
                    matched_lines.append(line_str)

            if matched_lines:
                # সেরা ৩-৪টি প্রাসঙ্গিক লাইন সামারি হিসেব রাখা
                summary = " | ".join(matched_lines[:4])
                return summary[:400]  # অতিরিক্ত বড় টেক্সট ছোট করা
            else:
                return "PDF Read Successful (No specific rice/duty keywords found in text)"
        else:
            return f"PDF Download Failed (HTTP {response.status_code})"

    except Exception as e:
        return f"PDF Parse Error: {str(e)[:100]}"


def fetch_rice_market_data():
    results = {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nbr_sro_no": "N/A",
        "nbr_pdf_url": "N/A",
        "pdf_summary": "N/A",
        "dgfood_bulletin_url": "https://dgfood.gov.bd/pages/downloads/6922dab8dbfbab28ce055f1a",
        "status": "Success"
    }

    # ---------------------------------------------------------
    # ১. NBR Customs SRO (HTML Extraction)
    # ---------------------------------------------------------
    try:
        nbr_url = "https://nbr.gov.bd/regulations/sros/customs-sros/eng"
        r = requests.get(nbr_url, headers=HEADERS, verify=False, timeout=15)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')

            pdf_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '.pdf' in href.lower() or 'uploads' in href.lower():
                    title = a.get_text().strip() or "Customs SRO PDF"
                    full_link = urljoin("https://nbr.gov.bd", href)
                    pdf_links.append((title, full_link))

            if pdf_links:
                results["nbr_sro_no"] = pdf_links[0][0][:60]
                results["nbr_pdf_url"] = pdf_links[0][1]

                print(f"📥 PDF পাওয়া গেছে, ডাউনলোড ও রিড করা হচ্ছে: {results['nbr_pdf_url']}")
                results["pdf_summary"] = download_and_parse_pdf(results["nbr_pdf_url"])
            else:
                results["nbr_sro_no"] = "Customs SRO Page Active"
                results["nbr_pdf_url"] = nbr_url
        else:
            results["nbr_sro_no"] = f"HTTP {r.status_code}"
            results["nbr_pdf_url"] = nbr_url

    except Exception as e:
        results["nbr_sro_no"] = "Fetch Error"
        results["status"] = f"NBR Error: {e}"

    return results


def save_to_csv(data):
    file_exists = os.path.isfile(CSV_FILE)
    fieldnames = ["scraped_at", "nbr_sro_no", "nbr_pdf_url", "pdf_summary", "dgfood_bulletin_url", "status"]

    with open(CSV_FILE, mode='a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)
    print(f"✅ CSV সফলভাবে তৈরি ও আপডেট হয়েছে: {CSV_FILE}")


def import_csv_to_db():
    if not os.path.exists(CSV_FILE):
        print("❌ CSV ফাইল পাওয়া যায়নি!")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at TEXT,
            nbr_sro_no TEXT,
            nbr_pdf_url TEXT,
            pdf_summary TEXT,
            dgfood_bulletin_url TEXT,
            status TEXT
        )
    ''')

    with open(CSV_FILE, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            cursor.execute("SELECT 1 FROM market_data WHERE nbr_pdf_url = ? AND scraped_at = ?", 
                           (row["nbr_pdf_url"], row["scraped_at"]))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO market_data (scraped_at, nbr_sro_no, nbr_pdf_url, pdf_summary, dgfood_bulletin_url, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (row["scraped_at"], row["nbr_sro_no"], row["nbr_pdf_url"], row.get("pdf_summary", "N/A"), row["dgfood_bulletin_url"], row["status"]))
                count += 1

    conn.commit()
    conn.close()
    print(f"✅ {count}টি নতুন তথ্য (PDF সামারিসহ) SQLite ডাটাবেজে ({DB_FILE}) সেভ হয়েছে।")


if __name__ == "__main__":
    print("১. ডাটা সংগ্রহ ও PDF রিড করা হচ্ছে...")
    data = fetch_rice_market_data()

    print("\n২. CSV ফাইলে সেভ করা হচ্ছে...")
    save_to_csv(data)

    print("\n৩. CSV ফাইলটি ওপেন করে দেখুন (pdf_summary কলামে PDF-এর টেক্সট এসেছে)। ডাটাবেজে ইমপোর্ট করতে 'y' চাপুন:")
    user_input = input("DB-তে পাঠাতে চান? (y/n): ")
    if user_input.lower() == 'y':
        import_csv_to_db()
    else:
        print("প্রসেস সম্পন্ন! ডাটা শুধু CSV-তেই রাখা হলো।")