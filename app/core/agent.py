import uuid
import asyncio
import time
from typing import List, Dict, Any, Optional
from app.models.schemas import ChatRequest, ChatResponse, TaskRequest, TaskResponse, Intent, TaskStatus, TaskStep
from app.core.intent import intent_detector
from app.core.planner import planner
from app.core.executor import executor
from app.core.memory import memory_system
from app.services.llm import llm_service
from app.utils.logger import logger

class Agent:
    def __init__(self):
        self.intent_detector = intent_detector
        self.planner = planner
        self.executor = executor
        self.memory_system = memory_system
        self.llm = llm_service
        self.tasks: Dict[str, TaskResponse] = {}
        self.active_loops: Dict[str, bool] = {}

    async def handle_chat(self, request: ChatRequest) -> ChatResponse:
        """
        Handle a natural language chat request.
        """
        logger.info(f"Handling chat request: {request.message}")
        
        # Detect intent
        intent = await self.intent_detector.detect(request.message)
        logger.info(f"Detected intent: {intent}")
        
        if intent == Intent.INFO:
            # Answer directly using LLM
            response_text = await self.llm.generate(request.message)
            # Update memory
            self.memory_system.add_short_term(request.user_id, {"role": "user", "content": request.message})
            self.memory_system.add_short_term(request.user_id, {"role": "assistant", "content": response_text})
            return ChatResponse(response=response_text, intent=intent)
        
        elif intent == Intent.TASK:
            # Create a task and return task ID
            task_id = str(uuid.uuid4())
            # Start autonomous agent loop in background
            asyncio.create_task(self.autonomous_loop(task_id, request.message, request.user_id))
            return ChatResponse(response="Autonomous task started in background.", intent=intent, task_id=task_id)

    async def autonomous_loop(self, task_id: str, goal: str, user_id: str):
        """
        The core autonomous loop: Observe -> Think -> Plan -> Act -> Reflect -> Learn.
        """
        logger.info(f"Starting autonomous loop for task {task_id}: {goal}")
        self.active_loops[task_id] = True
        self.tasks[task_id] = TaskResponse(task_id=task_id, status=TaskStatus.RUNNING, steps=[])
        
        max_iterations = 10
        iteration = 0
        
        while self.active_loops.get(task_id) and iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration} for task {task_id}")
            
            # 1. Observe State & Update Memory
            working_memory = self.memory_system.get_working_memory(user_id)
            context_summary = await self.memory_system.summarize_context(user_id)
            
            # 2. Generate Thoughts & Create Plan
            steps = await self.planner.plan(goal, user_id, context={"iteration": iteration, "working_memory": working_memory, "context_summary": context_summary})
            if not steps:
                logger.warning(f"No steps generated for task {task_id}. Stopping loop.")
                break
            
            self.tasks[task_id].steps.extend(steps)
            
            # 3. Execute Actions
            for step in steps:
                result = await self.executor.execute_step(step)
                # Update working memory with step result
                self.memory_system.update_working_memory(user_id, {f"step_{step.id}_result": result})
                
                # Check for task completion or failure
                if "task completed" in str(result).lower():
                    logger.info(f"Task {task_id} completed successfully.")
                    self.active_loops[task_id] = False
                    break
                
                if step.status == TaskStatus.FAILED:
                    logger.warning(f"Step failed: {step.description}. Attempting to replan...")
                    # Dynamic replanning could happen here
                    break
            
            # 4. Reflect & Learn
            await self.reflect_and_learn(task_id, goal, user_id, iteration)
            
            # Check if goal is achieved (simplified check)
            if not self.active_loops.get(task_id):
                break
                
            await asyncio.sleep(1) # Prevent tight loop
            
        self.tasks[task_id].status = TaskStatus.COMPLETED if not self.active_loops.get(task_id) else TaskStatus.FAILED
        logger.info(f"Autonomous loop for task {task_id} finished with status: {self.tasks[task_id].status}")

    async def reflect_and_learn(self, task_id: str, goal: str, user_id: str, iteration: int):
        """
        Analyze success/failure and store insights in memory.
        """
        task_response = self.tasks.get(task_id)
        if not task_response: return
        
        steps_summary = "; ".join([f"{s.description}: {s.status}" for s in task_response.steps[-5:]])
        prompt = f"""
        Reflect on the progress of the following task:
        Goal: "{goal}"
        Recent Steps: {steps_summary}
        Iteration: {iteration}
        
        What have we learned? Is the goal achieved? What should be improved?
        Return a brief summary of insights.
        """
        insights = await self.llm.generate(prompt)
        logger.info(f"Reflection insights for task {task_id}: {insights}")
        
        # Store in episodic memory
        self.memory_system.add_episodic(user_id, task_id, goal, str(task_response.status), insights)
        
        # If insights suggest completion, stop the loop
        if "goal achieved" in insights.lower() or "task finished" in insights.lower():
            self.active_loops[task_id] = False

    def get_task_status(self, task_id: str) -> Optional[TaskResponse]:
        return self.tasks.get(task_id)

    def stop_task(self, task_id: str):
        self.active_loops[task_id] = False

agent = Agent()
