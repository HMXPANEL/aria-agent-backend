import base64
import io
import json
import asyncio
from PIL import Image
from pytesseract import image_to_data, Output
from typing import Dict, Any, List
from app.utils.logger import logger
from app.services.llm import llm_service

class VisionService:
    def __init__(self):
        self.llm = llm_service

    async def analyze_screenshot(self, base64_image: str) -> Dict[str, Any]:
        """
        Analyzes a base64 encoded screenshot to extract text, buttons, and fields.
        """
        logger.info("Analyzing screenshot for vision understanding.")
        try:
            # Decode base64 image
            image_bytes = base64.b64decode(base64_image)
            image = Image.open(io.BytesIO(image_bytes))

            # Perform OCR using pytesseract in a thread pool executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, lambda: image_to_data(image, output_type=Output.DICT))

            texts = []
            # Initialize buttons and fields as empty lists, to be populated by LLM or more advanced vision
            buttons = [] 
            fields = []  

            n_boxes = len(data["level"])
            for i in range(n_boxes):
                # Filter out empty text and low confidence results
                if int(data["conf"][i]) > 60 and data["text"][i].strip():  
                    text = data["text"][i].strip()
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    texts.append({"text": text, "bbox": {"x": x, "y": y, "w": w, "h": h}})
            
            # Use LLM to identify buttons and fields from extracted text and their positions
            # This provides a more intelligent way to classify UI elements than simple OCR
            ui_analysis_prompt = f"""
            Given the following extracted texts and their bounding boxes from a screenshot, identify potential buttons and input fields. 
            Return a JSON object with two keys: 'buttons' and 'fields'. Each key should map to a list of dictionaries. Each dictionary should contain 'text' and 'bbox' (x, y, w, h).
            
            Extracted Texts: {json.dumps(texts)}
            
            Example Output:
            {{
                "buttons": [{{ "text": "Submit", "bbox": {{ "x": 100, "y": 200, "w": 50, "h": 30 }} }}],
                "fields": [{{ "text": "Search...", "bbox": {{ "x": 50, "y": 100, "w": 200, "h": 40 }} }}]
            }}
            """
            
            try:
                llm_analysis_response = await self.llm.generate_text(ui_analysis_prompt)
                llm_analysis = json.loads(llm_analysis_response)
                buttons = llm_analysis.get("buttons", [])
                fields = llm_analysis.get("fields", [])
            except Exception as llm_e:
                logger.warning(f"LLM failed to analyze UI elements: {llm_e}. Proceeding with OCR text only.")

            return {
                "texts": texts,
                "buttons": buttons,
                "fields": fields,
                # "raw_ocr_data": data # Uncomment for debugging raw OCR output
            }
        except Exception as e:
            logger.error(f"Error in vision service analyzing screenshot: {e}")
            return {"texts": [], "buttons": [], "fields": [], "error": str(e)}

vision_service = VisionService()
