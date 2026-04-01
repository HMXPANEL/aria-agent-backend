import json
import asyncio
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.utils.logger import logger
from app.config import settings
from app.core.safety import safety_layer
from app.core.vision.vision_service import vision_service
from app.core.controller_agent import controller_agent

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.device_screenshots: Dict[str, str] = {}
        self.command_responses: Dict[str, asyncio.Event] = {}
        self.command_results: Dict[str, Any] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"WebSocket connected for user: {user_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"WebSocket disconnected for user: {user_id}")

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def send_command_to_device(self, user_id: str, command_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a command to the connected Android device and waits for a response.
        """
        if user_id not in self.active_connections:
            logger.warning(f"No active WebSocket connection for user {user_id} to send command.")
            return {"status": "error", "message": "No device connected."}
        
        command_id = str(uuid.uuid4())
        command_payload["command_id"] = command_id
        
        # Create an event to wait for the response
        response_event = asyncio.Event()
        self.command_responses[command_id] = response_event
        
        await self.active_connections[user_id].send_text(json.dumps(command_payload))
        logger.info(f"Command {command_id} sent to device for user {user_id}: {command_payload}")
        
        try:
            # Wait for the response event to be set, with a timeout
            await asyncio.wait_for(response_event.wait(), timeout=30.0)
            result = self.command_results.pop(command_id, {"status": "error", "message": "No result received."})
            return result
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for response for command {command_id} from device {user_id}")
            self.command_responses.pop(command_id, None)
            return {"status": "error", "message": "Command response timed out."}
        except Exception as e:
            logger.error(f"Error sending command and waiting for response: {e}")
            self.command_responses.pop(command_id, None)
            return {"status": "error", "message": str(e)}

websocket_manager = ConnectionManager()

@router.websocket("/ws/device/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, secret: str = Query(None)):
    """
    WebSocket endpoint for Android device connection.
    Supports real-time screen streaming and command execution.
    """
    if secret != settings.ANDROID_WEBSOCKET_SECRET:
        logger.warning(f"Unauthorized WebSocket connection attempt for user {user_id} with secret: {secret}")
        await websocket.close(code=1008)
        return

    await websocket_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "screenshot":
                # Handle incoming screenshot
                screenshot_data = message.get("data")
                if screenshot_data:
                    websocket_manager.device_screenshots[user_id] = screenshot_data
                    logger.debug(f"Received screenshot from user {user_id}. Size: {len(screenshot_data)} bytes")
                    
                    # Trigger vision processing and agent awareness loop in background
                    asyncio.create_task(websocket_manager._process_screenshot_and_act(user_id, screenshot_data))

            elif msg_type == "command_response":
                command_id = message.get("command_id")
                if command_id and command_id in websocket_manager.command_responses:
                    websocket_manager.command_results[command_id] = message
                    websocket_manager.command_responses[command_id].set() # Signal that response is ready
                    logger.info(f"Received response for command {command_id} from device {user_id}.")
                else:
                    logger.warning(f"Received unhandled command response from device {user_id}: {message}")

            elif msg_type == "event":
                event_data = message.get("data")
                logger.info(f"Received event from device {user_id}: {event_data}")
                # Potentially feed this event to the controller agent for observation

            else:
                logger.warning(f"Unknown message type from device {user_id}: {message}")

    except WebSocketDisconnect:
        websocket_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        websocket_manager.disconnect(user_id)

async def _process_screenshot_and_act(user_id: str, screenshot_data: str):
    """
    Process the screenshot and feed it to the agent for awareness and action.
    This is a helper function, not a method of ConnectionManager.
    """
    try:
        vision_output = await vision_service.analyze_screenshot(screenshot_data)
        logger.info(f"Vision analysis for user {user_id}: {vision_output}")
        
        # Update agent's working memory with vision output
        if user_id in controller_agent.active_states:
            state = controller_agent.active_states[user_id]
            state.working_memory["last_screen_analysis"] = vision_output
            # Potentially trigger a re-evaluation or planning step in the agent's cognition loop
            # This part needs careful integration with the main cognition loop to avoid race conditions
            logger.info(f"Agent state for {user_id} updated with vision output.")

    except Exception as e:
        logger.error(f"Error processing screenshot for user {user_id}: {e}")

# Assign the helper function to the manager for internal use
websocket_manager._process_screenshot_and_act = _process_screenshot_and_act
