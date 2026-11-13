# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import uuid
from zoneinfo import ZoneInfo

from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud import storage
from google.genai import types

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

try:
    from app.a2ui_utils import a2ui_callback
except ImportError:
    from a2ui_utils import a2ui_callback



MODEL = "gemini-3.8-flash"
BUCKET_NAME = "ordermate-media-qwiklabs-gcp-04-f13d121e1410"
PROJECT_ID = "qwiklabs-gcp-04-f13d121e1410"



def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def search_products(query: str) -> str:
    """Search for retail products to inspect details, prices, warranty, and return policies.

    Args:
        query: Product name, category, or keyword to search for (e.g. 'laptop', 'shoes', 'phone').

    Returns:
        JSON string containing matching products with pricing, shipping info, and return policies.
    """
    import json
    import urllib.parse
    import urllib.request

    url = f"https://dummyjson.com/products/search?q={urllib.parse.quote(query)}&limit=3"
    req = urllib.request.Request(url, headers={"User-Agent": "OrderMate/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            results = []
            for p in data.get("products", []):
                results.append({
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "category": p.get("category"),
                    "price": p.get("price"),
                    "rating": p.get("rating"),
                    "warranty": p.get("warrantyInformation"),
                    "shipping": p.get("shippingInformation"),
                    "return_policy": p.get("returnPolicy"),
                    "stock": p.get("stock"),
                })
            return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch product data: {e}"})


async def generate_item_image(item_description: str, tool_context: ToolContext) -> str:
    """Generates an image for an item or product using gemini-3.1-flash-lite-image, saves it as an artifact, and uploads it to public Cloud Storage.

    Args:
        item_description: Description of the product, return item, or retail packaging to generate an image for.

    Returns:
        The public HTTPS URL of the uploaded image on Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=f"High quality clear product photograph of: {item_description}",
    )

    part = response.candidates[0].content.parts[0]
    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"
    ext = "jpg" if "jpeg" in mime_type else "png"
    filename = f"item_{uuid.uuid4().hex[:8]}.{ext}"

    # 1. Save artifact for the Playground's Artifacts panel
    if tool_context:
        try:
            await tool_context.save_artifact(
                filename=filename,
                artifact=types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            )
        except Exception:
            pass

    # 2. Upload bytes directly to the public Cloud Storage bucket in memory
    gcs_client = storage.Client(project=PROJECT_ID)
    bucket = gcs_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    # Return public HTTPS URL
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


async def generate_item_video(item_description: str, tool_context: ToolContext) -> str:
    """Generates a short preview or demonstration video for an item or product using Google's Omni model (gemini-omni-flash-preview) in the global region, saves it as an artifact, and uploads it to public Cloud Storage.

    Args:
        item_description: Description of the retail product, item demonstration, or return packaging to generate a short video clip for.

    Returns:
        The public HTTPS URL of the uploaded video on Cloud Storage.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    interaction = client.interactions.create(
        model="gemini-omni-flash-preview",
        input=f"A smooth, high quality product demonstration video of: {item_description}",
    )

    if not hasattr(interaction, "output_video") or not interaction.output_video:
        raise RuntimeError("No output video returned by Omni model.")

    video_bytes = base64.b64decode(interaction.output_video.data)
    mime_type = getattr(interaction.output_video, "mime_type", None) or "video/mp4"
    filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

    # 1. Save artifact for the Playground's Artifacts panel
    if tool_context:
        try:
            await tool_context.save_artifact(
                filename=filename,
                artifact=types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
            )
        except Exception:
            pass

    # 2. Upload bytes directly to the public Cloud Storage bucket in memory
    gcs_client = storage.Client(project=PROJECT_ID)
    bucket = gcs_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    # Return public HTTPS URL
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


SANDBOX_NAME = "projects/1047569611901/locations/us-east1/reasoningEngines/1072057921942061056/sandboxEnvironments/5945697088128942080"
code_executor = AgentEngineSandboxCodeExecutor(sandbox_resource_name=SANDBOX_NAME)

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="OrderMate Concierge, a helpful retail and customer concierge assistant designed to help shoppers search products, check return policies and shipping terms, generate product or item visuals and videos, and resolve order issues. You can also execute Python code in the sandbox to accurately compute prices, taxes, discounts, or refund amounts.",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

ordermate_concierge = Agent(
    name="ordermate_concierge",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[generate_item_video, generate_item_image, search_products, get_weather, get_current_time],
    code_executor=code_executor,
    after_model_callback=a2ui_callback,
)

# Alias for backwards compatibility with framework and runner imports
root_agent = ordermate_concierge



app = App(
    root_agent=ordermate_concierge,
    name="app",
)



