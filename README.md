# ☕ Bean O LLM Agent Evaluation with Opik

This project evaluates the performance of a customer support conversational agent  using the **Opik LLM evaluation framework**.

We assess the agent's responses for hallucination, relevance, usefulness, and key content consistency metrics through simulated test conversations.

---

## 📑 Project Structure


│── agent_backend.py # Flask backend (chat API)
│── test.py # Opik evaluation script
│── .env # Environment variables
│── index.html # Environment variables
├── requirements.txt
├── README.md




---

## 📦 Prerequisites

- Python 3.10+
- [OpenAI API Key](https://platform.openai.com/account/api-keys)
- [Opik](https://docs.opik.ai/)
- (Optional) Google Vertex AI / Gemini access for future integration

---

## 📥 Setup Instructions

1. **Clone this repository**
   ```bash
   git clone https://github.com/yourname/beano-agent-eval.git
   cd beano-agent-eval


2. **Clone this repository**
   ```bash
   pip install -r requirements.txt


3. **Create .env**
OPIK_API_KEY=<your_opik_api_key>
OPIK_WORKSPACE=<your_opik_workspace_id>
OPENAI_API_KEY=<your_openai_api_key>


4. **Run agent_backend.py to create agent**
   ```bash
   python agent_backend.py


5. **Run test.py to run Opik evaluation*
   ```bash
   python test.py


5. **Result Opik Comet Evaluation*
   


