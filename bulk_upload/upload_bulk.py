import os
import shutil
import requests

# ============================
# BASE DIRECTORY (lokasi file ini)
# ============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================
# CONFIG
# ============================
API_URL = "https://api.chatbotdev.online/api/informational/v1/documents/upload"

INPUT_DIR = os.path.join(BASE_DIR, "input")
SUCCESS_DIR = os.path.join(BASE_DIR, "success")
FAILED_DIR = os.path.join(BASE_DIR, "failed")

# ============================
# FUNCTION UPLOAD
# ============================
def upload_file(file_path):
    with open(file_path, "rb") as f:
        files = {
            "file": (os.path.basename(file_path), f, "application/pdf")
        }
        response = requests.post(API_URL, files=files)

    return response

# ============================
# MAIN PROCESS
# ============================
def main():
    files = [
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not files:
        print("❌ Tidak ada file PDF ditemukan")
        return

    for filename in files:
        file_path = os.path.join(INPUT_DIR, filename)
        print(f"📤 Uploading: {filename}")

        try:
            response = upload_file(file_path)

            if response.status_code == 200:
                data = response.json()

                if data.get("success"):
                    shutil.move(file_path, os.path.join(SUCCESS_DIR, filename))
                    print(f"✅ Success → moved to success/: {filename}")
                else:
                    shutil.move(file_path, os.path.join(FAILED_DIR, filename))
                    print(f"⚠️ API failed → moved to failed/: {filename}")

            else:
                shutil.move(file_path, os.path.join(FAILED_DIR, filename))
                print(f"❌ HTTP {response.status_code} → moved to failed/: {filename}")

        except Exception as e:
            shutil.move(file_path, os.path.join(FAILED_DIR, filename))
            print(f"🔥 Error {filename}: {str(e)}")

if __name__ == "__main__":
    main()
