import json
from typing import Dict, Any
from app.services.llm import llm_service
from app.utils.logger import logger

class IntentDetector:
    def __init__(self):
        self.llm = llm_service

    async def detect(self, text: str) -> Dict[str, Any]:
        """
        Detect the intent of the user's input (chat, action, task) using LLM-based classification.
        Returns a dictionary with 'intent', 'confidence', and 'entities'.
        """
        prompt = f"""
        Analyze the following user input and classify its primary intent as 'chat', 'action', or 'task'.
        'chat': User is asking a question, making a statement, or engaging in general conversation.
        'action': User is requesting a single, direct action that can be performed by a tool (e.g., "Open YouTube").
        'task': User is requesting a multi-step process that requires planning (e.g., "Search for AI news and summarize it").

        User Input: "{text}"

        Return a JSON object with the following structure:
        {{
            "intent": "chat | action | task",
            "confidence": 0.0-1.0,
            "entities": {{}}
        }}
        """
        try:
            response = await self.llm.generate_text(prompt)
            # Simple JSON extraction
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                intent_data = json.loads(response[start:end])
                return intent_data
            else:
                logger.error(f"Failed to parse intent from LLM response: {response}")
                return {"intent": "unknown", "confidence": 0.0, "entities": {}}
        except Exception as e:
            logger.error(f"Error detecting intent: {e}")
            return {"intent": "unknown", "confidence": 0.0, "entities": {}}

intent_detector = IntentDetector()
