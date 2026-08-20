# skills/vision_tools.py
import base64
import io
from langchain_core.tools import tool
from config.settings import GOOGLE_API_KEY

# A separate ChatGoogleGenerativeAI instance (not imported from llm/gemini.py) to avoid a
# circular import, since gemini.py imports this module's tools.
_vision_llm = None


def _get_vision_llm():
    global _vision_llm
    if _vision_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _vision_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
    return _vision_llm


def capture_screen():
    """Plain function: grabs a screenshot of the primary display. Local only, no network call."""
    from PIL import ImageGrab
    return ImageGrab.grab()


def _image_to_base64(img) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@tool
def read_screen_text() -> str:
    """Reads the text currently visible on screen using local OCR (no data leaves the device).
    Only use this when the user explicitly asks what's on their screen or to read something visible."""
    try:
        import pytesseract
    except ImportError:
        return "OCR isn't available — pytesseract isn't installed."

    try:
        image = capture_screen()
        text = pytesseract.image_to_string(image).strip()
    except Exception as e:
        return f"I couldn't read the screen: {e}"

    if not text:
        return "I didn't find any readable text on the screen."
    return text


@tool
def explain_screen(question: str = "What's wrong with this?") -> str:
    """Sends a screenshot of the current screen to Gemini's vision model to explain what's on it
    (e.g. a stack trace, an error, a diagram). This sends image data to Google's cloud API — only
    use this when the user explicitly asks about their screen and local OCR alone isn't enough."""
    try:
        image = capture_screen()
        image_b64 = _image_to_base64(image)
    except Exception as e:
        return f"I couldn't capture the screen: {e}"

    try:
        from langchain_core.messages import HumanMessage
        message = HumanMessage(content=[
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": f"data:image/png;base64,{image_b64}"},
        ])
        response = _get_vision_llm().invoke([message])
        return str(response.content)
    except Exception as e:
        return f"I couldn't analyze the screen: {e}"
