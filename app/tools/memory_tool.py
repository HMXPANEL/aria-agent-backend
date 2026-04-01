from typing import Any
from app.tools.registry import tool_registry
from app.core.memory_agent import memory_agent
from app.utils.logger import logger

@tool_registry.register(
    name="memory_store",
    description="Store information in the agent's long-term memory."
)
async def memory_store(key: str, value: Any, user_id: str = "default_user") -> str:
    """
    Store information in memory.
    """
    logger.info(f"Storing in memory: {key}")
    await memory_agent.store_semantic(user_id, f"{key}: {value}")
    return f"Successfully stored '{key}' in memory."

@tool_registry.register(
    name="memory_retrieve",
    description="Retrieve information from the agent's long-term memory."
)
async def memory_retrieve(query: str, user_id: str = "default_user") -> str:
    """
    Retrieve information from memory.
    """
    logger.info(f"Retrieving from memory: {query}")
    results = await memory_agent.retrieve_context(user_id, query)
    experiences = results.get("relevant_past_experiences", [])
    if not experiences:
        return "No relevant information found in memory."
    return f"Relevant information from memory: {'; '.join(experiences)}"
