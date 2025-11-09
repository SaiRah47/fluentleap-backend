import json
import os
import uuid
import firebase_admin
from firebase_admin import credentials, firestore, storage
from typing import List, Dict, Any
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv() # Load variables from .env file
DB_JSON_FILE = "db.json"
SERVICE_ACCOUNT_KEY_FILE = "serviceAccountKey.json"
LOCAL_IMAGE_DIR = "image_storage"

# --- Globals ---
db = None
bucket = None

# --- Helper Function (copied from your main.py) ---
def _format_word_data(word_data_list: List[Any]) -> List[Dict[str, str]]:
    """
    Safely formats word data from TinyDB (list of lists) to a list of dicts.
    """
    formatted_data = []
    if not word_data_list:
        return formatted_data
        
    for item in word_data_list:
        if isinstance(item, (list, tuple)) and len(item) >= 6:
            formatted_data.append({
                "word": item[0] if len(item) > 0 else "",
                "ipa": item[1] if len(item) > 1 else "",
                "meaning": item[2] if len(item) > 2 else "",
                "synonyms": item[3] if len(item) > 3 else "",
                "antonyms": item[4] if len(item) > 4 else "",
                "sentence": item[5] if len(item) > 5 else ""
            })
        elif isinstance(item, dict):
            formatted_data.append(item)
    return formatted_data

# --- Firebase & Storage Functions ---
def _init_firebase():
    """Initializes the Firebase Admin SDK for Firestore AND Storage."""
    global db, bucket
    
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_FILE)
            bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
            
            if not bucket_name:
                raise ValueError("FIREBASE_STORAGE_BUCKET not found in .env file. Please check it.")
                
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })
            
            db = firestore.client()
            bucket = storage.bucket()
            print("✓ Firebase initialized successfully (Firestore & Storage).")
            
        except FileNotFoundError:
            print(f"🔥 ERROR: '{SERVICE_ACCOUNT_KEY_FILE}' not found.")
            raise
        except ValueError as e:
            print(f"🔥 ERROR: {e}")
            raise

def upload_image_to_storage(image_bytes: bytes, filename: str) -> str:
    """
    Uploads raw image bytes to Firebase Storage and returns the public URL.
    """
    if not bucket:
        _init_firebase()
    try:
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type='image/png')
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"  -> 🔥 Error uploading to Firebase Storage: {e}")
        return ""

# --- Main Migration Logic ---
def migrate_data():
    print("Starting migration (with image upload)...")
    
    try:
        _init_firebase()
    except Exception as e:
        print("Migration aborted.")
        return

    # 1. Read db.json
    try:
        with open(DB_JSON_FILE, 'r') as f:
            data = json.load(f)
        
        # Handle TinyDB's two possible formats
        challenges = []
        if 'challenges' in data and isinstance(data['challenges'], dict):
            challenges = data.get('challenges', {}).values() # Old format
        elif 'challenges' in data and isinstance(data['challenges'], list):
            challenges = data['challenges'] # New format
        
        if not challenges:
            print(f"🔥 ERROR: Could not find 'challenges' in {DB_JSON_FILE}.")
            return
                
        print(f"✓ Read {len(list(challenges))} entries from {DB_JSON_FILE}.")
        
    except FileNotFoundError:
        print(f"🔥 ERROR: {DB_JSON_FILE} not found.")
        return
    except Exception as e:
        print(f"🔥 ERROR: Could not read {DB_JSON_FILE}. Details: {e}")
        return

    # 2. Loop and Upload to Firestore
    challenge_collection = db.collection('challenges')
    success_count = 0
    fail_count = 0
    
    print("Beginning upload to Firestore...")

    for entry in challenges:
        try:
            date_str = entry.get("date")
            if not date_str:
                print(f"Warning: Skipping entry with no date: {entry}")
                fail_count += 1
                continue
            
            print(f"\nProcessing entry for {date_str}...")
            
            # --- Image Migration Logic ---
            new_image_url = "" # Default to empty
            old_image_url = entry.get("story_image_url", "")
            
            if old_image_url:
                # 1. Find local file
                filename = old_image_url.replace("/images/", "")
                local_path = os.path.join(LOCAL_IMAGE_DIR, filename)
                
                if os.path.exists(local_path):
                    print(f"  -> Found local image: {local_path}")
                    
                    # 2. Read file bytes
                    with open(local_path, "rb") as f:
                        image_bytes = f.read()
                    
                    # 3. Upload to Firebase
                    new_firebase_filename = f"story-images/migrated-{date_str}-{uuid.uuid4()}.png"
                    new_image_url = upload_image_to_storage(image_bytes, new_firebase_filename)
                    
                    if new_image_url:
                        print(f"  -> ✓ Successfully uploaded to: {new_image_url}")
                    else:
                        print(f"  -> 🔥 Failed to upload image.")
                else:
                    print(f"  -> Warning: Image file not found at {local_path}. Skipping image.")
            # --- End Image Logic ---

            # Format word_data from list-of-lists to list-of-dicts
            formatted_word_data = _format_word_data(entry.get("word_data", []))

            # Create the final payload for Firestore
            payload = {
                "date": date_str,
                "words": entry.get("words", []),
                "word_data": formatted_word_data,
                "story": entry.get("story", ""),
                "feedback": entry.get("feedback", ""),
                "story_image_url": new_image_url # Use the new URL
            }
            
            # Use the date as the document ID to prevent duplicates
            doc_ref = challenge_collection.document(date_str)
            doc_ref.set(payload)
            
            print(f"  -> ✓ Uploaded data for {date_str}")
            success_count += 1
            
        except Exception as e:
            print(f"🔥 ERROR uploading entry for {date_str}: {e}")
            fail_count += 1

    print("\n--- Migration Complete ---")
    print(f"✅ Successful uploads: {success_count}")
    print(f"❌ Failed uploads: {fail_count}")

# --- Run the script ---
if __name__ == "__main__":
    migrate_data()