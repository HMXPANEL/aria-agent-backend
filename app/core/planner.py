import json
import uuid
from typing import List, Dict, Any, Optional
from app.models.schemas import TaskStep, TaskStatus
from app.services.llm import llm_service
from app.core.memory import memory_system
from app.utils.logger import logger

class Planner:
    def __init__(self):
        self.llm = llm_service
        self.memory = memory_system

    async def plan(self, goal: str, user_id: str = "default_user", context: Optional[Dict[str, Any]] = None) -> List[TaskStep]:
        """
        Break a goal into a series of structured steps with multi-step reasoning.
        """
        # Retrieve relevant past experiences from memory
        past_experiences = self.memory.retrieve_semantic(user_id, goal, n_results=3)
        working_memory = self.memory.get_working_memory(user_id)
        
        prompt = f"""
        You are an advanced AI agent planner. Your goal is to break down a complex task into a series of structured steps.
        
        Goal: "{goal}"
        
        Context: {json.dumps(context or working_memory)}
        Past Experiences: {json.dumps(past_experiences)}
        
        Available tools:
        - web_search(query: str): Search the web.
        - web_scrape(url: str): Scrape content from a URL.
        - file_write(filename: str, content: str): Write to a file.
        - file_read(filename: str): Read from a file.
        - tap(x: int, y: int): Tap on Android screen.
        - swipe(x1: int, y1: int, x2: int, y2: int): Swipe on Android screen.
        - type_text(text: str): Type text on Android device.
        - open_app(package_name: str): Open an Android app.
        - get_screenshot(): Get current Android screen.
        - observe_and_act(goal: str): Analyze screen and act.
        - shell_execute(command: str): Execute a shell command.
        - http_request(method: str, url: str, ...): Perform HTTP request.
        - memory_store(key: str, value: Any): Store in long-term memory.
        - memory_retrieve(key: str): Retrieve from long-term memory.

        Return the plan as a JSON list of objects with 'description', 'tool', and 'args' fields.
        Example:
        [
            {{"description": "Search for weather in Tokyo", "tool": "web_search", "args": {{"query": "weather in Tokyo"}}}},
            {{"description": "Save weather to file", "tool": "file_write", "args": {{"filename": "weather.txt", "content": "The weather is sunny."}}}}
        ]
        """
        try:
            response = await self.llm.generate(prompt)
            # Simple JSON extraction from LLM response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1 and end != -1:
                plan_json = json.loads(response[start:end])
                steps = []
                for step_data in plan_json:
                    steps.append(TaskStep(
                        id=str(uuid.uuid4()),
                        description=step_data["description"],
                        tool=step_data["tool"],
                        args=step_data["args"],
                        status=TaskStatus.PENDING
                    ))
                return steps
            else:
                logger.error(f"Failed to parse plan from LLM response: {response}")
                return []
        except Exception as e:
            logger.error(f"Error planning task: {e}")
            return []

    async def replan(self, goal: str, current_steps: List[TaskStep], failure_reason: str, user_id: str = "default_user") -> List[TaskStep]:
        """
        Dynamically replan based on a failure or new information.
        """
        logger.info(f"Replanning for goal: {goal} due to: {failure_reason}")
        # Similar to plan, but with failure context
        context = {"failure_reason": failure_reason, "completed_steps": [s.dict() for s in current_steps if s.status == TaskStatus.COMPLETED]}
        return await self.plan(goal, user_id, context=context)

planner = Planner()
