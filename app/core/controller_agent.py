import uuid
import asyncio
import time
from typing import List, Dict, Any, Optional
from app.models.schemas import ChatRequest, ChatResponse, TaskRequest, TaskResponse, Intent, TaskStatus, TaskStep
from app.models.agent_state import AgentState
from app.core.intent import intent_detector
from app.core.planner_agent import planner_agent
from app.core.executor_agent import executor_agent
from app.core.critic_agent import critic_agent
from app.core.memory_agent import memory_agent
from app.services.llm import llm_service
from app.utils.logger import logger
from app.core.safety import safety_layer
from app.config import settings

class ControllerAgent:
    def __init__(self):
        self.intent_detector = intent_detector
        self.planner = planner_agent
        self.executor = executor_agent
        self.critic = critic_agent
        self.memory = memory_agent
        self.llm = llm_service
        self.safety = safety_layer
        self.active_states: Dict[str, AgentState] = {}
        self.active_loops: Dict[str, bool] = {}

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """
        Handle a natural language chat request.
        """
        logger.info(f"Handling chat request: {request.message}")
        
        # Detect intent
        intent_data = await self.intent_detector.detect(request.message)
        intent = intent_data["intent"]
        logger.info(f"Detected intent: {intent} with confidence: {intent_data['confidence']}")
        
        if intent == "chat":
            # Answer directly using LLM
            response_text = await self.llm.generate_text(request.message)
            # Update memory
            await self.memory.add_short_term(request.user_id, {"role": "user", "content": request.message})
            await self.memory.add_short_term(request.user_id, {"role": "assistant", "content": response_text})
            return ChatResponse(response=response_text, intent=Intent.INFO)
        
        elif intent == "action" or intent == "task":
            # Create a task and return task ID
            task_id = str(uuid.uuid4())
            # Initialize Agent State
            state = AgentState(task_id=task_id, goal=request.message, user_id=request.user_id)
            self.active_states[task_id] = state
            # Start autonomous cognition loop in background
            asyncio.create_task(self.cognition_loop(task_id))
            return ChatResponse(response="Autonomous multi-agent task started.", intent=Intent.TASK, task_id=task_id)
        else:
            return ChatResponse(response="I\'m not sure how to handle that. Can you rephrase?", intent=Intent.UNKNOWN)

    async def cognition_loop(self, task_id: str):
        """
        The advanced cognition loop: Observe -> Thought -> Reason -> Plan -> Action -> Observation -> Reflection -> Learning.
        """
        state = self.active_states.get(task_id)
        if not state: return
        
        logger.info(f"Starting cognition loop for task {task_id}: {state.goal}")
        self.active_loops[task_id] = True
        state.current_status = TaskStatus.RUNNING
        
        iteration = 0
        
        try:
            while self.active_loops.get(task_id) and iteration < settings.MAX_AGENT_ITERATIONS:
                iteration += 1
                logger.info(f"Cognition Iteration {iteration} for task {task_id}")
                
                # Check kill switch
                if self.safety.is_killed(task_id):
                    state.current_status = TaskStatus.CANCELLED
                    state.error_message = "Task terminated by kill switch."
                    logger.warning(f"Cognition loop for task {task_id} terminated by kill switch.")
                    break

                # 1. Observe (input, memory, environment, screen)
                context = await self.memory.retrieve_context(state.user_id, state.goal)
                state.working_memory.update(context)
                
                # 2. Thought (what is happening?)
                thought_prompt = f"Goal: {state.goal}\nContext: {state.working_memory}\nWhat is the current situation and what should be our focus?"
                state.thoughts = await self.llm.generate_text(thought_prompt)
                
                # 3. Reason (why? what are options?)
                reason_prompt = f"Goal: {state.goal}\nThoughts: {state.thoughts}\nReason about the best approach to achieve the goal. Consider potential obstacles."
                state.reasoning = await self.llm.generate_text(reason_prompt)
                
                # 4. Plan (multi-step strategy)
                new_steps = await self.planner.generate_plan(state)
                if not new_steps:
                    logger.warning(f"No steps generated for task {task_id}. Attempting to replan.")
                    new_steps = await self.planner.replan(state, "No steps generated initially.")
                    if not new_steps:
                        state.error_message = "Failed to generate a plan."
                        state.current_status = TaskStatus.FAILED
                        break

                state.current_steps.extend(new_steps)
                
                # 5. Action (tool execution)
                needs_replanning = False
                for step in new_steps:
                    if not self.active_loops.get(task_id): break
                    
                    observation = await self.executor.execute_step(step, state.user_id, task_id)
                    state.last_observation = str(observation)
                    
                    # 6. Observation (result feedback)
                    evaluation = await self.critic.evaluate_step(step, observation, state)
                    state.critic_feedback = evaluation.get("feedback")
                    
                    if evaluation.get("is_goal_achieved"):
                        logger.info(f"Goal achieved for task {task_id}")
                        self.active_loops[task_id] = False
                        break
                    
                    if evaluation.get("needs_replanning"):
                        logger.warning(f"Replanning needed for task {task_id}: {state.critic_feedback}")
                        needs_replanning = True
                        break # Break step loop to replan in next cognition iteration
                
                if not self.active_loops.get(task_id): # Goal achieved or killed
                    break

                if needs_replanning:
                    # Clear current steps for replanning
                    state.current_steps = [] 
                    continue # Start new cognition iteration for replanning

                # 7. Reflection (what worked / failed)
                reflection = await self.critic.reflect_on_iteration(state, iteration)
                state.insights = reflection.get("insights")
                
                # 8. Learning (store improvements)
                await self.memory.store_episodic(state.user_id, task_id, state.goal, state.insights)
                
                await asyncio.sleep(settings.AGENT_LOOP_INTERVAL_SEC) # Prevent tight loop
            
        except Exception as e:
            logger.error(f"Error in cognition loop for task {task_id}: {e}")
            state.error_message = str(e)
            state.current_status = TaskStatus.FAILED
        finally:
            if state.current_status == TaskStatus.RUNNING:
                state.current_status = TaskStatus.COMPLETED # If loop finished without explicit failure
            self.active_loops[task_id] = False
            logger.info(f"Cognition loop for task {task_id} finished with status: {state.current_status}")

    def get_task_status(self, task_id: str) -> Optional[TaskResponse]:
        state = self.active_states.get(task_id)
        if not state: return None
        return TaskResponse(task_id=task_id, status=state.current_status, steps=state.current_steps)

    def stop_task(self, task_id: str):
        self.active_loops[task_id] = False
        if task_id in self.active_states:
            self.active_states[task_id].current_status = TaskStatus.CANCELLED
            logger.info(f"Task {task_id} explicitly cancelled.")

controller_agent = ControllerAgent()
