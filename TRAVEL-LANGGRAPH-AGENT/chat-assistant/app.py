import chainlit as cl
import httpx
import os
import logging
import sys
import json
from langchain_openai import ChatOpenAI

# =========================================================
# CLOUDWATCH LOGGING CONFIGURATION
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TRAVEL_UI")

# Use the ECS Agent Service URL (Update this in your ECS Env Vars)
LLM_AGENT_URL = os.environ.get("LLM_AGENT_URL", "http://your-ecs-agent:8000/chat")

# Initialize the "Shield" LLM for intent extraction
# Ensure OPENAI_API_KEY is in your ECS Task Definition
llm = ChatOpenAI(
    model="gpt-4o-mini", 
    temperature=0,
    api_key=os.environ.get("OPENAI_API_KEY")
)

# =========================================================
# UTILITY FUNCTIONS
# =========================================================

async def parse_user_request(text: str):
    """
    The 'Shield' node: Translates messy English into the structured 
    JSON your LangGraph Agent expects.
    """
    prompt = f"""
    Extract travel details from the user's request. 
    User Request: "{text}"
    
    Return ONLY a JSON object with:
    - origin (string)
    - destination (string)
    - travel_date_input (string)
    - total_budget (number)
    
    If any field is missing, use "unknown". 
    For budget, if missing, default to 1000.
    """
    try:
        response = await llm.ainvoke(prompt)
        # Clean the response in case LLM adds markdown backticks
        content = response.content.replace('```json', '').replace('
```', '').strip()
        return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to parse intent: {e}")
        return None

async def call_agent(payload: dict):
    """Helper to communicate with the ECS LangGraph Agent"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        logger.info(f"Calling Agent | Action: {payload.get('action')} | Thread: {payload.get('thread_id')}")
        response = await client.post(LLM_AGENT_URL, json=payload)
        response.raise_for_status()
        return response.json()

# =========================================================
# CHAINLIT HANDLERS
# =========================================================

@cl.on_chat_start
async def start():
    thread_id = cl.user_session.get("id")
    cl.user_session.set("thread_id", thread_id)
    logger.info(f"New session started: {thread_id}")
    
    await cl.Message(
        content="✈️ **Travel Planner Active**\nReady to help you plan! You can tell me your plans in plain English.\n\n*Example: 'I want to go from Bangalore to Dubai on May 15th with a budget of 1500'*"
    ).send()

@cl.on_message
async def handle_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id")
    user_input = message.content.strip()

    # Step 1: Check if the input is a manual budget fix (just a number)
    if user_input.replace('.', '', 1).isdigit():
        payload = {
            "thread_id": thread_id,
            "action": "fix_budget",
            "data": {"total_budget": float(user_input)}
        }
        res_data = await call_agent(payload)
        await process_agent_response(res_data)
        return

    # Step 2: Use the 'Shield' LLM to parse natural language
    structured_data = await parse_user_request(user_input)
    
    if not structured_data or structured_data.get("origin") == "unknown":
        await cl.Message(content="I couldn't quite catch your travel details. Could you please specify where you are traveling from, your destination, and the date?").send()
        return

    # Step 3: Trigger the LangGraph Agent
    payload = {
        "thread_id": thread_id,
        "action": "start",
        "data": {
            "origin": structured_data["origin"],
            "destination": structured_data["destination"],
            "travel_date_input": structured_data["travel_date_input"],
            "total_budget": structured_data["total_budget"],
            "messages": []
        }
    }
    
    try:
        res_data = await call_agent(payload)
        await process_agent_response(res_data)
    except Exception as e:
        logger.error(f"Agent Call Failed: {e}")
        await cl.Message(content="⚠️ My travel agent service is currently unavailable. Please try again in a moment.").send()

async def process_agent_response(res_data):
    """Analyzes graph state and renders UI elements"""
    thread_id = cl.user_session.get("thread_id")

    # Handle Flight Selection via Buttons
    if "flight_options" in res_data and not res_data.get("selected_flight_price"):
        actions = [
            cl.Action(
                name="select_flight", 
                value=str(f['price']), 
                label=f["info"],
                payload={"price": f['price']} # Required by modern Chainlit/Pydantic
            )
            for f in res_data["flight_options"]
        ]
        await cl.Message(
            content="✈️ **I found several flight options. Which one would you like?**",
            actions=actions
        ).send()

    # Handle Budget Deficit
    elif res_data.get("remaining_budget", 0) < 0:
        logger.warning(f"Thread {thread_id} is over budget.")
        await cl.Message(
            content=f"❌ **Budget Alert!**\nYou are over budget by **${abs(res_data['remaining_budget'])}**.\n\nPlease type a new **Total Budget** to continue."
        ).send()

    # Handle Final Success
    elif res_data.get("activities"):
        content = f"✅ **Trip Planned Successfully!**\n\n"
        content += f"**Destination:** {res_data.get('destination_iata', 'Success')}\n"
        content += f"**Budget Remaining:** ${res_data.get('remaining_budget', 0)}\n\n"
        content += f"**Top Activities:**\n{res_data['activities'][0]}"
        await cl.Message(content=content).send()

@cl.action_callback("select_flight")
async def on_action(action: cl.Action):
    """Handles the button click for flight selection"""
    thread_id = cl.user_session.get("thread_id")
    price = float(action.value)
    
    logger.info(f"User selected flight: ${price} for thread {thread_id}")
    
    # We assume a base hotel cost of $500 for the simulation
    payload = {
        "thread_id": thread_id,
        "action": "select_prices",
        "data": {"selected_flight_price": price, "selected_hotel_price": 500}
    }
    
    # Visual feedback for the user
    await cl.Message(content=f"Selected Flight: **${price}**. Finalizing your itinerary...").send()
    
    try:
        res_data = await call_agent(payload)
        await process_agent_response(res_data)
    except Exception as e:
        logger.error(f"Action Callback Failed: {e}")
        await cl.Message(content="⚠️ Something went wrong while selecting your flight.").send()