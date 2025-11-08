import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import date
from typing import List, Dict, Any, Optional

# --- Globals ---
db = None
bucket = None

def _init_firebase():
    """Initializes the Firebase Admin SDK."""
    global db, bucket
    
    # Check if already initialized
    if not firebase_admin._apps:
        try:
            # Use default service account key file
            cred = credentials.Certificate('serviceAccountKey.json')
            
            # Get the storage bucket from .env
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
            print("Please download it from Firebase Console and place it in the root.")
            raise
        except ValueError as e:
            print(f"ERROR: {e}")
            raise
    else:
        # Already initialized, just get the clients
        db = firestore.client()
        bucket = storage.bucket()


def get_today_str() -> str:
    """Returns today's date as 'YYYY-MM-DD'."""
    return date.today().strftime("%Y-%m-%d")

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
    word_data: List[tuple], # Firestore stores tuples as lists
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
        "word_data": word_data, # Firestore handles this fine
        "story": story,
        "feedback": feedback,
        "story_image_url": story_image_url
    }
    
    # .set() will create or overwrite the document
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
    # Order by date, newest first
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
        # Create a blob (file) in the bucket
        blob = bucket.blob(filename)
        
        # Upload the bytes
        blob.upload_from_string(
            image_bytes,
            content_type='image/png'
        )
        
        # Make the blob publicly accessible
        blob.make_public()
        
        # Return the public URL
        return blob.public_url
        
    except Exception as e:
        print(f"Error uploading image to Firebase Storage: {e}")
        return ""