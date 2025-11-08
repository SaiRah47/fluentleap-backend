import random
import io
import re
import json
import os
import base64
import uuid
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from gtts import gTTS

# Import your existing logic files
import db_utils
import llm_utils

# --- Constants ---
WORDS_PER_DAY = 5
OXFORD_WORDS_PATH = "oxford_5000.txt"

# --- (THIS IS THE FIX) ---
# Initialize Firebase on app startup
db_utils._init_firebase()
# --- (END OF FIX) ---

# --- App Setup ---
app = FastAPI(
    title="FluentLeap API",
    description="English vocabulary learning API",
    version="1.0.0"
)

# NOTE: We no longer need the /images static mount
# os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)
# app.mount("/images", StaticFiles(directory=IMAGE_STORAGE_DIR), name="images")


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# --- Pydantic Models ---
class StoryRequest(BaseModel):
    story: str

class WordData(BaseModel):
    word: str
    ipa: str
    meaning: str
    synonyms: str
    antonyms: str
    sentence: str

class ChallengeResponse(BaseModel):
    date: str
    words: List[str]
    word_data: List[WordData]
    story: str
    feedback: str
    story_image_url: Optional[str] = None

class FeedbackResponse(BaseModel):
    feedback: str

class LookupResponse(BaseModel):
    word: str
    ipa: str
    meaning: str
    synonyms: str
    antonyms: str
    sentence: str

class GrammarProblem(BaseModel):
    id: int
    incorrect: str
    correct: str

class GrammarChallenge(BaseModel):
    title: str
    description: str
    problems: List[GrammarProblem]


# --- Helper Function ---
def _format_word_data(word_data_list: List[Any]) -> List[Dict[str, str]]:
    """
    Safely formats word data from Firestore (list of lists) to a list of dicts.
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


# --- API Endpoints ---

@app.get("/api/today", response_model=ChallengeResponse)
async def get_today_challenge():
    """
    Gets today's 5 words. If they haven't been generated,
    it creates, saves, and returns them.
    """
    today_str = db_utils.get_today_str()
    # Now reads from Firestore
    today_record = db_utils.get_challenge_for_date(today_str) 

    if today_record:
        # Challenge already exists - format word_data
        today_record["word_data"] = _format_word_data(today_record.get("word_data", []))
        return today_record
    else:
        # Create new challenge
        try:
            with open(OXFORD_WORDS_PATH) as f:
                all_words = [line.strip() for line in f if line.strip() and line[0].isalpha()]
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"Word list file '{OXFORD_WORDS_PATH}' not found")
        
        # Now reads from Firestore
        all_used_words = db_utils.get_all_used_words()
        unused = list(set(all_words) - set(all_used_words))
        
        todays_words = []
        if len(unused) >= WORDS_PER_DAY:
            todays_words = random.sample(unused, WORDS_PER_DAY)
        elif 0 < len(unused) < WORDS_PER_DAY:
            todays_words = random.sample(unused, len(unused))
        else:
            print("Warning: All unique words have been used. Resetting word list.")
            todays_words = random.sample(all_words, WORDS_PER_DAY)

        if todays_words:
            todays_word_data_tuples = llm_utils.get_llm_vocab_batch(todays_words)
            formatted_word_data = _format_word_data(todays_word_data_tuples)
            
            # Save the new challenge to Firestore
            db_utils.save_challenge(
                today_str, 
                todays_words, 
                formatted_word_data, # <--- THIS IS THE FIX (was todays_word_data_tuples)
                story="",
                feedback="",
                story_image_url=""
            )
            
            return {
                "date": today_str,
                "words": todays_words,
                "word_data": formatted_word_data,
                "story": "",
                "feedback": "",
                "story_image_url": ""
            }
        else:
            raise HTTPException(status_code=500, detail="No words available to load")

@app.post("/api/story", response_model=FeedbackResponse)
async def save_story(story_request: StoryRequest):
    """
    Receives a story, gets feedback, GENERATES AN IMAGE, and saves all to DB.
    """
    story = story_request.story
    if not story:
        raise HTTPException(status_code=400, detail="No story provided")

    today_str = db_utils.get_today_str()
    today_record = db_utils.get_challenge_for_date(today_str)
    
    if not today_record:
        raise HTTPException(status_code=404, detail="Today's challenge not found. Please GET /api/today first.")

    # 1. Get text feedback (from Gemini)
    feedback = llm_utils.get_story_feedback(story)
    
    story_image_url = "" # Default empty string
    
    # 2. Generate image with Gemini
    image_bytes = llm_utils.generate_image_with_gemini(story)
    
    if image_bytes:
        try:
            # --- (THIS IS THE FIX) ---
            # 3. Create a unique filename
            filename = f"story-images/story-{today_str}-{uuid.uuid4()}.png"
            
            # 4. Upload to Firebase Storage
            story_image_url = db_utils.upload_image_to_storage(image_bytes, filename)
            
            if story_image_url:
                print(f"Image uploaded to: {story_image_url}")
            else:
                print("Error: Image upload failed, URL is empty.")
            # --- (END OF FIX) ---
            
        except Exception as e:
            print(f"Error saving image: {str(e)}")

    # 5. Save everything to Firestore
    # NOTE: We must pass _format_word_data to save_challenge,
    # because the record from the DB `today_record.get("word_data", [])`
    # is already formatted as a list of dicts.
    db_utils.save_challenge(
        today_str, 
        today_record["words"], 
        _format_word_data(today_record.get("word_data", [])),
        story, 
        feedback,
        story_image_url # <-- Pass the new public URL
    )
    
    return {"feedback": feedback}

@app.get("/api/lookup", response_model=LookupResponse)
async def lookup_word_endpoint(word: str = Query(..., description="Word to lookup")):
    # This endpoint needs no changes
    if not word:
        raise HTTPException(status_code=400, detail="No word parameter provided")
    try:
        data = llm_utils.lookup_word(word)
        response_data = {
            "word": data[0], "ipa": data[1], "meaning": data[2],
            "synonyms": data[3], "antonyms": data[4], "sentence": data[5]
        }
        return response_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to lookup word: {str(e)}")

@app.get("/api/history", response_model=List[ChallengeResponse])
async def get_history():
    # Now reads from Firestore
    all_challenges = db_utils.get_all_challenges()
    formatted_challenges = []
    for challenge in all_challenges:
        formatted_challenge = challenge.copy()
        formatted_challenge["word_data"] = _format_word_data(challenge.get("word_data", []))
        formatted_challenges.append(formatted_challenge)
    return formatted_challenges

@app.get("/api/review-words", response_model=List[WordData])
async def get_review_words():
    # Now reads from Firestore
    all_challenges = db_utils.get_all_challenges()
    all_word_data = []
    for entry in all_challenges:
        all_word_data.extend(_format_word_data(entry.get("word_data", [])))
    
    seen_words = set()
    unique_words = []
    for data in all_word_data:
        word = data["word"]
        if word not in seen_words:
            seen_words.add(word)
            unique_words.append(data)
    
    random.shuffle(unique_words)
    return unique_words

@app.get("/api/audio")
async def get_audio(word: str = Query(..., description="Word to pronounce")):
    # This endpoint needs no changes
    if not word:
        raise HTTPException(status_code=400, detail="No word parameter provided")
    try:
        tts = gTTS(word, lang="en", tld="com")
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        return StreamingResponse(
            mp3_fp,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f'inline; filename="{word}.mp3"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate audio: {str(e)}")

@app.get("/api/grammar", response_model=GrammarChallenge)
async def get_grammar_challenge_endpoint():
    # This endpoint needs no changes
    try:
        challenge_data = llm_utils.get_grammar_challenge()
        return challenge_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate grammar challenge: {str(e)}")


@app.get("/")
async def root():
    return {
        "message": "Welcome to the FluentLeap API (Firebase Edition)",
        "version": "1.0.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

# --- Run the App ---
if __name__ == '__main__':
    import uvicorn
    print("🚀 Starting FluentLeap API server (Firebase Edition)...")
    print("📡 Server will be available at: http://localhost:8000")
    print("📚 API docs will be available at: http://localhost:8000/docs")
    print("✅  API is now using Google Gemini and Firebase.")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")