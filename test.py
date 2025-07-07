import requests
import json
import os
import opik
from dotenv import load_dotenv
from opik.evaluation import evaluate_prompt, evaluate
from opik.evaluation.metrics import Hallucination, AnswerRelevance, Contains, Usefulness


load_dotenv()

OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")

api_key = os.environ["OPIK_API_KEY"]
opik_workspace = os.environ["OPIK_WORKSPACE"]
workspace_name = opik_workspace # Replace if not set in env


# Define your backend URL
BASE_URL = "http://localhost:5000/api"

def get_agent_data(agent_id):
    """
    Calls the /api/get-agent-data/<deployment_id> endpoint to retrieve agent details.
    """
    url = f"{BASE_URL}/get-agent-data/{agent_id}"
    print(f"\n--- Calling {url} to get agent data ---")
    try:
        response = requests.get(url)
        response.raise_for_status()
        agent_profile = response.json()
        print("Agent data retrieved successfully!")
        #print(json.dumps(agent_profile, indent=2))
        return agent_profile
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error getting agent data: {e}")
        print(f"Response: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: Is the Flask backend running at {BASE_URL}? {e}")
        print("Please ensure your 'app.py' Flask server is running on http://localhost:5000.")
    except Exception as e:
        print(f"An unexpected error occurred during agent data retrieval: {e}")
    return None

def chat_with_agent(agent_id, user_message, chat_history=[]):
    """
    Calls the /api/chat-with-agent endpoint to interact with an agent.
    """
    url = f"{BASE_URL}/chat-with-agent"
    print(f"\n--- Calling {url} to chat with agent {agent_id} ---")

    payload = {
        "agentId": agent_id,
        "userMessage": user_message,
        "chatHistory": chat_history # Pass accumulated chat history
    }
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        agent_response = result.get('response')
        print(f"User: {user_message}")
        print(f"Agent: {agent_response}")
        return agent_response
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error during chat: {e}")
        print(f"Response: {e.response.text}")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: Is the Flask backend running at {BASE_URL}? {e}")
        print("Please ensure your 'app.py' Flask server is running on http://localhost:5000.")
    except Exception as e:
        print(f"An unexpected error occurred during chat: {e}")
    return None

if __name__ == "__main__":
   
    agent_id_to_use = input("agent id: ") # <--- REPLACE THIS PLACEHOLDER
    
    print(f"Attempting to interact with agent ID: {agent_id_to_use}")

    # --- STEP 1: Retrieve Agent Data ---
    print("\n--- Retrieving Agent Data using the ID ---")
    retrieved_agent_profile = get_agent_data(agent_id_to_use)

    
    print("Agent data successfully retrieved from backend.")

    # --- STEP 2: Start Chat with Agent ---
    print("\n--- Starting a chat with the generated agent ---")
    chat_history = []

    test_scenarios = [
    {"input": "What is the return policy in this company??",
        "expected_output": "Our return policy allows for returns within 30 days for unopened bags."},
    {"input": "Do you have any light roast options??",
        "expected_output": "Yes, we do! Our light roasts are known for their brighter, more acidic flavors and often exhibit fruity or floral notes."},
    {"input": "How many roasted coffee type in your company?",
        "expected_output": "We offer three roast types: light, medium, and dark."},
    {"input": "How long is the shipping for standard one?",
        "expected_output": "Standard shipping typically takes 3-5 business days."},
    {"input": "How long is the shipping for express one?",
        "expected_output": "Express shipping typically takes 1-2 business days."},
    {"input": "What kind of coffee does Bean O sell?",
        "expected_output": "At Bean O, we sell premium organic coffee beans globally. We specialize in single-origin, ethically sourced beans, offering a variety of light, medium, and dark roasts, as well as convenient subscription services."},
    {"input": "Are your coffee beans ethically sourced?",
        "expected_output": "Yes, absolutely! At Bean O, we are committed to sustainability, and all our coffee beans are ethically sourced."},
    {"input": "Tell me about Bean O's values.",
        "expected_output": "At Bean O, our customers value quality, sustainability, and quick support. We are dedicated to providing premium organic, single-origin, and ethically sourced coffee beans."},
    {"input": "What's the best way to brew your light roast for a pour-over?",
        "expected_output": "While specific brewing methods can vary, a great starting point for pour-over with a light roast is often a water temperature around 200-205°F (93-96°C) and a grind size similar to table salt. A common ratio is 1:15 or 1:16 coffee to water. You can find more detailed brewing guides on our website for optimal results!"},
    {"input": "Which roast is ideal for making espresso?",
        "expected_output": "For espresso, many people prefer our dark roast due to its rich, bold flavor. However, some also enjoy the intensity of our medium roast. Ultimately, it comes down to personal preference!"},
    {"input": "How do I manage my coffee subscription?",
        "expected_output": "To manage your coffee subscription, you can log in to your account on our website. From your account dashboard, you'll be able to update your order frequency, change your coffee selection, or adjust your shipping details. If you need any specific guidance, just let me know!"},
    {"input": "Do you have any dark roast options?",
        "expected_output": "Yes, we certainly do! Bean O offers a selection of delicious dark roast coffee beans for those who prefer a bold and robust flavor."},
    {"input": "What are single-origin beans?",
        "expected_output": "Single-origin beans come from a single specific geographical location, which could be a single farm, a specific region, or a particular country. This means they often have distinct and unique flavor profiles influenced by their specific growing conditions."},
]
        
        # Perform chat & collect responses
    

    # Create / get Opik dataset
    opik_client = opik.Opik()
    dataset = opik_client.get_or_create_dataset(name="Agent-jellybean")

    print("Success create dataset")

    dataset.insert(test_scenarios)

    print("Success insert dataset")


    hallucination_metric = Hallucination()
    contains_metric = Contains(case_sensitive=False)
    useful_metric = Usefulness()
    relevance_metric = AnswerRelevance(require_context=False)

    print("Success insert metrics")
    

    # Define Opik evaluation task
    def evaluation_task(x):
        user_input = x["input"]
        agent_reply = chat_with_agent(agent_id_to_use, user_input, chat_history)
        return {
            "output": agent_reply
        }
    

    # Run Opik evaluation
    result = evaluate(
        dataset=dataset,
        task=evaluation_task,
        scoring_metrics=[hallucination_metric, useful_metric, relevance_metric],
        experiment_name="Agent-Jellybean-Eval",
        scoring_key_mapping={
        "reference": "expected_output"},
        task_threads=3
    )

    print("\n--- Opik Evaluation Results ---")
    print(result)
    
