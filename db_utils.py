import os
import firebase_admin
import llm_utils  # Make sure llm_utils is imported
from firebase_admin import credentials, firestore, storage
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# --- Globals ---
db = None
bucket = None

def _init_firebase():
    """Initializes the Firebase Admin SDK."""
    global db, bucket
    
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate('serviceAccountKey.json')
            bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
            if not bucket_name:
                raise ValueError("FIREBASE_STORAGE_BUCKET not found in .env file.")
                
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })
            
            db = firestore.client()
            bucket = storage.bucket()
            print("Firebase Admin SDK initialized successfully.")
            
        except FileNotFoundError:
            print("ERROR: serviceAccountKey.json not found.")
            raise
        except ValueError as e:
            print(f"ERROR: {e}")
            raise
    else:
        db = firestore.client()
        bucket = storage.bucket()


def get_today_str() -> str:
    """Returns today's date in UTC as 'YYYY-MM-DD'."""
    utc_now = datetime.now(timezone.utc)
    return utc_now.strftime("%Y-%m-%d")

def get_challenge_for_date(date_str: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a challenge document from Firestore by its date (ID).
    """
    if not db:
        _init_firebase()
        
    doc_ref = db.collection('challenges').document(date_str)
    doc = doc_ref.get()
    
    if doc.exists:
        return doc.to_dict()
    else:
        return None

def save_challenge(
    date_str: str, 
    words: List[str], 
    word_data: List[Dict[str, Any]], # Changed to List[Dict]
    story: str, 
    feedback: str,
    story_image_url: str
):
    """
    Saves or updates a challenge in Firestore using the date as the document ID.
    """
    if not db:
        _init_firebase()
        
    doc_ref = db.collection('challenges').document(date_str)
    
    challenge_data = {
        "date": date_str,
        "words": words,
        "word_data": word_data, 
        "story": story,
        "feedback": feedback,
        "story_image_url": story_image_url
    }
    
    doc_ref.set(challenge_data)
    print(f"Challenge for {date_str} saved to Firestore.")


def get_all_used_words() -> set:
    """
    Gets all words that have been used in previous challenges from Firestore.
    """
    if not db:
        _init_firebase()
        
    used_words = set()
    docs = db.collection('challenges').stream()
    
    for doc in docs:
        data = doc.to_dict()
        if "words" in data and isinstance(data["words"], list):
            used_words.update(data["words"])
            
    return used_words

def get_all_challenges() -> List[Dict[str, Any]]:
    """
    Gets all challenge documents from Firestore, ordered by date descending.
    """
    if not db:
        _init_firebase()
        
    all_challenges = []
    query = db.collection('challenges').order_by('date', direction=firestore.Query.DESCENDING)
    docs = query.stream()
    
    for doc in docs:
        all_challenges.append(doc.to_dict())
        
    return all_challenges


def upload_image_to_storage(image_bytes: bytes, filename: str) -> str:
    """
    Uploads raw image bytes to Firebase Storage and returns the public URL.
    """
    if not bucket:
        _init_firebase()
        
    try:
        blob = bucket.blob(filename)
        blob.upload_from_string(
            image_bytes,
            content_type='image/png'
        )
        blob.make_public()
        return blob.public_url
        
    except Exception as e:
        print(f"Error uploading image to Firebase Storage: {e}")
        return ""

def get_all_used_idioms() -> set:
    """
    Scans the daily_idioms collection and returns a set of all idioms used so far.
    """
    if not db:
        _init_firebase()
        
    used_idioms = set()
    docs = db.collection('daily_idioms').stream()
    
    for doc in docs:
        data = doc.to_dict()
        if "idioms" in data and isinstance(data["idioms"], list):
            for idiom_obj in data["idioms"]:
                if "word" in idiom_obj:
                    used_idioms.add(idiom_obj["word"])
            
    return used_idioms

def get_or_create_daily_idioms(date_str: str) -> List[Dict[str, Any]]:
    """
    Fetches the daily idioms from Firestore. If they don't exist,
    it generates new, unique ones, saves them, and then returns them.
    This function now validates and cleans data read from the DB.
    """
    if not db:
        _init_firebase()
        
    doc_ref = db.collection('daily_idioms').document(date_str)
    doc = doc_ref.get()
    
    # --- THIS IS THE NEW, SAFER LOGIC ---
    
    def _clean_idiom_list(raw_idioms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """A helper to guarantee all fields exist."""
        clean_list = []
        for idiom in raw_idioms:
            clean_list.append({
                "word": idiom.get("word", "Error"),
                "ipa": idiom.get("ipa", "N/A"),
                "meaning": idiom.get("meaning", "Error loading"),
                "synonyms": idiom.get("synonyms", "N/A"),
                "antonyms": idiom.get("antonyms", "N/A"),
                "collocations": idiom.get("collocations", "N/A"),
                "sentences": idiom.get("sentences", []),
                "forms": idiom.get("forms", "N/A") # <-- Guarantees "forms" exists
            })
        return clean_list

    if doc.exists:
        # Data found. We MUST clean it before returning,
        # in case it's "dirty" data from a past error.
        raw_idioms_from_db = doc.to_dict().get("idioms", [])
        return _clean_idiom_list(raw_idioms_from_db)
    else:
        # Data not found. Generate, clean, save, and return.
        try:
            # 1. Get raw data from LLM
            raw_data_obj = llm_utils.get_daily_idioms(avoid_list=get_all_used_idioms())
            raw_idiom_list = raw_data_obj.get("idioms", [])
            
            # 2. Clean the data
            clean_idiom_list = _clean_idiom_list(raw_idiom_list)

            # 3. Create the object to save to DB
            clean_data_to_save = {"idioms": clean_idiom_list}
            
            # 4. Save the clean data
            doc_ref.set(clean_data_to_save) 
            
            # 5. Return the clean list
            return clean_idiom_list
            
        except Exception as e:
            print(f"Error generating and saving daily idioms: {e}")
            return []