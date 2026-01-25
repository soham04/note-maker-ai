import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """make complete in detail note of this tutorial in english.
covering each and everything covered by the teacher.
make sure the notes are properly structured making it easy for the student to revise and remember later one.
Don't put exactly word to word.
Don't forget to include the intuition behind the algos.
Act like a good student who makes notes for everyone to understand not like a transcript.
Make sure no point is missed from the tutorial."""

def generate_notes(video_url: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    client = genai.Client(api_key=api_key)

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri=video_url,
                        mime_type="video/*",
                    )
                ),
            ],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="HIGH",
        ),
        system_instruction=[
            types.Part.from_text(text=SYSTEM_PROMPT),
        ],
    )

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=contents,
        config=generate_content_config,
    )
    
    return response.text
