import asyncio
import os
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
    await microphone.finish()
    await dg_connection.finish()
    print("Shutdown complete.")

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

async def get_transcript():
    transcription_complete = transcript_collector.transcription_complete
    try:
        config = DeepgramClientOptions(options={"keepalive": "true"})
        deepgram: DeepgramClient = DeepgramClient(DEEPGRAM_API_KEY, config)

        # dg_connection = deepgram.listen.asyncwebsocket.v("1")
        dg_connection = deepgram.listen.asynclive.v("1")
        print ("Listening...")

        async def on_message(self, result, **kwargs):
            sentence = result.channel.alternatives[0].transcript

            print (result)
            
            if not result.speech_final:
                transcript_collector.add_part(sentence)
            else:
                # This is the final part of the current sentence
                transcript_collector.add_part(sentence)
                full_sentence = transcript_collector.get_full_transcript()
                print(f"speaker: {full_sentence}")
                # Reset the collector for the next sentence
                transcript_collector.reset()

        async def on_error(self, error, **kwargs):
            print(f"\n\n{error}\n\n")

        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
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
        silence_threshold = 10

        while silence_duration < silence_threshold:
            if transcript_collector.transcription_complete:
                transcription_complete.clear()
                silence_duration += 1
                full_transcript = transcript_collector.get_full_transcript()
                transcript_collector.reset()
                print(f"Final Transcript to send to Groq: {full_transcript}")
                shutdown_keywords = ["bye", "goodbye"]

                # Process the full transcript
                content = full_transcript
                print(f"content {content}")

                await process_with_groq(content)
                
                if any(keyword in content.lower() for keyword in shutdown_keywords):
                    print("Shutdown keyword detected. Exiting...")
                    break

            await asyncio.sleep(1)

        await shutdown(dg_connection, microphone)

    except Exception as e:
        print(f"Could not open socket: {e}")



if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(get_transcript())
    except Exception as e:
        print(f"Error: {e}")
    finally:
        loop.close()

