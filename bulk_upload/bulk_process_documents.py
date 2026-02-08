import os
import requests
import time

# ============================
# CONFIG
# ============================
API_BASE_URL = "https://api.chatbotdev.online/api/informational/v1/documents"
LIST_API_URL = f"{API_BASE_URL}?status=pending&limit=100"
PROCESS_API_TEMPLATE = f"{API_BASE_URL}/{{document_id}}/process"

TIMEOUT = 300  # detik
SLEEP_BETWEEN_REQUEST = 1  # detik (hindari overload server)

# ============================
# FUNCTIONS
# ============================

def fetch_pending_documents():
    """
    Ambil dokumen PENDING dari API
    """
    response = requests.get(LIST_API_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def process_document(document_id: int):
    """
    Call API process document
    """
    url = PROCESS_API_TEMPLATE.format(document_id=document_id)
    response = requests.post(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def main():
    print("📥 Fetching pending documents...")
    data = fetch_pending_documents()

    documents = data.get("data") or data.get("documents") or []
    total = len(documents)

    if total == 0:
        print("✅ No pending documents to process")
        return

    print(f"📄 Found {total} pending documents\n")

    success = 0
    failed = 0

    for idx, doc in enumerate(documents, start=1):
        document_id = doc["id"]
        filename = doc.get("filename", "-")

        print(f"⚙️  [{idx}/{total}] Processing ID={document_id} | {filename}")

        try:
            result = process_document(document_id)
            print(f"✅ SUCCESS | Pages: {result.get('total_pages')} | Text length: {result.get('text_length')}")
            success += 1

        except requests.exceptions.RequestException as e:
            print(f"❌ FAILED | ID={document_id} | Error: {str(e)}")
            failed += 1

        time.sleep(SLEEP_BETWEEN_REQUEST)

    print("\n============================")
    print("📊 BULK PROCESS SUMMARY")
    print("============================")
    print(f"Total     : {total}")
    print(f"Success   : {success}")
    print(f"Failed    : {failed}")
    print("============================")


# ============================
# ENTRY POINT
# ============================
if __name__ == "__main__":
    main()
