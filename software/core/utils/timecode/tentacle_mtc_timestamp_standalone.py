"""
tentacle_mtc_timestamp.py
==========================

Minimal, standalone reader for MIDI Time Code (MTC) coming from a Tentacle Sync
unit connected over USB MIDI.

What this does
--------------
A Tentacle Sync generates SMPTE timecode and can output it as MIDI Time Code
(MTC) over its USB MIDI class-compliant interface. MTC is transmitted as a
continuous stream of "quarter-frame" MIDI messages; every 8 quarter-frames
(= 2 frames of video) form one complete HH:MM:SS:FF timecode value.

This script listens to that MIDI stream, decodes it into timecode values, and
calls a callback function *every time a new full timecode value is decoded*
(i.e. roughly every 2 frames -> ~12-15 times/second depending on fps). Each
callback also receives `time.time()` captured at the moment the value was
decoded, so you can log/pair it directly with whatever data you are recording
on your own machine.

Requirements
------------
    pip install mido python-rtmidi

`mido` is the MIDI library; `python-rtmidi` is the backend it uses to talk to
real MIDI hardware (works on macOS/Linux/Windows).

Hardware setup
--------------
1. Connect the Tentacle Sync to this machine via USB.
2. Make sure the Tentacle is set to output MTC (not just LTC) on its MIDI
   port, and that it is receiving/generating valid timecode (jam-synced or
   free-running).
3. Run this file directly to see a live printout of decoded timecodes:

       python tentacle_mtc_timestamp.py

   If it can't find the device, it will print all available MIDI input port
   names -- check that the Tentacle shows up there (by default this script
   looks for any port whose name contains "tentacle", case-insensitive).

Usage as a library
------------------
    from tentacle_mtc_timestamp import TentacleMTCReader

    def on_timecode(timecode_str, seconds, wall_time):
        # timecode_str: "HH:MM:SS:FF" (or "HH:MM:SS;FF" for drop-frame)
        # seconds:      timecode value converted to seconds (float)
        # wall_time:    time.time() when this value was decoded -- use this
        #               to align with your own recorded data.
        my_data_row["tentacle_timecode"] = timecode_str
        my_data_row["tentacle_wall_time"] = wall_time

    reader = TentacleMTCReader()
    reader.add_callback(on_timecode)
    reader.start()          # blocks briefly until synced, then runs in background

    ...                      # do your own recording here

    reader.stop()

Notes
-----
- `offset_frames` (default 2) compensates for the fact that a full MTC value
  is only known once its *last* quarter-frame has arrived, ~2 frames after
  the timecode instant it actually describes. This is standard MTC decoder
  practice and matches what most NLE/DAW software does.
- fps is auto-detected from the MTC stream (24, 25, 29.97 drop-frame, or 30).
- This is a trimmed-down extract of a larger internal framework
  (core/utils/timecode/mtc.py in the BilboLab project) with all
  project-specific dependencies removed -- it only depends on `mido`.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import mido

# ======================================================================================================================
# Timecode value object
# ======================================================================================================================

RATE_CODE_TO_FPS = {
    0: 24.0,
    1: 25.0,
    2: 29.97,  # drop-frame
    3: 30.0,
}


@dataclasses.dataclass
class Timecode:
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0
    fps: float = 25.0
    df: bool = False

    def to_seconds(self) -> float:
        nominal_fps = int(round(self.fps))
        total_frames = (
            ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * nominal_fps
            + self.frames
        )
        return total_frames / self.fps

    def offset_frames(self, frame_offset: int) -> "Timecode":
        nominal_fps = int(round(self.fps))
        total_frames = (
            ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * nominal_fps
            + self.frames
        )
        total_frames = max(0, total_frames + frame_offset)

        total_seconds, frames = divmod(total_frames, nominal_fps)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        return Timecode(
            hours=int(hours), minutes=int(minutes), seconds=int(seconds),
            frames=int(frames), fps=self.fps, df=self.df,
        )

    def to_string(self) -> str:
        sep = ";" if self.df else ":"
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{sep}{self.frames:02d}"

    def __repr__(self) -> str:
        return f"Timecode('{self.to_string()}', fps={self.fps})"


# ======================================================================================================================
# MTC reader
# ======================================================================================================================

class TentacleMTCReader:
    """
    Reads MIDI Time Code from a Tentacle Sync (or any MTC source) connected
    via USB MIDI, and fires a callback for every decoded timecode value.
    """

    def __init__(
        self,
        port_match: str = "tentacle",
        fps: float | None = None,
        drop_frame: bool = False,
        offset_frames: int = 2,
    ):
        """
        port_match:     substring (case-insensitive) to look for in MIDI input
                        port names to auto-select the Tentacle. Ignored if you
                        pass an explicit port_name to start().
        fps:            force a frame rate instead of auto-detecting it from
                        the MTC stream. Leave as None to auto-detect.
        drop_frame:     whether to format timecodes as drop-frame (29.97 fps).
        offset_frames:  see module docstring.
        """
        self.port_match = port_match
        self.fps = fps
        self.drop_frame = drop_frame
        self.offset_frames = offset_frames

        self._callbacks: list = []
        self._current = _RawTimecode()
        self._seen_mask = 0
        self._synced = False
        self._rate_code: int | None = None

        self._timecode: Timecode | None = None
        self._lock = threading.Lock()

        self._port_name: str | None = None
        self._inport: mido.ports.BaseInput | None = None
        self._thread: threading.Thread | None = None
        self._exit = False
        self._ready = threading.Event()

    # === PUBLIC API ===================================================================================================

    def add_callback(self, fn) -> None:
        """
        Register a function called every time a new timecode is decoded:
            fn(timecode_str: str, seconds: float, wall_time: float) -> None
        Exceptions raised inside fn are caught and printed so one bad
        callback can't kill the reader thread.
        """
        self._callbacks.append(fn)

    def remove_callback(self, fn) -> None:
        if fn in self._callbacks:
            self._callbacks.remove(fn)

    @staticmethod
    def list_ports() -> list[str]:
        return mido.get_input_names()  # type: ignore

    def find_port(self) -> str | None:
        for name in self.list_ports():
            if self.port_match.lower() in name.lower():
                return name
        return None

    def start(self, port_name: str | None = None, sync_timeout: float = 5.0) -> bool:
        """
        Find the MIDI port, start the background decoding thread, and block
        until either the first timecode is decoded or `sync_timeout` seconds
        have passed. Returns True on success, False if no port was found or
        it timed out.
        """
        self._port_name = port_name or self.find_port()

        if self._port_name is None:
            print(f"[TentacleMTCReader] No MIDI input matching '{self.port_match}' found.")
            print(f"[TentacleMTCReader] Available MIDI inputs: {self.list_ports()}")
            return False

        print(f"[TentacleMTCReader] Using MIDI input: {self._port_name}")

        self._exit = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        synced = self._ready.wait(timeout=sync_timeout)
        if not synced:
            print("[TentacleMTCReader] Timed out waiting for MTC sync. "
                  "Is the Tentacle powered, jammed, and outputting MTC?")
        return synced

    def stop(self) -> None:
        self._exit = True
        if self._inport is not None:
            try:
                self._inport.close()
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_timecode(self) -> Timecode | None:
        with self._lock:
            return self._timecode

    def get_seconds(self) -> float | None:
        tc = self.get_timecode()
        return tc.to_seconds() if tc is not None else None

    # === INTERNAL ======================================================================================================

    def _run(self) -> None:
        try:
            inport = mido.open_input(self._port_name)  # type: ignore
            self._inport = inport

            while not self._exit:
                had_message = False
                for msg in inport.iter_pending():
                    had_message = True
                    tc = self._feed(msg)
                    if tc is not None:
                        self._on_full_timecode(tc)

                if not had_message:
                    time.sleep(0.001)

        except Exception as exc:
            print(f"[TentacleMTCReader] Error reading MIDI: {exc}")
        finally:
            if self._inport is not None:
                try:
                    self._inport.close()
                except Exception:
                    pass
                self._inport = None

    def _feed(self, msg) -> Timecode | None:
        if msg.type != "quarter_frame":
            return None

        raw_bytes = msg.bytes()
        if len(raw_bytes) < 2:
            return None

        data = raw_bytes[1] & 0x7F
        msg_type = (data >> 4) & 0x07
        nibble = data & 0x0F

        self._seen_mask |= (1 << msg_type)
        cur = self._current

        if msg_type == 0:
            cur.frames = (cur.frames & 0xF0) | nibble
        elif msg_type == 1:
            cur.frames = (cur.frames & 0x0F) | (nibble << 4)
        elif msg_type == 2:
            cur.seconds = (cur.seconds & 0xF0) | nibble
        elif msg_type == 3:
            cur.seconds = (cur.seconds & 0x0F) | (nibble << 4)
        elif msg_type == 4:
            cur.minutes = (cur.minutes & 0xF0) | nibble
        elif msg_type == 5:
            cur.minutes = (cur.minutes & 0x0F) | (nibble << 4)
        elif msg_type == 6:
            cur.hours = (cur.hours & 0xF0) | nibble
        elif msg_type == 7:
            cur.hours = (cur.hours & 0x1F) | ((nibble & 0x01) << 4)
            self._rate_code = (nibble >> 1) & 0x03

            detected_fps = RATE_CODE_TO_FPS.get(self._rate_code)
            if detected_fps is not None and self.fps is None:
                self.fps = detected_fps
                print(f"[TentacleMTCReader] Detected MTC frame rate: {detected_fps} fps")

            if self._seen_mask == 0xFF:  # full 8-message cycle received
                self._seen_mask = 0

                if not self._synced:
                    # First cycle may be a partial/contaminated read -- skip it.
                    self._synced = True
                    return None

                if self.fps is None:
                    return None

                return Timecode(
                    hours=cur.hours, minutes=cur.minutes, seconds=cur.seconds,
                    frames=cur.frames, fps=self.fps, df=self.drop_frame,
                )

        return None

    def _on_full_timecode(self, tc_raw: Timecode) -> None:
        tc = tc_raw.offset_frames(self.offset_frames)
        wall_time = time.time()

        with self._lock:
            self._timecode = tc

        if not self._ready.is_set():
            self._ready.set()

        for fn in list(self._callbacks):
            try:
                fn(tc.to_string(), tc.to_seconds(), wall_time)
            except Exception as exc:
                print(f"[TentacleMTCReader] Callback error: {exc}")


@dataclasses.dataclass
class _RawTimecode:
    frames: int = 0
    seconds: int = 0
    minutes: int = 0
    hours: int = 0


# ======================================================================================================================
# Minimum working example: print every decoded timestamp
# ======================================================================================================================

if __name__ == "__main__":

    def print_timecode(timecode_str: str, seconds: float, wall_time: float) -> None:
        print(f"TC={timecode_str}  seconds={seconds:.3f}  wall_time={wall_time:.3f}")

    reader = TentacleMTCReader()
    reader.add_callback(print_timecode)

    if not reader.start():
        raise SystemExit(1)

    print("Reading timecodes from Tentacle Sync. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        reader.stop()
