import asyncio
import os
import webbrowser
import urllib.parse
from groq import Groq
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)

load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class TranscriptCollector:
    def __init__(self):
        self.reset()
        self.transcription_complete = asyncio.Event()

    def reset(self):
        self.transcript_parts = []

    def add_part(self, part):
        self.transcript_parts.append(part)

    def get_full_transcript(self):
        return ' '.join(self.transcript_parts)

transcript_collector = TranscriptCollector()

async def shutdown(dg_connection, microphone):
    try:
        print("Shutting down...")
        microphone.finish()  # Make sure to finish microphone
        await dg_connection.finish()  # Ensure Deepgram connection is finished
        print("Shutdown complete.")
    except Exception as e:
        print(f"Error during shutdown: {e}")


async def process_with_groq(content):
    attempts = 3
    while attempts > 0:
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": content}],
                model="llama3-8b-8192",
            )
            print(chat_completion.choices[0].message.content)
            break
        except Exception as e:
            print(f"Error while sending to Groq, attempts remaining: {attempts - 1}. Error: {e}")
            attempts -= 1
            await asyncio.sleep(1)

def open_google():
    webbrowser.open("https://www.google.com")

def search_google(query):
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(search_url)

async def chat_response(self, result, **kwargs):
    sentence = result.channel.alternatives[0].transcript
    if not sentence.strip(): 
        return
    
    if not result.speech_final:
        transcript_collector.add_part(sentence)
    else:
        transcript_collector.add_part(sentence)
        full_sentence = transcript_collector.get_full_transcript()
        print(f"speaker: {full_sentence}")

        if any(keyword in full_sentence.lower() for keyword in ["bye", "goodbye"]):
            print("Shutdown keyword detected. Exiting...")
            await shutdown(self.dg_connection, self.microphone)
            await self.websocket.close()
            return
        
        if "open google" in full_sentence.lower():
                open_google()
        elif "search" in full_sentence.lower():
            search_query = full_sentence.lower().replace("search", "").strip()
            search_google(search_query)
        else:
            content = full_sentence.strip()
            await process_with_groq(content)
        transcript_collector.reset()

async def get_transcript():
    try:
        config = DeepgramClientOptions(options={"keepalive": "true"})
        deepgram: DeepgramClient = DeepgramClient(DEEPGRAM_API_KEY, config)

        dg_connection = deepgram.listen.asynclive.v("1")
        print(dg_connection)
        print ("Listening...")


        async def on_error(self, error, **kwargs):
            print(f"\n\n{error}\n\n")

        dg_connection.on(LiveTranscriptionEvents.Transcript, chat_response)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        options = LiveOptions(
            model="nova-2",
            punctuate=True,
            language="en-US",
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            endpointing=True
        )
        await dg_connection.start(options)

        microphone = Microphone(dg_connection.send)
        microphone.start()

        silence_duration = 0
        silence_threshold = 20

        while silence_duration < silence_threshold:
            silence_duration += 1   
            await asyncio.sleep(1)

        await shutdown(dg_connection, microphone)

    except Exception as e:
        print(f"Could not open socket: {e}")
    except KeyboardInterrupt:
        print(f"Keyboard force quit.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(get_transcript())
    except Exception as e:
        print(f"Error: {e}")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

