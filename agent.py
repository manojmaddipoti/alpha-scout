# %% [markdown]
# ### Cell 1: Setup and Authentication
# This only needs to be run once per session.

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

print("✅ Setup complete. API Key loaded.")

# %% [markdown]
# ### Cell 2: Define the Agent Function
# Run this cell whenever you change the "personality" or logic of your agent.

def run_agent(prompt, system_message="You are a helpful AI assistant."):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

print("✅ Agent function defined.")

# %% [markdown]
# ### Cell 3: Interactive Testing
# This is the "Box" you will run over and over. 
# You can change the prompt here and click 'Run Cell' without restarting the script!

user_input = "Write a 1-sentence tagline for a new AI startup on an M4 Mac."
result = run_agent(user_input)

print(f"--- AGENT RESPONSE ---\n{result}")
# %%
