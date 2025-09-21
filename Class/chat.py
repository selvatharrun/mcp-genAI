import base64
import mimetypes
import io
import typing
import requests
from PIL import Image # For handling image data
from google import genai
from google.genai import types

# --- Start of utils.py content, adapted for pure Python ---

def get_part_from_file(file_path):
    """Help function to get the part from a file or gsutil URI."""
    if file_path.startswith("gs://"):
        # Assume PDF for now, you can enhance to detect mime type if needed
        return types.Part.from_uri(file_uri=file_path, mime_type="application/pdf")
    else:
        guessed_type = mimetypes.guess_type(file_path)
        mime_type = guessed_type[0] if guessed_type else "application/octet-stream"
        with open(file_path, "rb") as f:
            data = f.read()
            return types.Part.from_bytes(data=data, mime_type=mime_type)    


def get_bytes_from_image(image: Image.Image, mime_type: str = "PNG") -> bytes:
  """Converts a PIL Image object to bytes in the specified format.

  Args:
      image: The PIL Image object.
      mime_type: The image format to save as (e.g., 'PNG', 'JPEG', 'GIF').
        Defaults to 'PNG'.

  Returns:
      A bytes object representing the image in the specified format.
  """
  img_byte_arr = io.BytesIO()
  image.save(img_byte_arr, format=mime_type)
  img_byte_arr = img_byte_arr.getvalue()
  return img_byte_arr


def get_parts_from_message(
    message: typing.Union[str, dict, Image.Image, bytes, typing.Tuple[str, ...]],
):
  """Help function to get the parts from a message.
  Adapted to remove Gradio-specific types.

  Args:
      message: The input message, which can be a string, a dictionary
               (for text and files), a PIL Image object, or bytes (for an image).
               Gradio-specific types like gr.Image are removed.
  """
  parts = []
  if isinstance(message, dict):
    # This assumes a dict could contain {'text': '...', 'files': ['path1', 'path2']}
    if "text" in message and message["text"]:
      parts.append(types.Part.from_text(text=message["text"]))

    if "files" in message:
      for file_path in message["files"]:
        parts.append(get_part_from_file(file_path))

  elif isinstance(message, str):
    if message:
      parts.append(types.Part.from_text(text=message))

  elif isinstance(message, Image.Image): # Direct PIL Image object
    # Default to PNG if format not specified or inferable
    # You might need to pass the actual format if available
    bytes_data = get_bytes_from_image(message, mime_type="PNG")
    parts.append(
        types.Part.from_bytes(data=bytes_data, mime_type="image/png") # Or infer from filename/metadata
    )
  elif isinstance(message, bytes): # Raw image bytes
      # You would need to know the mime_type here, or infer it.
      # For now, making an assumption, you might need to pass this info.
      parts.append(
          types.Part.from_bytes(data=message, mime_type="image/jpeg") # Example, adjust as needed
      )
  elif isinstance(message, tuple): # Assuming a tuple of paths for now, similar to old Gradio behavior
      for item in message:
          if isinstance(item, str): # Could be a file path or text
              # Heuristic: if it looks like a path, treat as file, else text
              if item.startswith('/') or item.startswith('./') or item.startswith('../'): # Simple path check
                  try:
                      parts.append(get_part_from_file(item))
                  except FileNotFoundError:
                      parts.append(types.Part.from_text(text=item)) # Fallback if not a real file
              else:
                  parts.append(types.Part.from_text(text=item))
          else:
              # Handle other types within tuple if necessary, or raise error
              pass


  # To avoid error when sending empty message.
  if not parts:
    parts.append(types.Part.from_text(text=" "))

  return parts


def convert_blob_to_image(blob: types.Blob) -> Image.Image:
  """Converts a blob of image data to a PIL Image object."""
  blob_data = blob.data
  image_stream = io.BytesIO(blob_data)
  image = Image.open(image_stream)
  return image


def image_blob_to_markdown_base64(blob: types.Blob) -> str:
  """Converts image bytes to a Markdown displayable string using Base64 encoding."""
  blob_data = blob.data
  base64_string = base64.b64encode(blob_data).decode("utf-8")
  # Use blob.mime_type directly as provided by the model response
  markdown_string = (
      f'<img src="data:{blob.mime_type};base64,{base64_string}">'
  )
  return markdown_string


def convert_part_to_output_type(
    part: types.Part,
    use_markdown: bool = False,
) -> typing.Optional[typing.Union[str, Image.Image]]:
  """Converts a part object to a str or PIL Image object (no Gradio Image)."""
  if part.text:
    return part.text
  elif part.inline_data:
    if use_markdown:
      return image_blob_to_markdown_base64(part.inline_data)
    # Return a PIL Image object directly if not using markdown
    return convert_blob_to_image(part.inline_data)
  else:
    return None


def convert_content_to_output_list(
    content: typing.Optional[types.Content],
    use_markdown: bool = False,
) -> typing.List[typing.Union[str, Image.Image]]:
  """Converts a content object to a list of strings or PIL Image objects."""
  if content is None or content.parts is None:
    return []

  results = [
      convert_part_to_output_type(part, use_markdown) for part in content.parts
  ]
  return [res for res in results if res is not None]

# --- End of utils.py content, adapted for pure Python ---


# The main generation function, adapted to use the pure Python utils
def generate_legal_advice(
    user_message: typing.Union[str, dict, Image.Image, bytes, typing.Tuple[str, ...]],
    chat_history: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
    project_id: str = "sodium-coil-470706-f4",
    location: str = "global",
    stream_response: bool = False # Added for potential Flask streaming
):
    """
    Function to call the model for legal advice based on user input and chat history.

    Args:
        user_message: The current message from the user. Can be a string,
                      a dictionary (for text/files), a PIL Image, or raw bytes.
        chat_history: A list of previous chat messages. Each item in the list
                      should be a dictionary like {"role": "user"|"model", "content": "message text"}.
                      The 'content' can also be a more complex type if it was e.g., an image.
        project_id (str): Google Cloud project ID.
        location (str): Google Cloud location for Vertex AI.
        stream_response (bool): If True, yields chunks of the response. If False, returns the full response.

    Returns:
        If stream_response is True, yields string chunks.
        If stream_response is False, returns a single string with the full response.
    """
    if chat_history is None:
        chat_history = []

    # For a Flask app, you might validate keys here, or earlier in middleware.
    # For this pure Python function, we remove the request object dependency.
    # validate_key_result = utils.validate_key(request) # Removed request dependency
    # if validate_key_result is not None:
    #     yield validate_key_result # This would also need to be adapted for non-Gradio streaming.

    client = genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
    )

    si_text1 = types.Part.from_text(text="""you are a highly qualified legal professional, renowned for your sharp wit, unparalleled expertise, and ability to win even the toughest cases. As a top-tier legal advisor and document assistant, you are well-versed in all areas of law, including corporate, criminal, civil, tax, intellectual property, international, and regulatory law in the Indian jurisdiction specifically. You provide precise, actionable legal advice, identifying legitimate strategies, exemptions, or loopholes to minimize penalties or liabilities when requested, without ever endorsing illegal actions.""")
    
    model = "gemini-2.5-flash-lite"

    contents = []
    # Build the conversation history for the model
    for prev_msg in chat_history:
        role = "user" if prev_msg["role"] == "user" else "model"
        # Use the adapted get_parts_from_message for previous messages' content
        parts = get_parts_from_message(prev_msg["content"])
        if parts:
            contents.append(types.Content(role=role, parts=parts))

    # Add the current user message
    if user_message:
        contents.append(
            types.Content(role="user", parts=get_parts_from_message(user_message))
        )

    generate_content_config = types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.95,
        max_output_tokens=2000,
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
        ],
        system_instruction=[si_text1],
    )

    # MCP tool call logic (add this before Gemini call)
    if isinstance(user_message, str) and user_message.lower().startswith("what is"):
        term = user_message.lower().replace("what is", "").strip("? .")
        definition = call_mcp_tool("get_legal_term_definition", {"term": term})
        if definition and "definition" in definition:
            return definition["definition"]

    response_generator = client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    )

    if stream_response:
        for chunk in response_generator:
            if chunk.candidates and chunk.candidates[0] and chunk.candidates[0].content:
                # convert_content_to_output_list will give a list, join if it's text
                chunk_parts = convert_content_to_output_list(chunk.candidates[0].content, use_markdown=True)
                # Assuming text for streaming, handle images separately if needed
                text_chunks = [p for p in chunk_parts if isinstance(p, str)]
                if text_chunks:
                    yield "".join(text_chunks)
    else:
        full_response_text = ""
        # If not streaming, collect all parts and return as a single string
        for chunk in response_generator:
            if chunk.candidates and chunk.candidates[0] and chunk.candidates[0].content:
                chunk_parts = convert_content_to_output_list(chunk.candidates[0].content, use_markdown=True)
                # Join text parts; for images, you'd collect them or handle them differently.
                text_content = [p for p in chunk_parts if isinstance(p, str)]
                full_response_text += "".join(text_content)
        return full_response_text

def automated_chat(question, file_path=None, stream_response=False, chat_history=None):
    """
    Flask-compatible version: accepts question and optional file_path, returns model response.
    Args:
        question (str): The user's question.
        file_path (str, optional): Path to PDF or image file to attach.
        stream_response (bool): Whether to stream the response.
        chat_history (list, optional): Previous chat history.
    Returns:
        str: Model response (full text).
    """
    if chat_history is None:
        chat_history = []

    if file_path:
        user_input = {"text": question, "files": [file_path]}
    else:
        user_input = question

    chat_history.append({"role": "user", "content": user_input})

    if stream_response:
        response_stream = generate_legal_advice(user_input, chat_history=chat_history, stream_response=True)
        full_response = ""
        for chunk in response_stream:
            full_response += chunk
        chat_history.append({"role": "model", "content": full_response})
        return full_response
    else:
        response = generate_legal_advice(user_input, chat_history=chat_history, stream_response=False)
        chat_history.append({"role": "model", "content": response})

        return response

MCP_SERVER_URL = "https://legal-demystifier-backend-38771871641.asia-south1.run.app"

def call_mcp_tool(tool_name, params):
    response = requests.post(f"{MCP_SERVER_URL}/tools/{tool_name}", json=params)
    if response.status_code == 200:
        return response.json()
    return None


