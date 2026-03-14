from __future__ import annotations
import os
import json
import time
from queue import Queue
from threading import Thread, Lock
from gtts import gTTS
import pyttsx3
import asyncio
import hashlib
import edge_tts
from pydub import AudioSegment
from pydub.generators import Sine
import numpy as np

from core.utils.network.network import check_internet
from core.utils.os_utils import getOS
from core.utils.pygame_utils import pygame
from core.utils.files import get_script_path, get_absolute_path, makeDir, joinPaths, file_exists, deleteFile, \
    listFilesInDir, \
    splitExtension
from core.utils.logging_utils import Logger

# Initialize logger
logger = Logger('Sound')
logger.setLevel('INFO')

active_sound_system: SoundSystem | None = None

_beep_cache_files = {}


def beep(
        frequency: int = 440,
        time_ms: int = 250,
        repeats: int = 1,
        volume: float = 1.0,
        force: bool = False,
        flush: bool = False,
):
    """
    Non-blocking beep tone played through the active SoundSystem.

    - Reuses cached beep files from previous runs if found.
    - For repeats > 1, generates a single file containing all beeps with small gaps.
    - `force` and `flush` are forwarded to SoundSystem.play().
    """
    global active_sound_system

    if active_sound_system is None:
        logger.warning("No active sound system for beep()")
        return

    # Clamp parameters
    volume = max(0.0, min(1.0, float(volume)))  # pygame expects 0..1
    repeats = max(1, int(repeats))
    gap_ms = max(0, int(time_ms))

    # Cache key must include repeats + gap for multi-beep variants
    key = (int(frequency), int(time_ms), int(repeats), int(gap_ms))

    # Path where beep files are stored
    sound_path = get_absolute_path(
        f"./sounds/beep_{frequency}_{time_ms}_{repeats}_{gap_ms}.wav"
    )

    # Check in-memory cache first
    if key in _beep_cache_files:
        sound_file = _beep_cache_files[key]

    # If not in memory, check if file already exists from a previous run
    elif file_exists(sound_path):
        _beep_cache_files[key] = sound_path
        sound_file = sound_path

    else:
        # === Generate the base single-beep segment ===
        sample_rate = 44100
        duration_sec = time_ms / 1000.0
        n_samples = int(sample_rate * duration_sec)

        t = np.linspace(0, duration_sec, n_samples, endpoint=False)
        waveform = np.sin(2 * np.pi * frequency * t)

        max_int16 = np.iinfo(np.int16).max

        # Add headroom so we can boost without nasty clipping:
        # 0.3 * max_int16 (~ -10 dB) + apply_gain(+10 dB) ≈ full scale
        headroom_factor = 0.3
        samples = (waveform * max_int16 * headroom_factor).astype(np.int16)

        # Stereo (pygame mixer.music typically handles stereo files fine)
        stereo = np.column_stack((samples, samples))

        # Create AudioSegment
        base_beep = AudioSegment(
            stereo.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=2,
        )

        # Make it "loud" without starting already at clipping
        base_beep = base_beep.apply_gain(10)  # +10 dB

        # === Build full segment with repeats + gaps ===
        if repeats == 1:
            full_segment = base_beep
        else:
            gap = AudioSegment.silent(duration=gap_ms)
            segments = []
            for i in range(repeats):
                segments.append(base_beep)
                if i < repeats - 1 and gap_ms > 0:
                    segments.append(gap)
            full_segment = sum(segments)

        # Export once and reuse forever
        full_segment.export(sound_path, format="wav")

        _beep_cache_files[key] = sound_path
        sound_file = sound_path

    # Queue non-blocking playback (single file that already includes repeats)
    active_sound_system.play(sound_file, volume=volume, force=force, flush=flush)


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
    """
    Plays a sound file if it exists. Playback is non-blocking.

    :param file: Path or name of the sound file.
    """
    if file_exists(file):
        file_path = file
    elif file_exists(get_absolute_path(f'library/{file}.wav')):
        file_path = get_absolute_path(f'library/{file}.wav')
    else:
        return

    try:
        pygame.mixer.Sound(file_path).play()
    except Exception as e:
        print(f"Error playing sound '{file}': {e}")


def apply_robot_filter(input_file, output_file):
    """
    Applies a robotic voice filter to an input audio file and saves the output.

    Parameters:
        input_file (str): Path to the input audio file.
        output_file (str): Path to save the output audio file.
    """
    # Load the audio file
    audio = AudioSegment.from_file(input_file)

    # Apply a high-pass filter to emphasize higher frequencies
    high_pass_filtered = audio.high_pass_filter(1000)

    # Modulate the audio with a sine wave (robotic vibration effect)
    sine_wave = Sine(120).to_audio_segment(duration=len(audio) - 3).apply_gain(-10)  # 120 Hz modulation, reduced volume
    modulated_audio = high_pass_filtered.overlay(sine_wave, loop=True)

    # Add ring modulation for a more robotic sound
    audio_samples = np.array(audio.get_array_of_samples())
    sample_rate = audio.frame_rate
    time_array = np.arange(len(audio_samples)) / sample_rate
    ring_mod_frequency = 100  # Frequency for the ring modulator in Hz
    ring_mod_wave = np.sin(2 * np.pi * ring_mod_frequency * time_array)
    ring_modulated_samples = (audio_samples * ring_mod_wave).astype(audio_samples.dtype)

    # Create an AudioSegment from the ring-modulated samples
    ring_modulated_audio = AudioSegment(
        ring_modulated_samples.tobytes(),
        frame_rate=audio.frame_rate,
        sample_width=audio.sample_width,
        channels=audio.channels
    )

    # Combine the modulated audio with the ring-modulated audio
    combined_audio = modulated_audio.overlay(ring_modulated_audio)

    # Add distortion for a mechanical effect
    distorted_audio = combined_audio + 5  # Increase gain slightly

    # Save the processed audio to the output file
    distorted_audio.export(output_file, format="mp3")


class VoiceEngine:
    """
    Base class for Voice Engines. Must be subclassed to provide specific TTS functionality.
    """
    offline: bool

    def generate(self, text, file_path):
        """
        Generate a TTS file from the provided text.

        :param text: Text to convert to speech.
        :param file_path: File path to save the generated audio.
        """
        raise NotImplementedError("Subclasses must implement 'generate' method")


class GTTSVoiceEngine(VoiceEngine):
    """
    Google Text-to-Speech (gTTS) voice engine implementation.
    """
    offline = False

    def generate(self, text, file_path):
        tts = gTTS(text=text, lang="en")
        tts.save(file_path)


# Voice presets for easy selection by name
VOICE_PRESETS = {
    'male': {'voice': 'en-GB-RyanNeural', 'robot_filter': False},
    'female': {'voice': 'en-GB-LibbyNeural', 'robot_filter': False},
    'robot_male': {'voice': 'en-GB-RyanNeural', 'robot_filter': True},
    'robot_female': {'voice': 'en-GB-LibbyNeural', 'robot_filter': True},
    'robot': {'voice': 'en-GB-RyanNeural', 'robot_filter': True},
}


class EdgeTTSVoiceEngine(VoiceEngine):
    """
Edge TTS voice engine implementation using edge-tts library.

Available voices:
- English (United Kingdom):
  - Female: en-GB-LibbyNeural
  - Male: en-GB-RyanNeural
  - Neutral: en-GB-SoniaNeural

- English (United States):
  - Female: en-US-JennyNeural
  - Male: en-US-GuyNeural
  - Neutral: en-US-AriaNeural

- German:
  - Female: de-DE-KatjaNeural
  - Male: de-DE-ConradNeural
  - Neutral: de-DE-AmalaNeural

- Spanish (Spain):
  - Female: es-ES-ElviraNeural
  - Male: es-ES-AlvaroNeural
  - Neutral: es-ES-DarioNeural

- Spanish (Mexico):
  - Female: es-MX-LuciaNeural
  - Male: es-MX-JorgeNeural
  - Neutral: es-MX-CarlosNeural
"""
    offline = False

    def __init__(self, voice="en-GB-RyanNeural"):
        self.voice = voice

    async def _generate_async(self, text, file_path):
        """
        Asynchronous generation of TTS audio file.

        :param text: Text to convert to speech.
        :param file_path: File path to save the generated audio.
        """
        communicate = edge_tts.Communicate(text, voice=self.voice)
        await communicate.save(file_path)

    def generate(self, text, file_path):
        asyncio.run(self._generate_async(text, file_path))


if getOS() == "Windows":
    class Pyttsx3VoiceEngine(VoiceEngine):
        """
        pyttsx3 voice engine implementation for offline TTS on Windows.
        """
        offline = True

        def __init__(self):
            self.engine = pyttsx3.init()

        def generate(self, text, file_path):
            self.engine.save_to_file(text, file_path)
            self.engine.runAndWait()


def cleanTTS():
    """
    Clean the TTS folder by deleting all files and resetting the index.json.
    """

    try:
        for file in listFilesInDir(get_absolute_path('tts_files')):
            file_path = joinPaths(get_absolute_path('tts_files'), file)
            if file_exists(file_path):
                deleteFile(file_path)

        # Reset the index.json structure
        with open(get_absolute_path('./tts_files/index.json'), "w") as f:
            json.dump({}, f)

        logger.info("TTS files cleared.")
    except Exception as e:
        logger.error(f"Error while cleaning TTS folder: {e}")


class SoundSystem:
    """
    SoundSystem class for managing audio playback and text-to-speech (TTS).
    """

    def __init__(self, volume=0.5, primary_engine=None, fallback_engine=None, add_robot_filter: bool = False):
        """
        Initialize the SoundSystem with volume and TTS engines.

        :param volume: Default volume level.
        :param primary_engine: Primary TTS engine.
        :param fallback_engine: Fallback TTS engine for offline usage.
        """
        pygame.mixer.music.set_volume(volume)
        self.default_volume = volume
        self.volume = volume
        self.queue = Queue()
        self.lock = Lock()
        self.running = False
        self.add_robot_filter = add_robot_filter
        self.thread = Thread(target=self._playback_thread, daemon=True)

        # Ensure all paths are relative to the script's location
        self.script_dir = get_script_path()

        # Prepare directories for TTS and sound files
        self.tts_folder = get_absolute_path('./tts_files')
        makeDir(self.tts_folder)

        self.sound_folder = get_absolute_path('./sounds')
        makeDir(self.sound_folder)

        # Index file to store mapping of text to generated TTS files
        self.index_file = joinPaths(self.tts_folder, "index.json")
        if not file_exists(self.index_file):
            with open(self.index_file, "w") as f:
                json.dump({}, f)

        if primary_engine is None:
            primary_engine = GTTSVoiceEngine()
        elif isinstance(primary_engine, str) and primary_engine == 'gtts':
            primary_engine = GTTSVoiceEngine()
        elif isinstance(primary_engine, str) and primary_engine == 'etts':
            primary_engine = EdgeTTSVoiceEngine()

        self.primary_engine = primary_engine
        self.fallback_engine = fallback_engine

        # Check for internet connectivity
        self.has_internet = check_internet()

    def speak(self, text, volume=None, force=False, flush=False):
        """
        Speak a given text using TTS.

        :param text: Text to speak.
        :param force: Whether to interrupt current playback.
        :param volume: Volume level for playback.
        :param flush: Whether to clear the playback queue.
        """
        try:
            filename = self._get_or_generate_tts_file(text)
        except Exception as e:
            logger.error(f"Error during TTS generation: {e}")
            return
        if filename is None:
            return
        if force:
            self._interrupt_and_play(filename, volume, flush)
        else:
            self.queue.put((filename, volume))

    def play(self, file, volume=None, force=False, flush=False):
        """
        Play a given sound file.

        :param file: Path or name of the sound file.
        :param force: Whether to interrupt current playback.
        :param volume: Volume level for playback.
        :param flush: Whether to clear the playback queue.
        """
        file_path = self._resolve_file_path(file)
        if not file_path:
            logger.error(f"Error: File '{file}' not found.")
            return
        if force:
            self._interrupt_and_play(file_path, volume, flush)
        else:
            self.queue.put((file_path, volume))

    def start(self):
        """
        Start the playback thread.
        """
        self.running = True
        if not self.thread.is_alive():
            self.thread = Thread(target=self._playback_thread, daemon=True)
            self.thread.start()
        self.play('empty')

        global active_sound_system
        if active_sound_system is not None:
            logger.warning("Overriding active sound system")
        active_sound_system = self

    def close(self):
        """
        Stop the playback thread and clean up.
        """
        self.running = False
        if self.thread.is_alive():
            self.thread.join()

    def _playback_thread(self):
        """
        Thread responsible for handling audio playback from the queue.
        """
        while self.running:
            try:
                file, volume = None, None
                if not self.queue.empty():
                    file, volume = self.queue.get()

                if file:
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
            except Exception as e:
                logger.error(f"Error in playback thread: {e}")
            time.sleep(0.1)

    def _interrupt_and_play(self, file, volume=None, flush=False):
        """
        Interrupt current playback and play the given file.

        :param file: File to play.
        :param volume: Volume level for playback.
        :param flush: Whether to clear the playback queue.
        """
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        temp_queue = []
        while not self.queue.empty():
            temp_queue.append(self.queue.get())

        self.queue.put((file, volume))

        if not flush:
            for item in temp_queue:
                self.queue.put(item)

    def _get_or_generate_tts_file(self, text):
        """
        Generate or retrieve a TTS file for the given text.

        :param text: Text to convert to speech.
        :return: Path to the generated TTS file or None if generation failed.
        """
        engine_name = self.primary_engine.__class__.__name__ if self.primary_engine else "None"
        hash_value = hashlib.sha256(text.encode()).hexdigest()

        with open(self.index_file, "r") as f:
            index = json.load(f)

        if text not in index:
            index[text] = {}

        if engine_name in index[text]:
            file_path = index[text][engine_name]
            if file_exists(file_path):
                logger.debug(f"Found file for \"{text}\" using engine \"{engine_name}\"")
                return file_path
            else:
                del index[text][engine_name]

        file_path = joinPaths(self.tts_folder, f"{hash_value}_{engine_name}.mp3")
        logger.debug(f"Attempting to generate new file for \"{text}\" using engine \"{engine_name}\"")

        try:
            if self.has_internet and self.primary_engine:
                self.primary_engine.generate(text, file_path)
                if self.add_robot_filter:
                    apply_robot_filter(file_path, file_path)
            elif self.fallback_engine:
                self.fallback_engine.generate(text, file_path)
            else:
                logger.error(f"No TTS engine available for text: \"{text}\"")
                return None

            index[text][engine_name] = file_path
            with open(self.index_file, "w") as f:
                json.dump(index, f)

            logger.debug(f"Generated file for \"{text}\" using engine \"{engine_name}\"")
            return file_path
        except Exception as e:
            logger.warning(f"Primary TTS engine failed: {e}")
            # Try fallback engine if primary fails (e.g., edge-tts 403 errors)
            return self._try_fallback_tts(text, hash_value, index)

    def _try_fallback_tts(self, text, hash_value, index):
        """
        Attempt TTS generation with fallback engine or gTTS.
        """
        fallback = self.fallback_engine or GTTSVoiceEngine()
        fallback_name = fallback.__class__.__name__

        # Check if we already have a cached file from this fallback
        if fallback_name in index.get(text, {}):
            file_path = index[text][fallback_name]
            if file_exists(file_path):
                logger.debug(f"Found cached fallback file for \"{text}\"")
                return file_path

        file_path = joinPaths(self.tts_folder, f"{hash_value}_{fallback_name}.mp3")
        logger.info(f"Trying fallback TTS engine: {fallback_name}")

        try:
            fallback.generate(text, file_path)
            if self.add_robot_filter:
                apply_robot_filter(file_path, file_path)

            if text not in index:
                index[text] = {}
            index[text][fallback_name] = file_path
            with open(self.index_file, "w") as f:
                json.dump(index, f)

            logger.debug(f"Generated file using fallback engine \"{fallback_name}\"")
            return file_path
        except Exception as e:
            logger.error(f"Fallback TTS engine also failed: {e}")
            return None

    def _resolve_file_path(self, file):
        """
        Resolve the file path from different locations and extensions.

        :param file: File name or path to resolve.
        :return: Resolved file path or None if not found.
        """
        if file_exists(file):
            return file

        file_path = joinPaths(self.script_dir, file)
        if file_exists(file_path):
            return file_path

        file_in_sounds = joinPaths(self.sound_folder, file)
        if file_exists(file_in_sounds):
            return file_in_sounds

        file_base, _ = splitExtension(file)
        for ext in ['.wav', '.mp3', '.ogg']:
            file_with_ext = file_base + ext
            file_in_sounds = joinPaths(self.sound_folder, file_with_ext)
            if file_exists(file_in_sounds):
                return file_in_sounds

        return None


if __name__ == "__main__":
    # Example usage
    # primary_engine = GTTSVoiceEngine()
    primary_engine = EdgeTTSVoiceEngine()
    sound_system = SoundSystem(volume=0.5, primary_engine=primary_engine, add_robot_filter=False)
    # cleanTTS()
    sound_system.start()
    try:
        beep(frequency=1000, volume=2, repeats=3)
        # playSound('warning')
        # speak("BILBO 1 disconnected")
        # # speak("Experiment with ID f-e-x-1-2-3-4 finished")
        # # playSound('startup')¥
        time.sleep(10)
    finally:
        sound_system.close()
