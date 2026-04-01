import json
from typing import Dict, Any, Optional
from app.models.schemas import TaskStep, TaskStatus
from app.models.agent_state import AgentState
from app.services.llm import llm_service
from app.utils.logger import logger

class CriticAgent:
    def __init__(self):
        self.llm = llm_service

    async def evaluate_step(self, step: TaskStep, observation: Any, state: AgentState) -> Dict[str, Any]:
        """
        Evaluate the outcome of a single step.
        """
        logger.info(f"Critic Agent evaluating step: {step.description}")
        
        prompt = f"""
        Goal: {state.goal}
        Step: {step.description}
        Tool Used: {step.tool}
        Observation: {observation}
        
        Evaluate if this step was successful and if the overall goal is achieved.
        Return a JSON object with:
        - "is_successful": boolean
        - "is_goal_achieved": boolean
        - "needs_replanning": boolean
        - "feedback": string (explanation)
        """
        try:
            response = await self.llm.generate(prompt)
            # Simple JSON extraction
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(response[start:end])
            else:
                return {"is_successful": step.status == TaskStatus.COMPLETED, "is_goal_achieved": False, "needs_replanning": False, "feedback": "Evaluation failed to parse."}
        except Exception as e:
            logger.error(f"Error evaluating step: {e}")
            return {"is_successful": False, "is_goal_achieved": False, "needs_replanning": True, "feedback": str(e)}

    async def reflect_on_iteration(self, state: AgentState, iteration: int) -> Dict[str, Any]:
        """
        Reflect on the overall progress after an iteration.
        """
        logger.info(f"Critic Agent reflecting on iteration {iteration}")
        
        steps_summary = "; ".join([f"{s.description}: {s.status}" for s in state.current_steps[-5:]])
        prompt = f"""
        Reflect on the progress of the following task:
        Goal: "{state.goal}"
        Recent Steps: {steps_summary}
        Iteration: {iteration}
        Working Memory: {json.dumps(state.working_memory)}
        
        What have we learned? What should be improved in the next iteration?
        Return a JSON object with:
        - "insights": string (summary of learning)
        - "suggestions": list of strings (for improvement)
        """
        try:
            response = await self.llm.generate(prompt)
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(response[start:end])
            else:
                return {"insights": "Reflection failed to parse.", "suggestions": []}
        except Exception as e:
            logger.error(f"Error reflecting on iteration: {e}")
            return {"insights": str(e), "suggestions": []}

critic_agent = CriticAgent()
