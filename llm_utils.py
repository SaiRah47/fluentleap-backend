import google.generativeai as genai
import json
import os
import re
from dotenv import load_dotenv
from typing import List, Tuple, Dict, Any

# --- Configuration ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file. Please add it.")

genai.configure(api_key=GOOGLE_API_KEY)

# --- Model Configuration (FIXED) ---
TEXT_MODEL_NAME = "gemini-flash-lite-latest"
IMAGE_MODEL_NAME = "gemini-2.5-flash-image"

# Safety settings (set to be permissive for this app)
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# Config for forcing JSON output from the text model
JSON_CONFIG = genai.GenerationConfig(response_mime_type="application/json")


def _get_text_model() -> genai.GenerativeModel:
    """Returns an instance of the text generation model."""
    return genai.GenerativeModel(TEXT_MODEL_NAME, safety_settings=SAFETY_SETTINGS)

def _get_image_model() -> genai.GenerativeModel:
    """Returns an instance of the image generation model."""
    return genai.GenerativeModel(IMAGE_MODEL_NAME, safety_settings=SAFETY_SETTINGS)

def _clean_json_response(response_text: str) -> str:
    """Cleans the typical markdown ```json ... ``` wrapper from the model response."""
    match = re.search(r'```json\s*(\{.*\})\s*```', response_text, re.DOTALL)
    if match:
        return match.group(1)
    return response_text # Return as-is if no wrapper found

# --- API Functions (Rewritten for Gemini) ---

def get_llm_vocab_batch(words: List[str]) -> List[Tuple]:
    """
    Gets the 5-word batch for the daily challenge using Gemini.
    Returns a list of tuples.
    """
    model = _get_text_model()
    
    system_prompt = """
    You are an English vocabulary tutor bot.
    You MUST reply with a single, valid JSON object.
    The object must have a single key "word_data", which is a list.
    Each item in the list must be an object with keys: "word", "ipa", "meaning", "synonyms", "antonyms", "sentence".
    - "word": The word requested.
    - "ipa": IPA pronunciation string.
    - "meaning": A short, clear definition (max 12 words).
    - "synonyms": A comma-separated string of 3 synonyms.
    - "antonyms": A comma-separated string of 3 antonyms (or "none").
    - "sentence": A natural English sentence using the word.
    """
    
    user_prompt = f"Generate the vocabulary data for these 5 words: {', '.join(words)}"
    
    print(f"Calling Gemini for vocab batch: {', '.join(words)}...")
    
    try:
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=JSON_CONFIG
        )
        
        response_text = _clean_json_response(response.text)
        data = json.loads(response_text)
        word_list = data.get("word_data", [])
        
        results = []
        for item in word_list:
            results.append((
                item.get("word", ""),
                item.get("ipa", ""),
                item.get("meaning", ""),
                item.get("synonyms", ""),
                item.get("antonyms", ""),
                item.get("sentence", "")
            ))
        
        if not results:
             raise Exception("AI returned empty word data.")
             
        print("Gemini vocab batch successful.")
        return results
        
    except Exception as e:
        print(f"Error decoding JSON from Gemini (vocab): {e}")
        # Fallback in case of error
        return [
            (word, "N/A", "Error loading data from AI.", "N/A", "N/A", "N/A") for word in words
        ]

def get_story_feedback(story: str) -> str:
    """
    Gets writing feedback for the user's story using Gemini.
    Returns a formatted string.
    """
    model = _get_text_model()
    
    system_prompt = """
    You are a helpful and concise English writing tutor.
    A student wrote a short story.
    Please provide feedback following this structure EXACTLY:
    ### Corrections:
    (List any grammar or spelling corrections. If none, write "None.")
    
    ### Suggestions:
    (Give 1-2 short, actionable suggestions for improvement.)
    
    ### Best Version:
    (Provide a revised version of the story. Keep it close to the original length.)
    
    Keep your feedback positive and encouraging. Do not add any extra text outside this structure.
    """
    
    user_prompt = f"Here is the story: \n---\n{story}\n---"
    
    print("Calling Gemini for story feedback...")
    try:
        response = model.generate_content([system_prompt, user_prompt])
        feedback = response.text
        
        if "### Corrections:" not in feedback: # Basic validation
            raise Exception("AI did not follow feedback format.")
            
        print("Gemini story feedback successful.")
        return feedback
        
    except Exception as e:
        print(f"Error from Gemini (feedback): {e}")
        return f"### Corrections:\nNone.\n\n### Suggestions:\nGreat job using the words!\n\n### Best Version:\n{story}"


def lookup_word(word_to_lookup: str) -> tuple:
    """
    Looks up a single word using Gemini.
    Returns a single tuple.
    """
    model = _get_text_model()
    
    system_prompt = """
    You are an English vocabulary tutor bot.
    You MUST reply with a single, valid JSON object with keys:
    "word", "ipa", "meaning", "synonyms", "antonyms", "sentence".
    """
    
    user_prompt = f"Generate the vocabulary data for this word: {word_to_lookup}"
    
    print(f"Calling Gemini for word lookup: {word_to_lookup}...")
    try:
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=JSON_CONFIG
        )
        response_text = _clean_json_response(response.text)
        item = json.loads(response_text)
        
        print("Gemini lookup successful.")
        return (
            item.get("word", word_to_lookup),
            item.get("ipa", ""),
            item.get("meaning", ""),
            item.get("synonyms", ""),
            item.get("antonyms", ""),
            item.get("sentence", "")
        )
    except Exception as e:
        print(f"Error decoding JSON from Gemini (lookup): {e}")
        return (word_to_lookup, "N/A", "Error loading data.", "N/A", "N/A", "N/A")


def get_grammar_challenge() -> dict:
    """
    Generates a new grammar challenge using Gemini.
    Returns a Python dictionary.
    """
    model = _get_text_model()
    
    system_prompt = """
    You are an English grammar quiz generator.
    Create a new grammar challenge about a common English error (e.g., their/there/they're, your/you're, its/it's, affect/effect).
    You MUST reply with only a single, valid JSON object in this exact format:
    {
      "title": "Grammar Fix-Up: <Topic>",
      "description": "Correct the grammar in the sentences below. Type your corrected sentence in the box.",
      "problems": [
        { "id": 1, "incorrect": "<Incorrect sentence 1>", "correct": "<Correct sentence 1>" },
        { "id": 2, "incorrect": "<Incorrect sentence 2>", "correct": "<Correct sentence 2>" }
      ]
    }
    """
    
    user_prompt = "Generate a new grammar challenge with 2 problems."
    
    print("Calling Gemini for grammar challenge...")
    try:
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=JSON_CONFIG
        )
        response_text = _clean_json_response(response.text)
        data = json.loads(response_text)
        
        if "title" not in data: # Basic validation
            raise Exception("Invalid JSON structure from AI")
            
        print("Gemini grammar challenge successful.")
        return data
    except Exception as e:
        print(f"Error decoding JSON from Gemini (grammar): {e}")
        print(f"Raw response was: {response_text}")
        return {
          "title": "Grammar Fix-Up: Your/You're",
          "description": "Correct the grammar in the sentences below. (Error: Could not load from AI)",
          "problems": [
            { "id": 1, "incorrect": "Your going to be late.", "correct": "You're going to be late." },
            { "id": 2, "incorrect": "Is this you're book?", "correct": "Is this your book?" }
          ]
        }


def generate_image_with_gemini(story: str) -> bytes:
    """
    Generates an image with Gemini based on the story.
    Returns the image as raw bytes.
    """
    model = _get_image_model() 
    
    prompt = f"""
    Generate an image for the following story.
    Style: "vibrant digital art".
    Do not include any text or words in the image.

    Story:
    "{story}"
    """
    
    print(f"Calling Gemini Image Model ({IMAGE_MODEL_NAME}) for story...")
    try:
        response = model.generate_content(prompt)
        
        # 1. Check for safety blocks
        if response.prompt_feedback.block_reason:
            print(f"Error: Image generation blocked due to: {response.prompt_feedback.block_reason}")
            return None

        # --- (THIS IS THE FIX) ---
        # 2. Iterate through all parts to find the image
        #    The model sends text AND an image in different parts.
        #    We must loop through all parts to find the one with image data.
        
        image_bytes = None
        for part in response.candidates[0].content.parts:
            if part.inline_data.data:
                image_bytes = part.inline_data.data
                break # Found the image, stop looking
            elif part.text:
                # Log the text part for debugging, but don't fail
                print(f"Model also returned text") 

        # 3. Check if we found image bytes after the loop
        if image_bytes:
            print("Gemini Image generation successful.")
            return image_bytes
        else:
            # No image was found in any part
            print("Error: Model response did not contain any image data (and was not blocked).")
            # print(f"DEBUG: Full candidate: {response.candidates[0]}") 
            return None
        # --- (END OF FIX) ---
            
    except Exception as e:
        print(f"Error during image generation API call: {str(e)}")
        return None