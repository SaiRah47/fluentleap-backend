from tinydb import TinyDB, Query
from datetime import date
from typing import List, Tuple, Any

DB_FILE = "db.json"
WORDS_PER_DAY = 5

db = TinyDB(DB_FILE)
challenge_table = db.table('challenges')
Challenge = Query()

def get_today_str():
    """Returns today's date as 'YYYY-MM-DD'."""
    return date.today().strftime("%Y-%m-%d")

def get_all_used_words():
    """Scans all challenges and returns a set of all words used so far."""
    result = set()
    for entry in challenge_table.all():
        result.update(entry.get('words', []))
    return result

def get_challenge_for_date(day_str):
    """Finds and returns the challenge record for a specific date."""
    return challenge_table.get(Challenge.date == day_str)

# --- UPDATED FUNCTION SIGNATURE ---
def save_challenge(day_str: str, 
                   words: List[str], 
                   word_data: List[Any], # Can be tuples or dicts
                   story: str = "", 
                   feedback: str = "", 
                   story_image_url: str = ""): # <-- THE NEW PARAMETER
    """
    Saves or updates a daily challenge, now including the image URL.
    """
    record = get_challenge_for_date(day_str)
    
    payload = {
        "date": day_str,
        "words": words,
        "word_data": word_data,
        "story": story,
        "feedback": feedback,
        "story_image_url": story_image_url # <-- THE NEW FIELD
    }
    
    if record:
        # If we're saving a story, we get all fields.
        # If we're just creating the day's words, the other fields are empty.
        # This simple update logic works for both cases.
        challenge_table.update(payload, doc_ids=[record.doc_id])
    else:
        # If no record exists, insert the full payload
        challenge_table.insert(payload)

def get_all_challenges():
    """Returns all challenge records, sorted by date descending."""
    return sorted(challenge_table.all(), key=lambda x: x['date'], reverse=True)


# Note: The lookup-related functions from your original file aren't
# used by the FastAPI app (which calls the LLM directly).
# I'm keeping them commented out in case you want to add that feature back.

# def get_lookups_table():
#     db = TinyDB("db.json")
#     return db.table('lookups')

# def save_lookup_word(word, meaning, synonyms, antonyms, sentence):
#     table = get_lookups_table()
#     table.insert({
#         "word": word,
#         "meaning": meaning,
#         "synonyms": synonyms,
#         "antonyms": antonyms,
#         "sentence": sentence
#     })

# def get_all_lookup_words():
#     table = get_lookups_table()
#     return table.all()