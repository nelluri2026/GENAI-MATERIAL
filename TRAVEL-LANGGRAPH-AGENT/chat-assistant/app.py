import chainlit as cl
import httpx
import os
import logging
import sys
import json
from langchain_openai import ChatOpenAI

# =========================================================
# LOGGING & CONFIG (ENHANCED)
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("TRAVEL_UI")
AGENT_LOG = logging.getLogger("AGENT_FLOW")
CALLBACK_LOG = logging.getLogger("CALLBACK_FLOW")
UI_LOG = logging.getLogger("UI_RENDER")

LLM_AGENT_URL = os.environ.get("LLM_AGENT_URL", "http://your-ecs-agent:8000/chat")

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.environ.get("OPENAI_API_KEY")
)

# =========================================================
# DEFAULT STATE (CRITICAL FIX)
# =========================================================
DEFAULT_STATE = {
    "origin": "unknown",
    "destination": "unknown",
    "travel_date_formatted": "unknown",
    "total_budget": None
}

# =========================================================
# UTILITY FUNCTIONS
# =========================================================

from datetime import datetime
from dateutil import parser

def resolve_date(raw_date: str):
    if not raw_date or raw_date == "unknown":
        return "unknown"

    try:
        current_year = datetime.utcnow().year
        dt = parser.parse(raw_date, fuzzy=True, default=datetime(current_year, 1, 1))
        dt = dt.replace(year=current_year)
        return dt.strftime("%Y-%m-%d")
    except:
        return "unknown"
    
async def parse_user_request(text: str):
    logger.info(f"🧠 Parsing user input: {text}")

    prompt = f"""
Extract travel details from the user's request.

User Request: "{text}"

Return ONLY a JSON object with:

- origin: string or "unknown"
- destination: string or "unknown"
- travel_date_raw: string exactly as user wrote (e.g. "oct 25th", "15 july", or "unknown")
- total_budget: number or null

STRICT RULES:
- DO NOT infer or calculate dates
- DO NOT convert dates to ISO format
- DO NOT assume year, month, or day
- DO NOT normalize or reformat anything related to date
- If user does not explicitly provide full date → travel_date_raw must be "unknown"
- Never hallucinate missing values
"""

    try:
        response = await llm.ainvoke(prompt)
        content = response.content.strip()

        if content.startswith("```json"):
            content = content[7:-3]

        parsed = json.loads(content)

        logger.info(f"🧾 Parsed Data: {parsed}")
        return parsed

    except Exception as e:
        logger.error(f"❌ Parsing Error: {e}")
        return None


async def call_agent(payload: dict):
    AGENT_LOG.info(f"➡️ CALLING AGENT | Action: {payload.get('action')}")
    AGENT_LOG.info(f"📦 Payload: {json.dumps(payload, indent=2)}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(LLM_AGENT_URL, json=payload)

            AGENT_LOG.info(f"⬅️ STATUS CODE: {response.status_code}")

            data = response.json()
            AGENT_LOG.info(f"📥 RESPONSE: {json.dumps(data, indent=2)}")
            return data

        except httpx.ConnectTimeout:
            AGENT_LOG.error("❌ CONNECT TIMEOUT to backend")
            return {"error": "timeout"}

        except Exception as e:
            AGENT_LOG.error(f"❌ Agent call failed: {e}")
            return {"error": str(e)}


# =========================================================
# CHAINLIT HANDLERS
# =========================================================

@cl.on_chat_start
async def start():
    thread_id = cl.user_session.get("id")
    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("activities_shown", False)
    cl.user_session.set("travel_data", DEFAULT_STATE.copy())

    logger.info(f"🚀 SESSION STARTED | Thread ID: {thread_id}")

    await cl.Message(
        content="✈️ **Smart Travel Planner**\nProvide Source, Destination, Date, Budget."
    ).send()


@cl.on_message
async def handle_message(message: cl.Message):
    user_input = message.content.strip()

    logger.info(f"📩 USER INPUT: {user_input}")

    thread_id = cl.user_session.get("thread_id")

    # =========================
    # RETRIEVE FLOW
    # =========================
    if user_input.lower().startswith("/retrieve"):
        parts = user_input.split()

        if len(parts) < 2:
            await cl.Message(content="⚠️ Usage: /retrieve TRV-ID").send()
            return

        ref_id = parts[1].upper()

        cl.user_session.set("thread_id", ref_id)

        res_data = await call_agent({
            "thread_id": ref_id,
            "action": "retrieve"
        })

        await process_agent_response(res_data)
        return

    # =========================
    # BUDGET SHORTCUT
    # =========================
    if user_input.replace('.', '', 1).isdigit():
        logger.info("💰 Budget update detected")

        res_data = await call_agent({
            "thread_id": thread_id,
            "action": "fix_budget",
            "data": {"total_budget": float(user_input)}
        })

        await process_agent_response(res_data)
        return

    # =========================
    # SESSION LOAD
    # =========================
    current_data = cl.user_session.get("travel_data") or DEFAULT_STATE.copy()

    new_details = await parse_user_request(user_input)

    if new_details:
        for key in ["origin", "destination"]:
            val = new_details.get(key, "unknown")
            if val != "unknown":
                current_data[key] = val

        # 🔥 DATE FIX (THIS IS THE IMPORTANT PART)
        raw_date = new_details.get("travel_date_raw", "unknown")
        current_data["travel_date_formatted"] = resolve_date(raw_date)

        # budget
        if new_details.get("total_budget"):
            current_data["total_budget"] = new_details["total_budget"]

    cl.user_session.set("travel_data", current_data)

    logger.info(f"🧾 SESSION DATA: {current_data}")

    # =========================
    # VALIDATION
    # =========================
    missing = []
    if current_data["origin"] == "unknown":
        missing.append("Source")
    if current_data["destination"] == "unknown":
        missing.append("Destination")
    if not current_data["total_budget"]:
        missing.append("Budget")

    if missing:
        await cl.Message(content=f"Need: {', '.join(missing)}").send()
        return

    # =========================
    # START AGENT
    # =========================
    payload = {
        "thread_id": thread_id,
        "action": "start",
        "data": {
            "origin": current_data.get("origin", "unknown"),
            "destination": current_data.get("destination", "unknown"),
            "travel_date_input": current_data.get("travel_date_formatted", "unknown"),
            "total_budget": current_data.get("total_budget")
        }
    }

    logger.info("🚀 STARTING AGENT FLOW")

    res_data = await call_agent(payload)
    await process_agent_response(res_data)


# =========================================================
# UI LOGIC
# =========================================================

async def process_agent_response(res_data):

    UI_LOG.info(f"🎯 UI STATE: {json.dumps(res_data, indent=2)}")

    # -------------------------
    # BOOKING VIEW
    # -------------------------
    if res_data.get("is_booked") and res_data.get("booking_reference"):
        summary = f"""
### 🔍 Booking Details
🆔 {res_data.get("booking_reference")}
✈️ {res_data.get("selected_flight_price")}
🏨 {res_data.get("selected_hotel_price")}
💰 {res_data.get("remaining_budget")}
📍 {res_data.get("origin")} → {res_data.get("destination")}
📅 {res_data.get("travel_date_formatted", "unknown")}
"""
        await cl.Message(content=summary).send()
        return

    # -------------------------
    # FLIGHTS
    # -------------------------
    if res_data.get("flight_options") and not res_data.get("selected_flight_price"):
        actions = [
            cl.Action(
                name="select_flight",
                label=f"{f['info']} (${f['price']})",
                payload={"price": f['price']}
            )
            for f in res_data["flight_options"]
        ]
        await cl.Message(content="✈️ Select Flight:", actions=actions).send()
        return

    # -------------------------
    # HOTELS
    # -------------------------
    if res_data.get("hotel_options") and not res_data.get("selected_hotel_price"):
        actions = [
            cl.Action(
                name="select_hotel",
                label=f"{h['name']} (${h['price']})",
                payload={"price": h['price']}
            )
            for h in res_data["hotel_options"]
        ]
        await cl.Message(content="🏨 Select Hotel:", actions=actions).send()
        return

    # -------------------------
    # FINAL CONFIRM
    # -------------------------
    if res_data.get("selected_hotel_price") and not res_data.get("is_booked"):
        remaining = res_data.get("remaining_budget", 0)

        summary = f"""
### Final Confirmation
💰 Remaining: {remaining}
"""

        actions = [
            cl.Action(
                name="confirm_booking",
                label="Confirm Booking",
                payload={}
            )
        ]

        await cl.Message(content=summary, actions=actions).send()
        return


# =========================================================
# CALLBACKS
# =========================================================

@cl.action_callback("select_flight")
async def on_flight(action: cl.Action):
    CALLBACK_LOG.info(f"✈️ Flight selected: {action.payload}")

    res = await call_agent({
        "thread_id": cl.user_session.get("thread_id"),
        "action": "select_prices",
        "data": {"selected_flight_price": float(action.payload["price"])}
    })

    await process_agent_response(res)


@cl.action_callback("select_hotel")
async def on_hotel(action: cl.Action):
    CALLBACK_LOG.info(f"🏨 Hotel selected: {action.payload}")

    res = await call_agent({
        "thread_id": cl.user_session.get("thread_id"),
        "action": "select_prices",
        "data": {"selected_hotel_price": float(action.payload["price"])}
    })

    await process_agent_response(res)


@cl.action_callback("confirm_booking")
async def on_confirm(action: cl.Action):
    CALLBACK_LOG.info("✅ Confirm booking triggered")

    res = await call_agent({
        "thread_id": cl.user_session.get("thread_id"),
        "action": "confirm_booking"
    })

    await process_agent_response(res)


@cl.action_callback("show_spots")
async def on_show_spots(action: cl.Action):
    CALLBACK_LOG.info("🎡 Fetching activities")

    res_data = await call_agent({
        "thread_id": cl.user_session.get("thread_id"),
        "action": "get_activities"
    })

    activities = res_data.get("activities", [])

    for act in activities[:5]:
        if isinstance(act, dict):
            await cl.Message(
                content=f"**{act.get('title')}**\n{act.get('price')}"
            ).send()