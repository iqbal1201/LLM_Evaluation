# Save this as app.py (requires Flask, requests, flask-cors, python-dotenv, google-cloud-texttospeech, python-docx, PyPDF2)
# pip install Flask requests flask-cors python-dotenv google-cloud-texttospeech google-cloud-speech python-docx PyPDF2

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import json
import requests
import os
import uuid
import base64
from dotenv import load_dotenv
import tempfile
from werkzeug.utils import secure_filename # Import for secure filename handling

# Imports for document parsing (you'll need to install these: pip install python-docx PyPDF2)
try:
    from docx import Document # For .docx files
except ImportError:
    print("WARNING: python-docx not installed. Word document parsing will not work.")
    Document = None

try:
    import PyPDF2 # For .pdf files
except ImportError:
    print("WARNING: PyPDF2 not installed. PDF document parsing will not work.")
    PyPDF2 = None


# Import the Google Cloud client library for Text-to-Speech
from google.cloud import texttospeech_v1beta1 as texttospeech
from google.cloud import speech_v1p1beta1 as speech

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key="

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable not set. Please set it in a .env file or directly.")

# --- Google Cloud TTS Client Initialization ---
try:
    tts_client = texttospeech.TextToSpeechClient()
    print("Google Cloud Text-to-Speech client initialized.")
except Exception as e:
    print(f"ERROR: Failed to initialize Google Cloud Text-to-Speech client: {e}")
    print("Please ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set and has 'Cloud Text-to-Speech User' role.")
    tts_client = None

# --- Google Cloud STT Client Initialization ---
try:
    stt_client = speech.SpeechClient()
    print("Google Cloud Speech-to-Text client initialized.")
except Exception as e:
    print(f"ERROR: Failed to initialize Google Cloud Speech-to-Text client: {e}")
    print("Please ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set and has 'Cloud Speech-to-Text User' role.")
    stt_client = None


# --- Data Storage (for demonstration, in-memory. Use Firestore/DB for production) ---
deployed_agents = {}

# --- Helper function for text extraction from documents ---
def extract_text_from_pdf(pdf_path):
    if not PyPDF2:
        return "[PyPDF2 not installed - cannot extract PDF text]"
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                text += reader.pages[page_num].extract_text() or ''
        return text
    except Exception as e:
        return f"[Error extracting PDF text: {e}]"

def extract_text_from_word(docx_path):
    if not Document:
        return "[python-docx not installed - cannot extract Word text]"
    text = ""
    try:
        document = Document(docx_path)
        for paragraph in document.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        return f"[Error extracting Word text: {e}]"

@app.route('/api/generate-agent-ai', methods=['POST'])
def generate_agent_ai_endpoint():
    """
    Receives Agent data from frontend (now potentially FormData with files),
    calls Gemini, and prepares data.
    """
    # Check if this is a JSON request (legacy or if frontend sends JSON)
    # The frontend is now sending FormData, so this check will likely fail.
    # The primary way to receive data will be request.form and request.files.
    # We will remove this check for now, as it's causing the 400.
    # if not request.is_json:
    #     return jsonify({"message": "Request must be JSON"}), 400

    # Access form data (text fields) via request.form
    agent_data = {}
    for key in request.form:
        # Flask's request.form gives strings. If you have nested JSON, you'll need to parse.
        if key in ['advancedFeatures', 'deploymentChannels']: # These are JSON.stringify'd from frontend
            try:
                agent_data[key] = json.loads(request.form[key])
            except json.JSONDecodeError:
                agent_data[key] = request.form[key] # Keep as string if not valid JSON
        else:
            agent_data[key] = request.form[key]

    # Handle the uploaded file (knowledgeBaseFile)
    knowledge_base_file = request.files.get('knowledgeBaseFile')
    knowledge_base_content_from_file = ""

    if agent_data.get('knowledgeBaseType') == 'upload_doc' and knowledge_base_file:
        filename = secure_filename(knowledge_base_file.filename)
        # Create a temporary file to save the uploaded content
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            knowledge_base_file.save(tmp_file.name)
            temp_filepath = tmp_file.name # Get the path to the temporary file

        try:
            if filename.lower().endswith('.pdf'):
                knowledge_base_content_from_file = extract_text_from_pdf(temp_filepath)
            elif filename.lower().endswith(('.doc', '.docx')):
                knowledge_base_content_from_file = extract_text_from_word(temp_filepath)
            else:
                knowledge_base_content_from_file = f"[Unsupported file type for extraction: {filename}]"
        except Exception as e:
            knowledge_base_content_from_file = f"[Error processing file {filename}: {e}]"
            print(f"Error processing uploaded file {filename}: {e}")
        finally:
            # Clean up the temporary file
            os.unlink(temp_filepath)
        
        # Override knowledgeBaseContent with extracted text
        agent_data['knowledgeBaseContent'] = knowledge_base_content_from_file
        print(f"Extracted content from {filename} (first 200 chars): {knowledge_base_content_from_file[:200]}")

    # Basic validation for essential fields (after parsing FormData)
    required_fields = ['name', 'llm', 'useCase', 'purpose', 'campaignDesignPrompt']
    if not all(k in agent_data for k in required_fields):
        missing_fields = [k for k in required_fields if k not in agent_data]
        return jsonify({"message": f"Missing essential Agent data fields. Required: {', '.join(required_fields)}. Missing: {', '.join(missing_fields)}"}), 400

    # Determine the output language for Gemini's generated content
    output_language_for_gemini = agent_data.get('language', 'English')
    output_requirement_text = ""
    if output_language_for_gemini == "Bahasa Indonesia":
        output_requirement_text = "Perkenalkan diri kamu dulu. Kamu adalah Agent Assisstant berdasarkan karakter persona yang diberikan. Gunakan informasi karakter persona sebagai panduan anda, termasuk gaya komunikasinya, dan uraikan bagaimana ia akan menangani interaksi tipikal untuk kasus penggunaannya. Sertakan beberapa contoh dialog untuk beberapa skenario (misalnya, 'Oke, saya akan memeriksa kalender untuk Anda.'). Pastikan seluruh output adalah dalam Bahasa Indonesia."
    elif output_language_for_gemini == "Hindi":
        output_requirement_text = "कृपया पहले अपना परिचय दें. आप दिए गए व्यक्तित्व चरित्र के आधार पर एजेंट सहायक हैं। व्यक्तित्व चरित्र की जानकारी को अपने मार्गदर्शक के रूप में उपयोग करें, जिसमें उनकी संचार शैली शामिल है, और वर्णन करें कि वे आपके उपयोग के मामले के लिए सामान्य बातचीत को कैसे संभालेंगे। कई परिदृश्यों के लिए कुछ नमूना संवाद शामिल करें। (उदाहरण के लिए, 'ठीक है, मैं आपके लिए कैलेंडर की जाँच करूँगा।')। सुनिश्चित करें कि पूरा आउटपुट हिंदी में हो।"
    else: # Default to English
        output_requirement_text = "Introduce yourself first. You are the Agent Assistant based on the persona character provided. Use the persona character information as your guide, including their communication style, and describe how they would handle typical interactions for your use case. Include some sample dialogue for several scenarios (e.g., 'Okay, I will check the calendar for you.'). Ensure the entire output is in English."
    
    
    # Construct the prompt for Gemini using the processed agent_data
    # Note: Use agent_data.get('knowledgeBaseContent', '') as it now holds either direct text or extracted text
    prompt = (
        f"Create a Business Agent AI profile based on the following details:\n"
        f"Agent Name: {agent_data.get('name', 'N/A')}\n"
        f"Gender: {agent_data.get('gender', 'N/A')}\n"
        f"LLM: {agent_data.get('llm', 'gemini-2.0-flash')}\n"
        f"Language: **{agent_data.get('language', 'English')}**\n" # Emphasize language here
        f"Business Use Case: {agent_data.get('useCase', 'General Inquiry')}\n"
        f"Agent Purpose: {agent_data.get('purpose', 'N/A')}\n"
        f"Traits: {agent_data.get('traits', 'N/A')}\n"
        f"Flaws: {agent_data.get('flaws', 'N/A')}\n"
        f"Knowledge Base Type: {agent_data.get('knowledgeBaseType', 'N/A')}\n"
        f"Knowledge Base Content: {agent_data.get('knowledgeBaseContent', 'No knowledge base content provided.')}\n"
        f"Voice Select: {agent_data.get('voiceSelect', 'N/A')}\n"
        f"Voice Speed: {agent_data.get('voiceSpeed', 'N/A')}\n"
        f"\n--- Campaign Design and Function Calling Instructions ---\n"
        f"The agent should follow this conversational flow and consider these function calls:\n"
        f"{agent_data.get('campaignDesignPrompt', 'No specific flow defined. Engage in general conversation.')}\n"
        f"\n--- Output Requirement ---\n"
        f"**{output_requirement_text}**" # Use dynamic output requirement
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]
    }

    headers = {
        'Content-Type': 'application/json'
    }

    api_full_url = f"{GEMINI_API_URL}{GEMINI_API_KEY}"
    generated_text = ""

    if not GEMINI_API_KEY:
        return jsonify({"message": "Gemini API Key not configured on the backend."}), 500

    try:
        response = requests.post(api_full_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        json_response = response.json()

        if "candidates" in json_response and len(json_response["candidates"]) > 0 and \
           "content" in json_response["candidates"][0] and \
           "parts" in json_response["candidates"][0]["content"] and \
           len(json_response["candidates"][0]["content"]["parts"]) > 0:
            generated_text = json_response["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"Unexpected Gemini API response structure: {json.dumps(json_response)}")
            return jsonify({"message": "Failed to get generated text from Gemini."}), 500

    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({"message": f"Error calling Gemini API: {e}"}), 500
    except json.JSONDecodeError as e:
        print(f"Error decoding Gemini API response: {e}")
        return jsonify({"message": f"Error decoding Gemini API response: {e}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred during Gemini API call: {e}")
        return jsonify({"message": f"An unexpected error occurred during AI generation: {e}"}), 500

    # --- Store/Prepare data ---
    deployment_id = str(uuid.uuid4())
    full_agent_profile = {
        "id": deployment_id,
        "parameters": agent_data, # Original input parameters from form (includes knowledgeBaseType, content)
        "ai_generated_content": generated_text, # Gemini's response
        "deployment_channels": agent_data.get('deploymentChannels', []) # Note: This might be stringified JSON from frontend
    }

    deployed_agents[deployment_id] = full_agent_profile
    print(f"Agent created and stored. ID: {deployment_id}")

    return jsonify({
        "message": "Agent AI generated successfully!",
        "generatedText": generated_text,
        "deploymentId": deployment_id
    }), 200

@app.route('/api/get-agent-data/<deployment_id>', methods=['GET'])
def get_agent_data(deployment_id):
    """
    Endpoint to fetch Agent data by ID.
    """
    agent_profile = deployed_agents.get(deployment_id)
    if agent_profile:
        return jsonify(agent_profile), 200
    else:
        return jsonify({"message": "Agent data not found."}), 404

@app.route('/api/synthesize-speech', methods=['POST'])
def synthesize_speech():
    """
    Receives text, language, and voice type from frontend,
    calls Google Cloud TTS, and returns base64 encoded audio.
    """
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400

    data = request.get_json()
    text = data.get('text')
    language_code = data.get('languageCode')
    voice_name = data.get('voiceName')

    if not text or not language_code or not voice_name:
        return jsonify({"message": "Missing text, languageCode, or voiceName"}), 400

    if tts_client is None:
        return jsonify({"message": "Google Cloud Text-to-Speech client not initialized. Check server logs."}), 500

    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0 # You can adjust this if needed
        )

        response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        audio_content_base64 = base64.b64encode(response.audio_content).decode('utf-8')

        return jsonify({"audioContent": audio_content_base64, "format": "audio/mp3"}), 200

    except Exception as e:
        print(f"Error synthesizing speech with GCP TTS: {e}")
        return jsonify({"message": f"Failed to synthesize speech: {e}"}), 500


@app.route('/api/chat-with-agent', methods=['POST', 'OPTIONS'])
@cross_origin()
def chat_with_agent():
    """
    Handles a chat turn with a specified agent.
    Receives agent_id and user_message, fetches agent config,
    and sends to Gemini for a response.
    """
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400

    data = request.get_json()
    agent_id = data.get('agentId')
    user_message = data.get('userMessage')
    chat_history = data.get('chatHistory', [])

    if not agent_id or not user_message:
        return jsonify({"message": "Missing agentId or userMessage"}), 400

    agent_profile = deployed_agents.get(agent_id)
    if not agent_profile:
        return jsonify({"message": "Agent not found"}), 404

    agent_name = agent_profile['parameters'].get('name', 'AI Agent')
    agent_persona = agent_profile.get('ai_generated_content', 'You are a helpful assistant.')
    campaign_design = agent_profile['parameters'].get('campaignDesignPrompt', 'Engage in general conversation.')
    selected_llm = agent_profile['parameters'].get('llm', 'gemini-2.0-flash')
    selected_language = agent_profile['parameters'].get('language', 'English') 

    system_instruction = (
        f"You are {agent_name}. Your core persona is:\n{agent_persona}\n\n"
        f"Follow these conversation flow and function calling instructions:\n{campaign_design}\n\n"
        f"**IMPORTANT:** All your responses MUST be entirely in {selected_language}. Do NOT use any other language or mixed languages. Start every response directly in {selected_language}. Do not give special symbol: for instance asterisk symbol in response unless required (@ in email address)."
        f"Be concise, helpful, and follow your defined persona and rules. Respond in markdown."
    )

    gemini_chat_history = []
    gemini_chat_history.append({'role': 'user', 'parts': [{'text': system_instruction}]})

    if chat_history:
        for entry in chat_history:
            if entry['sender'] == 'user':
                gemini_chat_history.append({'role': 'user', 'parts': [{'text': entry['message']}]})
            elif entry['sender'] == 'agent':
                gemini_chat_history.append({'role': 'model', 'parts': [{'text': entry['message']}]})

    gemini_chat_history.append({'role': 'user', 'parts': [{'text': user_message}]})

    payload = {
        "contents": gemini_chat_history
    }

    headers = {
        'Content-Type': 'application/json'
    }

    api_full_url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_llm}:generateContent?key={GEMINI_API_KEY}"
    
    if not GEMINI_API_KEY:
        return jsonify({"message": "Gemini API Key not configured on the backend."}), 500

    try:
        response = requests.post(api_full_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        json_response = response.json()

        if "candidates" in json_response and len(json_response["candidates"]) > 0 and \
           "content" in json_response["candidates"][0] and \
           "parts" in json_response["candidates"][0]["content"] and \
           len(json_response["candidates"][0]["content"]["parts"]) > 0:
            agent_response_text = json_response["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"response": agent_response_text}), 200
        else:
            print(f"Unexpected Gemini API response structure for chat: {json.dumps(json_response)}")
            return jsonify({"message": "Failed to get agent response from Gemini."}), 500

    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API for chat: {e}")
        return jsonify({"message": f"Error communicating with AI: {e}"}), 500
    except json.JSONDecodeError as e:
        print(f"Error decoding Gemini API response for chat: {e}")
        return jsonify({"message": f"Error processing AI response: {e}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred during chat with AI: {e}")
        return jsonify({"message": f"An unexpected error occurred: {e}"}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
