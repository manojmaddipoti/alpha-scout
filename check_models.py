import google.generativeai as genai
import os
from dotenv import load_dotenv

# 1. Load the .env file so Python can find your GOOGLE_API_KEY
load_dotenv()

# 2. Configure the API
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("❌ Error: GOOGLE_API_KEY not found. Check your .env file.")
else:
    genai.configure(api_key=api_key)

    print("\n🔍 Checking for available Gemini models...\n")
    print("-" * 30)
    
    try:
        # 3. List models
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # We strip 'models/' prefix to get the clean ID you need for app.py
                clean_name = m.name.replace("models/", "")
                print(f"✅ {clean_name}")
                
        print("-" * 30)
        print("\n👉 Use these exact names in your app.py 'model_choice' list.")
        
    except Exception as e:
        print(f"❌ Error fetching models: {e}")