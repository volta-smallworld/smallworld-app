"""
Agent / conversational interface powered by Claude Haiku.

The agent wraps the pipeline via tool calls. It translates natural
language into pipeline config, narrates results, and handles
refinement loops.
"""

import json
from typing import List, Optional
from config import ANTHROPIC_API_KEY
from log import get_logger

log = get_logger("agent.chat")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Tool definitions for the agent
TOOLS = [
    {
        "name": "run_pipeline",
        "description": (
            "Run the smallworld terrain analysis pipeline. Finds optimal photography "
            "viewpoints for a given location. Returns ranked camera positions with "
            "beauty scores and lighting information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "center_lat": {
                    "type": "number",
                    "description": "Latitude of search center"
                },
                "center_lng": {
                    "type": "number",
                    "description": "Longitude of search center"
                },
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometers (1-50)",
                    "default": 10
                },
                "mode": {
                    "type": "string",
                    "enum": ["ground", "drone"],
                    "description": "Camera mode: ground photographer or drone",
                    "default": "ground"
                },
                "feature_weights": {
                    "type": "object",
                    "description": "Weights for terrain features (peaks, ridges, cliffs, water, relief). 0-1 scale.",
                    "properties": {
                        "peaks": {"type": "number"},
                        "ridges": {"type": "number"},
                        "cliffs": {"type": "number"},
                        "water": {"type": "number"},
                        "relief": {"type": "number"},
                    }
                },
                "beauty_weights": {
                    "type": "object",
                    "description": "Weights for beauty factors. All should sum to ~1.0.",
                    "properties": {
                        "viewshed_richness": {"type": "number"},
                        "viewpoint_entropy": {"type": "number"},
                        "skyline_fractal": {"type": "number"},
                        "prospect_refuge": {"type": "number"},
                        "depth_layering": {"type": "number"},
                        "mystery": {"type": "number"},
                        "water_visibility": {"type": "number"},
                    }
                },
                "composition_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only use these composition templates (e.g., ['thirds_upper_right', 'golden_diagonal']). Omit for all."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                },
            },
            "required": ["center_lat", "center_lng"],
        },
    },
    {
        "name": "describe_viewpoint",
        "description": (
            "Generate a photographer-friendly natural language description "
            "of a viewpoint result, including composition, terrain features, "
            "and shooting tips."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "viewpoint": {
                    "type": "object",
                    "description": "The viewpoint result object to describe"
                },
            },
            "required": ["viewpoint"],
        },
    },
    {
        "name": "export_drone_csv",
        "description": "Export viewpoints as Litchi-compatible CSV for automated drone missions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "viewpoint_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Which viewpoint results to include (1-indexed)"
                },
            },
            "required": ["viewpoint_indices"],
        },
    },
]

SYSTEM_PROMPT = """You are the smallworld photography assistant. You help photographers and drone pilots find optimal camera angles for landscape photography.

You have access to a terrain analysis pipeline that:
1. Fetches elevation data for any location on Earth
2. Extracts terrain features (peaks, ridges, cliffs, water, saddles)
3. Computes camera positions using composition rules (rule of thirds, golden ratio, etc.)
4. Scores viewpoints for beauty (fractal dimension, prospect-refuge, depth, mystery)
5. Computes optimal lighting times (shadow analysis)
6. Exports to Litchi CSV for drone missions

When the user describes what they want, translate it into pipeline parameters:
- Location names → lat/lng coordinates
- "dramatic" → high cliff/relief weights
- "serene" / "peaceful" → high water weight, lower cliffs
- "depth" / "layers" → high depth_layering weight
- "open" / "panoramic" → high prospect weight
- "intimate" / "enclosed" → high refuge weight
- "mysterious" → high mystery weight
- "complex skyline" → high skyline_fractal weight

Always run the pipeline first, then describe the results in photographer-friendly language.
Include practical shooting tips: lens recommendations, time of day, what to look for.

Keep responses concise and focused on actionable photography advice."""


class AgentChat:
    """Conversational agent wrapping the pipeline."""

    def __init__(self):
        self.conversation_history = []
        self.last_results = None
        self.last_config = None

        if HAS_ANTHROPIC and ANTHROPIC_API_KEY:
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            log.info("AgentChat initialized with Anthropic client")
        else:
            self.client = None
            log.info("AgentChat initialized in fallback mode (no API key)")

    def chat(self, user_message: str, pipeline_runner=None) -> dict:
        """Process a user message and return a response.

        Args:
            user_message: The user's natural language input
            pipeline_runner: callable(config_dict) -> results list

        Returns:
            dict with 'response' (text) and optionally 'results' (viewpoints)
        """
        log.info(f"Chat message: {user_message[:100]}{'...' if len(user_message) > 100 else ''}")

        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        if not self.client:
            log.debug("Using fallback response (no client)")
            return self._fallback_response(user_message, pipeline_runner)

        # Call Claude with tools
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.conversation_history,
        )

        # Process tool calls
        results = None
        assistant_content = []

        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_result = self._execute_tool(
                    block.name, block.input, pipeline_runner
                )
                if block.name == "run_pipeline" and tool_result.get("results"):
                    results = tool_result["results"]

                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

                # Add tool result to conversation
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_content,
                })
                self.conversation_history.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_result),
                    }],
                })

                # Get final response after tool use
                final = self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=self.conversation_history,
                )

                text = ""
                for fb in final.content:
                    if fb.type == "text":
                        text += fb.text

                self.conversation_history.append({
                    "role": "assistant",
                    "content": text,
                })

                return {"response": text, "results": results}

        # No tool calls — just text response
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        self.conversation_history.append({
            "role": "assistant",
            "content": text,
        })

        return {"response": text, "results": results}

    def _execute_tool(self, name: str, inputs: dict, pipeline_runner) -> dict:
        """Execute a tool call."""
        log.info(f"Executing tool: {name}")
        if name == "run_pipeline" and pipeline_runner:
            results = pipeline_runner(inputs)
            self.last_results = results
            self.last_config = inputs
            return {
                "results": [r.to_dict() if hasattr(r, 'to_dict') else r for r in results],
                "count": len(results),
            }

        elif name == "describe_viewpoint":
            vp = inputs.get("viewpoint", {})
            return {
                "description": (
                    f"Viewpoint at {vp.get('lat', '?')}N, {vp.get('lng', '?')}W, "
                    f"altitude {vp.get('altitude_m', '?')}m. "
                    f"Composition: {vp.get('composition', 'unknown')}. "
                    f"Beauty score: {vp.get('beauty_total', 0):.3f}."
                )
            }

        elif name == "export_drone_csv":
            if self.last_results:
                from pipeline import export_litchi_csv
                indices = inputs.get("viewpoint_indices", [])
                selected = [self.last_results[i - 1] for i in indices
                            if 0 < i <= len(self.last_results)]
                csv = export_litchi_csv(selected or self.last_results)
                return {"csv": csv, "waypoints": len(selected or self.last_results)}

        return {"error": f"Unknown tool: {name}"}

    def _fallback_response(self, message: str, pipeline_runner) -> dict:
        """Handle messages when Claude API is not available.
        Parse basic location requests and run pipeline directly.
        """
        msg_lower = message.lower()

        # Try to extract coordinates if mentioned
        # For demo: support a few well-known locations
        locations = {
            "yosemite": (37.7459, -119.5332),
            "half dome": (37.7459, -119.5332),
            "zermatt": (46.0207, 7.7491),
            "matterhorn": (45.9763, 7.6586),
            "grand canyon": (36.1069, -112.1129),
            "mount rainier": (46.8523, -121.7603),
            "mount fuji": (35.3606, 138.7274),
            "dolomites": (46.4102, 11.8440),
            "patagonia": (-50.3418, -72.2648),
            "swiss alps": (46.5, 7.9),
        }

        lat, lng = None, None
        for name, coords in locations.items():
            if name in msg_lower:
                lat, lng = coords
                break

        if lat is not None and pipeline_runner:
            config = {
                "center_lat": lat,
                "center_lng": lng,
                "radius_km": 10,
                "mode": "drone" if "drone" in msg_lower else "ground",
                "max_results": 10,
            }

            # Adjust weights based on keywords
            if any(w in msg_lower for w in ["dramatic", "cliff", "rugged"]):
                config["feature_weights"] = {"cliffs": 0.9, "relief": 0.8, "peaks": 0.7}
            if any(w in msg_lower for w in ["serene", "peaceful", "calm"]):
                config["feature_weights"] = {"water": 0.9, "peaks": 0.5}
            if "depth" in msg_lower or "layers" in msg_lower:
                config["beauty_weights"] = {"depth_layering": 0.3}

            results = pipeline_runner(config)
            self.last_results = results

            return {
                "response": (
                    f"Found {len(results)} viewpoints near "
                    f"({lat:.4f}, {lng:.4f}). "
                    f"Top viewpoint: beauty score {results[0].beauty_total:.3f}, "
                    f"composition: {results[0].composition}."
                    if results else
                    "No suitable viewpoints found in this area."
                ),
                "results": [r.to_dict() if hasattr(r, 'to_dict') else r for r in results] if results else [],
            }

        return {
            "response": (
                "I can help you find optimal photography angles! "
                "Try describing a location and what kind of shot you're looking for. "
                "For example: 'Find dramatic cliff shots near Yosemite' or "
                "'Show me panoramic viewpoints near the Dolomites'."
            ),
            "results": None,
        }
