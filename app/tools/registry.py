import inspect
from typing import Dict, Any, Callable, Optional, Awaitable
from app.utils.logger import logger

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, schema: Optional[Dict[str, Any]] = None):
        def decorator(func: Callable[..., Awaitable[Any]]):
            self.tools[name] = {
                "func": func,
                "description": description,
                "schema": schema or self._generate_schema(func)
            }
            logger.info(f"Tool registered: {name}")
            return func
        return decorator

    def _generate_schema(self, func: Callable) -> Dict[str, Any]:
        sig = inspect.signature(func)
        schema = {"type": "object", "properties": {}, "required": []}
        for name, param in sig.parameters.items():
            if name == "self": continue
            param_type = "string"
            if param.annotation == int: param_type = "integer"
            elif param.annotation == bool: param_type = "boolean"
            elif param.annotation == dict: param_type = "object"
            
            schema["properties"][name] = {"type": param_type}
            if param.default == inspect.Parameter.empty:
                schema["required"].append(name)
        return schema

    async def execute(self, name: str, **kwargs) -> Any:
        if name not in self.tools:
            raise ValueError(f"Tool '{name}' not found in registry.")
        
        func = self.tools[name]["func"]
        logger.info(f"Executing tool '{name}' with args: {kwargs}")
        
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

tool_registry = ToolRegistry()
