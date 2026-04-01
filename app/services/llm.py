from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import List, Dict, Any, Optional
from app.config import settings
from app.utils.logger import logger
import asyncio

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.NVIDIA_API_KEY,
            base_url=settings.NVIDIA_BASE_URL
        )
        self.model = settings.NVIDIA_MODEL_NAME
        self.default_temp = 0.3
        self.max_tokens = 1000
        self.timeout = 30.0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(f"Retrying LLM call... Attempt {retry_state.attempt_number}")
    )
    async def _call_nvidia(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        """
        Internal method to call NVIDIA API with retries.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature if temperature is not None else self.default_temp,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"NVIDIA API Error: {e}")
            raise e

    async def generate_text(self, prompt: str, system_prompt: str = "You are a helpful AI assistant.") -> str:
        """
        Generate a clean text response from a single prompt.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        return await self._call_nvidia(messages)

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Handle a multi-turn chat conversation.
        """
        return await self._call_nvidia(messages)

    async def plan(self, task_description: str, context: Optional[str] = None) -> str:
        """
        Specialized function for generating plans with lower temperature.
        """
        system_prompt = "You are an expert task planner. Break down the user's goal into logical, executable steps."
        prompt = f"Goal: {task_description}\nContext: {context if context else 'No additional context.'}\nGenerate a detailed plan."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        # Use lower temperature for planning to ensure consistency
        return await self._call_nvidia(messages, temperature=0.2)

    async def generate(self, prompt: str, system_prompt: str = "You are a helpful AI assistant.") -> str:
        """
        Legacy compatibility method for existing code.
        """
        return await self.generate_text(prompt, system_prompt)

llm_service = LLMService()
