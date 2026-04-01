from typing import Dict, Any
from app.utils.logger import logger
from app.tools.registry import tool_registry

class AndroidTool:
    def __init__(self):
        pass

    @tool_registry.register(
        name="android.tap",
        description="Generates a structured command to tap on the Android screen at specified coordinates (x, y)."
    )
    async def tap(self, x: int, y: int) -> Dict[str, Any]:
        """
        Generates a structured command to tap on the Android screen at specified coordinates.
        """
        logger.info(f"AndroidTool: Generating tap command at ({x}, {y})")
        return {"command": "tap", "args": {"x": x, "y": y}}

    @tool_registry.register(
        name="android.swipe",
        description="Generates a structured command to swipe on the Android screen from (x1, y1) to (x2, y2)."
    )
    async def swipe(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """
        Generates a structured command to swipe on the Android screen from (x1, y1) to (x2, y2).
        """
        logger.info(f"AndroidTool: Generating swipe command from ({x1}, {y1}) to ({x2}, {y2})")
        return {"command": "swipe", "args": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}}

    @tool_registry.register(
        name="android.type",
        description="Generates a structured command to type the given text on the Android device."
    )
    async def type(self, text: str) -> Dict[str, Any]:
        """
        Generates a structured command to type the given text on the Android device.
        """
        logger.info(f"AndroidTool: Generating type command with text: {text}")
        return {"command": "type", "args": {"text": text}}

    @tool_registry.register(
        name="android.open_app",
        description="Generates a structured command to open an Android application by its package name."
    )
    async def open_app(self, package_name: str) -> Dict[str, Any]:
        """
        Generates a structured command to open an Android application by its package name.
        """
        logger.info(f"AndroidTool: Generating open_app command for package: {package_name}")
        return {"command": "open_app", "args": {"package_name": package_name}}

    @tool_registry.register(
        name="android.get_screenshot",
        description="Generates a structured command to request a screenshot from the Android device."
    )
    async def get_screenshot(self) -> Dict[str, Any]:
        """
        Generates a structured command to request a screenshot from the Android device.
        """
        logger.info("AndroidTool: Generating get_screenshot command.")
        return {"command": "get_screenshot", "args": {}}

    @tool_registry.register(
        name="android.observe_and_act",
        description="Generates a structured command to analyze the current screen and perform an action based on the goal."
    )
    async def observe_and_act(self, goal: str) -> Dict[str, Any]:
        """
        Generates a structured command to analyze the current screen and perform an action based on the goal.
        """
        logger.info(f"AndroidTool: Generating observe_and_act command for goal: {goal}")
        return {"command": "observe_and_act", "args": {"goal": goal}}

android_tool = AndroidTool()
