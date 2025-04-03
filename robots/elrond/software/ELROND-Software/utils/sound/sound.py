import json
import time
import asyncio
import hashlib
import threading
from queue import Empty

from gtts import gTTS
import pyttsx3
import edge_tts
from pydub import AudioSegment
from pydub.generators import Sine
import numpy as np

from utils.network import check_internet
from utils.os_utils import getOS
from utils.pygame_utils import pygame
from utils.files import get_script_path, relativeToFullPath, makeDir, joinPaths, fileExists, deleteFile, listFilesInDir, splitExtension
from utils.logging_utils import Logger

# Initialize logger
logger = Logger('Sound')
logger.setLevel('DEBUG')

active_sound_system = None

def speak(text, volume=None, force=False, flush=False):
    if active_sound_system is not None:
        active_sound_system.speak(text, volume, force, flush)
    else:
        logger.warning("No active sound system")


def playSound(file, volume=None, force=False, flush=False):
    if active_sound_system is not None:
        active_sound_system.play(file, volume, force, flush)
    else:
        logger.warning("No active sound system")


def playFile(file):
    if fileExists(file):
        file_path = file
    elif fileExists(relativeToFullPath(f'library/{file}.wav')):
        file_path = relativeToFullPath(f'library/{file}.wav')
    else:
        return

    try:
        pygame.mixer.Sound(file_path).play()
    except Exception as e:
        logger.error(f"Error playing sound '{file}': {e}")


def apply_robot_filter(input_file, output_file):
    audio = AudioSegment.from_file(input_file)
    high_pass_filtered = audio.high_pass_filter(2000)
    sine_wave = Sine(60).to_audio_segment(duration=len(audio) - 3).apply_gain(-25)
    modulated_audio = high_pass_filtered.overlay(sine_wave, loop=True)

    audio_samples = np.array(audio.get_array_of_samples())
    sample_rate = audio.frame_rate
    time_array = np.arange(len(audio_samples)) / sample_rate
    ring_mod_frequency = 100
    ring_mod_wave = np.sin(2 * np.pi * ring_mod_frequency * time_array)
    ring_modulated_samples = (audio_samples * ring_mod_wave).astype(audio_samples.dtype)
    ring_modulated_audio = AudioSegment(
        ring_modulated_samples.tobytes(),
        frame_rate=audio.frame_rate,
        sample_width=audio.sample_width,
        channels=audio.channels
    )
    combined_audio = modulated_audio.overlay(ring_modulated_audio)
    distorted_audio = combined_audio + 10
    distorted_audio.export(output_file, format="mp3")


# === TTS Engines ===

class VoiceEngine:
    offline: bool

    def generate(self, text, file_path):
        raise NotImplementedError("Subclasses must implement 'generate' method")


class GTTSVoiceEngine(VoiceEngine):
    offline = False

    def generate(self, text, file_path):
        tts = gTTS(text=text, lang="en")
        tts.save(file_path)


class EdgeTTSVoiceEngine(VoiceEngine):
    offline = False

    def __init__(self, voice="de-DE-KatjaNeural"):
        self.voice = voice

    async def _generate_async(self, text, file_path):
        communicate = edge_tts.Communicate(text, voice=self.voice)
        await communicate.save(file_path)

    def generate(self, text, file_path):
        # Synchronous wrapper: if you call generate, run the async version
        asyncio.run(self._generate_async(text, file_path))


if getOS() == "Windows":
    class Pyttsx3VoiceEngine(VoiceEngine):
        offline = True

        def __init__(self):
            self.engine = pyttsx3.init()

        def generate(self, text, file_path):
            self.engine.save_to_file(text, file_path)
            self.engine.runAndWait()


def cleanTTS():
    try:
        for file in listFilesInDir(relativeToFullPath('tts_files')):
            file_path = joinPaths(relativeToFullPath('tts_files'), file)
            if fileExists(file_path):
                deleteFile(file_path)

        with open(relativeToFullPath('./tts_files/index.json'), "w") as f:
            json.dump({}, f)

        logger.info("TTS files cleared.")
    except Exception as e:
        logger.error(f"Error while cleaning TTS folder: {e}")


# === Async SoundSystem ===

class SoundSystem:
    def __init__(self, volume=0.5, primary_engine=None, fallback_engine=None, add_robot_filter: bool = False):

        try:
            pygame.mixer.music.set_volume(volume)
        except Exception as e:
            ...

        self.default_volume = volume
        self.volume = volume

        # Prepare directories
        self.script_dir = get_script_path()
        self.tts_folder = relativeToFullPath('./tts_files')
        makeDir(self.tts_folder)
        self.sound_folder = relativeToFullPath('./sounds')
        makeDir(self.sound_folder)
        self.index_file = joinPaths(self.tts_folder, "index.json")
        if not fileExists(self.index_file):
            with open(self.index_file, "w") as f:
                json.dump({}, f)

        if primary_engine is None:
            primary_engine = GTTSVoiceEngine()
        self.primary_engine = primary_engine
        self.fallback_engine = fallback_engine

        self.has_internet = check_internet()
        self.add_robot_filter = add_robot_filter

        # Create an asyncio queue for playback items
        self.playback_queue = asyncio.Queue()

        # Create an event loop running in a separate thread
        self.loop = asyncio.new_event_loop()
        self.running = True
        self.loop_thread = threading.Thread(target=self._start_loop, daemon=True)

        # Schedule the playback worker
        asyncio.run_coroutine_threadsafe(self._playback_worker(), self.loop)

        global active_sound_system
        if active_sound_system is not None:
            logger.warning("Overriding active sound system")
        active_sound_system = self

    def start(self):
        self.loop_thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def speak(self, text, volume=None, force=False, flush=False):
        # Schedule the asynchronous speak process; return immediately.
        asyncio.run_coroutine_threadsafe(
            self._process_speak(text, volume, force, flush),
            self.loop
        )

    def play(self, file, volume=None, force=False, flush=False):
        # For non-TTS sounds, you could either create a similar async wrapper or run the blocking call in a thread.
        file_path = self._resolve_file_path(file)
        if not file_path:
            logger.error(f"Error: File '{file}' not found.")
            return
        if force:
            asyncio.run_coroutine_threadsafe(self._interrupt_and_enqueue(file_path, volume, flush), self.loop)
        else:
            asyncio.run_coroutine_threadsafe(self.playback_queue.put((file_path, volume)), self.loop)

    def _resolve_file_path(self, file):
        if fileExists(file):
            return file
        file_path = joinPaths(self.script_dir, file)
        if fileExists(file_path):
            return file_path
        file_in_sounds = joinPaths(self.sound_folder, file)
        if fileExists(file_in_sounds):
            return file_in_sounds
        file_base, _ = splitExtension(file)
        for ext in ['.wav', '.mp3', '.ogg']:
            file_with_ext = file_base + ext
            file_in_sounds = joinPaths(self.sound_folder, file_with_ext)
            if fileExists(file_in_sounds):
                return file_in_sounds
        return None

    async def _process_speak(self, text, volume, force, flush):
        file = await self._get_or_generate_tts_file_async(text)
        if file is None:
            return

        if force:
            # Stop current playback and clear queue
            await asyncio.to_thread(pygame.mixer.music.stop)
            self._clear_playback_queue()

        # Enqueue file for playback
        await self.playback_queue.put((file, volume))

    def _clear_playback_queue(self):
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except Empty:
                break

    async def _playback_worker(self):
        while self.running:
            file, volume = await self.playback_queue.get()
            await self._blocking_play(file, volume)

    async def _blocking_play(self, file, volume):
        await asyncio.to_thread(self._play_file, file, volume)

    def _play_file(self, file, volume):
        try:
            if volume is not None:
                pygame.mixer.music.set_volume(volume)
            else:
                pygame.mixer.music.set_volume(self.default_volume)
            pygame.mixer.music.load(file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            pygame.mixer.music.set_volume(self.default_volume)
        except Exception as e:
            logger.error(f"Error during playback of '{file}': {e}")

    async def _get_or_generate_tts_file_async(self, text):
        engine_name = self.primary_engine.__class__.__name__ if self.primary_engine else "None"
        hash_value = hashlib.sha256(text.encode()).hexdigest()

        index = await asyncio.to_thread(self._read_index)
        if text not in index:
            index[text] = {}
        if engine_name in index[text]:
            file_path = index[text][engine_name]
            if await asyncio.to_thread(fileExists, file_path):
                logger.debug(f"Found file for \"{text}\" using engine \"{engine_name}\"")
                return file_path
            else:
                del index[text][engine_name]

        file_path = joinPaths(self.tts_folder, f"{hash_value}_{engine_name}.mp3")
        logger.debug(f"Generating new file for \"{text}\" using engine \"{engine_name}\"")
        try:
            if self.has_internet and self.primary_engine:
                if hasattr(self.primary_engine, '_generate_async'):
                    await self.primary_engine._generate_async(text, file_path)
                else:
                    await asyncio.to_thread(self.primary_engine.generate, text, file_path)
                if self.add_robot_filter:
                    await asyncio.to_thread(apply_robot_filter, file_path, file_path)
            elif self.fallback_engine:
                await asyncio.to_thread(self.fallback_engine.generate, text, file_path)
            else:
                logger.error(f"No TTS engine available for text: \"{text}\"")
                return None

            index[text][engine_name] = file_path
            await asyncio.to_thread(self._write_index, index)
            logger.debug(f"Generated file for \"{text}\" using engine \"{engine_name}\"")
            return file_path
        except Exception as e:
            logger.error(f"Error generating TTS file: {e}")
            return None

    def _read_index(self):
        try:
            with open(self.index_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading index file: {e}")
            return {}

    def _write_index(self, index):
        try:
            with open(self.index_file, "w") as f:
                json.dump(index, f)
        except Exception as e:
            logger.error(f"Error writing index file: {e}")

    async def _interrupt_and_enqueue(self, file, volume, flush):
        await asyncio.to_thread(pygame.mixer.music.stop)
        if flush:
            self._clear_playback_queue()
        await self.playback_queue.put((file, volume))

    def close(self):
        self.running = False
        # Stop playback
        pygame.mixer.music.stop()
        # Stop the event loop safely
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()


if __name__ == "__main__":
    # Example usage:
    # primary_engine = GTTSVoiceEngine()
    primary_engine = EdgeTTSVoiceEngine()
    sound_system = SoundSystem(volume=0.9, primary_engine=primary_engine, add_robot_filter=False)
    cleanTTS()

    # Call speak() without blocking the caller.
    speak("Hello, this is an asynchronous test.", volume=0.8)

    # To allow time for background tasks to run (in a real app your main loop would run indefinitely)
    time.sleep(10)
    sound_system.close()
