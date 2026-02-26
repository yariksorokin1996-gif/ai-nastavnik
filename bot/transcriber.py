import io
from openai import AsyncOpenAI
from shared.config import OPENAI_API_KEY

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def transcribe_voice(voice_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Транскрибирует голосовое сообщение через OpenAI Whisper."""
    audio_file = io.BytesIO(voice_bytes)
    audio_file.name = "voice.ogg"

    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="ru",
    )
    return transcript.text
