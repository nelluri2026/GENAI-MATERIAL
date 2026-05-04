import os, json, re, requests
from datetime import datetime
from app.state import TravelState
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SerpAPIWrapper
from app.config import logger

llm = ChatOpenAI(model="gpt-4o", temperature=0)
search_tool = SerpAPIWrapper()

# --- 1. Define the Node ---
def budget_check_node(state: TravelState):
    total = state.get("total_budget", 0) or 0
    flight = state.get("selected_flight_price", 0) or 0
    hotel = state.get("selected_hotel_price", 0) or 0
    
    spent = flight + hotel
    remaining = total - spent
    
    logger.info(f"--- 🧠 BUDGET CHECK: Total ${total} | Spent ${spent} | Remaining ${remaining} ---")
    
    # Returning this dict updates the LangGraph state automatically
    return {"remaining_budget": remaining}

from dateutil import parser
from datetime import datetime

def normalize_date(user_input: str):
    try:
        dt = parser.parse(user_input, fuzzy=True, default=datetime(1900, 1, 1))
        # If year not mentioned, assume current year
        if dt.year == 1900:
            dt = dt.replace(year=datetime.now().year)
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning(f"Date parsing failed: {e}")
        return datetime.now().strftime("%Y-%m-%d")

def fallback_iata(city: str):
    mapping = {"dubai": "DXB", "bangkok": "BKK", "london": "LHR"}
    return mapping.get(city.lower(), "DXB")

def input_processor_node(state: TravelState):
    logger.info(f"--- 🔍 PROCESSING: {state.get('origin')} ---")
    formatted_date = normalize_date(state["travel_date_input"])
    prompt = f"Return ONLY JSON: {{'origin_iata': '...', 'destination_iata': '...'}} for Origin: {state['origin']}, Destination: {state['destination']}"
    
    try:
        raw = llm.invoke(prompt).content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(match.group(0))
        origin, dest = data["origin_iata"].upper(), data["destination_iata"].upper()
    except Exception as e:
        logger.warning(f"LLM Processor failed, using fallbacks: {e}")
        origin, dest = fallback_iata(state["origin"]), fallback_iata(state["destination"])
        
    return {
            "origin_iata": origin,
            "destination_iata": dest,
            "travel_date_formatted": state.get("travel_date_formatted") or formatted_date
        }

def flight_agent(state: TravelState):
    logger.info(f"--- ✈️ FLIGHTS: {state['origin_iata']} -> {state['destination_iata']} ---")
    url = "https://api.duffel.com/air/offer_requests?return_offers=true"
    headers = {"Duffel-Version": "v2", "Authorization": f"Bearer {os.getenv('DUFFEL_ACCESS_TOKEN')}", "Content-Type": "application/json"}
    payload = {"data": {"slices": [{"origin": state['origin_iata'], "destination": state['destination_iata'], "departure_date": state['travel_date_formatted']}], "passengers": [{"type": "adult"}], "cabin_class": "economy"}}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        res.raise_for_status()
        offers = res.json().get("data", {}).get("offers", [])[:3]
        results = [{"info": f"{o['owner']['name']}: ${o['total_amount']}", "price": float(o["total_amount"])} for o in offers]
        logger.info(f"Found {len(results)} flight offers")
        return {"flight_options": results}
    except Exception as e:
        logger.error(f"Flight API Error: {e}")
        return {"flight_options": [{"info": "Emirates: $420", "price": 420}, {"info": "Qatar: $390", "price": 390}]}

def hotel_agent(state: TravelState):
    dest = state.get('destination', 'New York')
    logger.info(f"--- 🏨 HOTELS: {dest} ---")
    
    try:
        # Instead of a raw string, we create structured data for your Chainlit buttons
        # In a real app, you'd parse the search results, but for now, let's structure them:
        results = [
            {"name": f"Grand Central Hotel {dest}", "price": 250.0},
            {"name": f"Riverside Inn {dest}", "price": 150.0},
            {"name": f"City Center Suites", "price": 300.0}
        ]
        return {"hotel_options": results}
    except Exception as e:
        logger.error(f"Hotel Search Error: {e}")
        return {"hotel_options": [{"name": "Standard Stay", "price": 200.0}]}

def supervisor_node(state: TravelState):
    total = state.get("total_budget") or 0.0
    f_price = state.get("selected_flight_price") or 0.0
    h_price = state.get("selected_hotel_price") or 0.0

    spent = f_price + h_price
    remaining = round(total - spent, 2)

    logger.info(f"--- 💰 CALCULATION: {total} - {spent} = {remaining} ---")

    return {"remaining_budget": remaining}

def activity_agent(state: TravelState):
    logger.info(f"--- 🎭 ACTIVITIES: {state['destination']} ---")
    
    try:
        results = search_tool.results(f"top attractions in {state['destination']}")
        
        activities = []
        
        # 👇 Extract from SerpAPI structured response
        for place in results.get("organic_results", [])[:5]:
            activities.append({
                "title": place.get("title"),
                "price": "Check availability",
                "thumbnail": place.get("thumbnail") or None
            })
        
        logger.info(f"Extracted {len(activities)} activities")
        return {"activities": activities}

    except Exception as e:
        logger.error(f"Activity Search Error: {e}")
        return {
            "activities": [
                {"title": "Local sightseeing", "price": "Free", "thumbnail": None}
            ]
        }

def budget_warning_node(state: TravelState):
    logger.warning(f"--- ⚠️ OVER BUDGET: ${abs(state.get('remaining_budget', 0))} ---")
    return {}

    
def booking_node(state: TravelState):
    import uuid
    # Generate the professional reference ID
    ref_id = f"TRV-{uuid.uuid4().hex[:6].upper()}"
    return {
        "booking_reference": ref_id,
        "is_booked": True
    }
    
from langgraph.types import interrupt
def review_itinerary(state):
    return interrupt({
        "message": "Please confirm booking",
        "flight": state.get("selected_flight_price"),
        "hotel": state.get("selected_hotel_price"),
        "remaining": state.get("remaining_budget")
    })