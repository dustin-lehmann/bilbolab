import json
import math
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass, field


@dataclass
class VideoStreamInfo:
    codec: str = ''
    codec_long: str = ''
    width: int = 0
    height: int = 0
    display_width: int | None = None
    display_height: int | None = None
    sar: str = ''
    dar: str = ''
    fps: float = 0.0
    bitrate: int | None = None  # bits per second
    bit_depth: int | None = None
    pix_fmt: str = ''
    color_space: str = ''
    color_transfer: str = ''
    color_primaries: str = ''
    profile: str = ''
    level: str = ''
    field_order: str = ''


@dataclass
class AudioStreamInfo:
    codec: str = ''
    codec_long: str = ''
    sample_rate: int = 0
    channels: int = 0
    channel_layout: str = ''
    bitrate: int | None = None  # bits per second
    bit_depth: int | None = None


@dataclass
class VideoInfo:
    file_path: str = ''
    file_size: int = 0  # bytes
    format: str = ''
    format_long: str = ''
    duration: float = 0.0  # seconds
    bitrate: int = 0  # bits per second
    timecode: str | None = None
    creation_time: str | None = None
    video: VideoStreamInfo = field(default_factory=VideoStreamInfo)
    audio: AudioStreamInfo | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def file_size_mb(self) -> float:
        return self.file_size / (1024 * 1024)

    @property
    def file_size_gb(self) -> float:
        return self.file_size / (1024 * 1024 * 1024)

    @property
    def bitrate_mbps(self) -> float:
        return self.bitrate / 1_000_000

    def __str__(self) -> str:
        lines = [
            f"File:       {os.path.basename(self.file_path)}",
            f"Size:       {self.file_size_mb:.1f} MB ({self.file_size_gb:.2f} GB)",
            f"Format:     {self.format_long}",
            f"Duration:   {_format_duration(self.duration)}",
            f"Bitrate:    {self.bitrate_mbps:.1f} Mbit/s",
        ]
        if self.timecode:
            lines.append(f"Timecode:   {self.timecode}")
        if self.creation_time:
            lines.append(f"Created:    {self.creation_time}")

        v = self.video
        lines.append("")
        lines.append("Video:")
        res = f"  {v.width}x{v.height}"
        if v.display_width and v.display_height and (v.display_width != v.width or v.display_height != v.height):
            res += f" -> {v.display_width}x{v.display_height} (display)"
        lines.append(f"  Resolution:   {res.strip()}")
        lines.append(f"  Codec:        {v.codec_long} ({v.codec})")
        if v.profile:
            lines.append(f"  Profile:      {v.profile}" + (f" (Level {v.level})" if v.level else ""))
        lines.append(f"  Pixel format: {v.pix_fmt}" + (f" ({v.bit_depth}-bit)" if v.bit_depth else ""))
        lines.append(f"  Frame rate:   {v.fps:.3f} fps")
        if v.bitrate:
            lines.append(f"  Bitrate:      {v.bitrate / 1_000_000:.1f} Mbit/s")
        if v.sar and v.sar != '1:1':
            lines.append(f"  SAR:          {v.sar}")
        if v.dar:
            lines.append(f"  DAR:          {v.dar}")
        if v.color_space:
            lines.append(f"  Color:        {v.color_space} / {v.color_transfer} / {v.color_primaries}")
        if v.field_order and v.field_order not in ('progressive', 'unknown'):
            lines.append(f"  Interlaced:   {v.field_order}")

        a = self.audio
        if a:
            lines.append("")
            lines.append("Audio:")
            lines.append(f"  Codec:        {a.codec_long} ({a.codec})")
            lines.append(f"  Sample rate:  {a.sample_rate} Hz")
            lines.append(f"  Channels:     {a.channels}" + (f" ({a.channel_layout})" if a.channel_layout else ""))
            if a.bitrate:
                lines.append(f"  Bitrate:      {a.bitrate // 1000} kbit/s")

        if self.metadata:
            lines.append("")
            lines.append("Metadata:")
            for k, v_meta in self.metadata.items():
                lines.append(f"  {k}: {v_meta}")

        return '\n'.join(lines)


def _format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m}:{s:05.2f}"


def analyze_video(input_path: str) -> VideoInfo:
    """Analyze a video file and return detailed information.

    Uses ffprobe to extract codec, resolution, frame rate, bitrate, timecode,
    color info, audio details, and metadata.

    Args:
        input_path: Path to the video file.

    Returns:
        A VideoInfo dataclass with all extracted information. Print it for a
        human-readable summary.

    Raises:
        FileNotFoundError: If the input file or ffprobe is not found.
        subprocess.CalledProcessError: If ffprobe exits with a non-zero status.
    """
    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffprobe') is None:
        raise FileNotFoundError("ffprobe not found. Install ffmpeg to analyze videos.")

    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', input_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)

    fmt = data.get('format', {})
    streams = data.get('streams', [])

    info = VideoInfo(
        file_path=input_path,
        file_size=int(fmt.get('size', 0)),
        format=fmt.get('format_name', ''),
        format_long=fmt.get('format_long_name', ''),
        duration=float(fmt.get('duration', 0)),
        bitrate=int(fmt.get('bit_rate', 0)),
    )

    # Extract metadata (skip boring keys)
    fmt_tags = fmt.get('tags', {})
    skip_keys = {'compatible_brands', 'minor_version', 'major_brand', 'encoder'}
    for k, v in fmt_tags.items():
        if k.lower() == 'timecode':
            info.timecode = v
        elif k.lower() == 'creation_time':
            info.creation_time = v
        elif k.lower() not in skip_keys:
            info.metadata[k] = v

    # Find video and audio streams
    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

    # Also check data streams for timecode
    if not info.timecode:
        for s in streams:
            if s.get('codec_type') == 'data' or s.get('codec_tag_string') == 'tmcd':
                tc = s.get('tags', {}).get('timecode')
                if tc:
                    info.timecode = tc
                    break

    if video_stream:
        vs = video_stream
        v = info.video
        v.codec = vs.get('codec_name', '')
        v.codec_long = vs.get('codec_long_name', '')
        v.width = int(vs.get('width', 0))
        v.height = int(vs.get('height', 0))
        v.pix_fmt = vs.get('pix_fmt', '')
        v.profile = vs.get('profile', '')
        v.level = str(vs.get('level', '')) if vs.get('level') else ''
        v.field_order = vs.get('field_order', '')
        v.color_space = vs.get('color_space', '')
        v.color_transfer = vs.get('color_transfer', '')
        v.color_primaries = vs.get('color_primaries', '')

        # SAR / DAR
        v.sar = vs.get('sample_aspect_ratio', '')
        v.dar = vs.get('display_aspect_ratio', '')
        if v.sar and v.sar != '1:1' and ':' in v.sar:
            sar_num, sar_den = (int(x) for x in v.sar.split(':'))
            if sar_den > 0:
                v.display_width = round(v.width * sar_num / sar_den)
                v.display_height = v.height

        # Frame rate from r_frame_rate (e.g. "24000/1001")
        r_fps = vs.get('r_frame_rate', '')
        if r_fps and '/' in r_fps:
            num, den = r_fps.split('/')
            if int(den) > 0:
                v.fps = int(num) / int(den)

        # Bitrate
        if vs.get('bit_rate'):
            v.bitrate = int(vs['bit_rate'])

        # Bit depth from bits_per_raw_sample
        if vs.get('bits_per_raw_sample'):
            v.bit_depth = int(vs['bits_per_raw_sample'])

    if audio_stream:
        a_s = audio_stream
        a = AudioStreamInfo(
            codec=a_s.get('codec_name', ''),
            codec_long=a_s.get('codec_long_name', ''),
            sample_rate=int(a_s.get('sample_rate', 0)),
            channels=int(a_s.get('channels', 0)),
            channel_layout=a_s.get('channel_layout', ''),
        )
        if a_s.get('bit_rate'):
            a.bitrate = int(a_s['bit_rate'])
        if a_s.get('bits_per_raw_sample'):
            a.bit_depth = int(a_s['bits_per_raw_sample'])
        info.audio = a

    return info


def _run_ffmpeg(cmd: list[str]):
    """Run an ffmpeg command with readable error messages."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else '(no output)'
        raise RuntimeError(
            f"ffmpeg failed (exit {e.returncode}):\n"
            f"  Command: {' '.join(cmd)}\n"
            f"  Error: {stderr}"
        ) from None


def _audio_flags(output_path: str, bitrate: str = '192k') -> list[str]:
    """Choose audio codec flags based on the output container.

    MOV supports PCM audio natively, so we can copy the audio stream.
    MP4 and other containers require transcoding to AAC.
    """
    ext = os.path.splitext(output_path)[1].lower()
    if ext in ('.mov', '.mxf'):
        return ['-c:a', 'copy']
    return ['-c:a', 'aac', '-b:a', bitrate]


def _output_path(input_path: str, suffix: str, ext: str | None = None) -> str:
    """Build an output path, preserving the input extension by default."""
    base, in_ext = os.path.splitext(input_path)
    return f"{base}{suffix}{ext or in_ext}"


def _set_mov_pixel_aspect_ratio(file_path: str, h_spacing: int, v_spacing: int):
    """Modify the pasp (Pixel Aspect Ratio) atom in a MOV/MP4 file.

    Directly overwrites the hSpacing/vSpacing values in the container without
    touching the video bitstream. QuickTime uses pasp to determine display size.

    Args:
        file_path: Path to the MOV/MP4 file to modify in-place.
        h_spacing: Horizontal spacing (numerator of pixel aspect ratio).
        v_spacing: Vertical spacing (denominator of pixel aspect ratio).

    Raises:
        RuntimeError: If no valid pasp atom is found.
    """
    pasp_tag = b'pasp'
    with open(file_path, 'r+b') as f:
        data = f.read()

    # Find all occurrences of 'pasp' and validate each as a real atom
    offset = 0
    found = False
    while True:
        idx = data.find(pasp_tag, offset)
        if idx == -1:
            break
        # The 4 bytes before 'pasp' are the atom size (big-endian uint32)
        if idx >= 4:
            size = struct.unpack('>I', data[idx - 4:idx])[0]
            if size == 16:
                # Valid pasp atom: overwrite hSpacing and vSpacing
                with open(file_path, 'r+b') as f:
                    f.seek(idx + 4)
                    f.write(struct.pack('>II', h_spacing, v_spacing))
                found = True
                break
        offset = idx + 4

    if not found:
        raise RuntimeError(
            f"No pasp atom found in {file_path}. The metadata desqueeze method "
            f"requires a pasp atom in the container. Use method='scale' instead."
        )


def _tc_flags() -> list[str]:
    """Common ffmpeg flags to preserve timecode and metadata."""
    return [
        '-map', '0:v',       # video stream
        '-map', '0:a?',      # audio stream (if present)
        '-map', '0:d?',      # data/timecode stream (if present)
        '-map_metadata', '0',  # copy global metadata
        '-c:d', 'copy',      # pass through data streams unchanged
    ]


def webm_to_mp4(input_path: str, output_path: str | None = None, overwrite: bool = True) -> str:
    """Convert a .webm file to .mp4 using ffmpeg.

    Args:
        input_path: Path to the source .webm file.
        output_path: Path for the output .mp4. If None, replaces the .webm extension.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created .mp4 file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + '.mp4'
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path]
    cmd += _tc_flags()
    cmd += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p', output_path]

    _run_ffmpeg(cmd)

    return output_path


def change_speed(input_path: str, speed: float, output_path: str | None = None, overwrite: bool = True) -> str:
    """Change the playback speed of a video using ffmpeg.

    Args:
        input_path: Path to the source video file.
        speed: Speed multiplier (e.g. 0.5 for half speed, 2.0 for double speed).
        output_path: Path for the output file. If None, appends the speed to the filename
                     (e.g. "video_2.0x.mp4").
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created video file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        ValueError: If speed is not positive.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    if speed <= 0:
        raise ValueError(f"Speed must be positive, got {speed}")

    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        output_path = _output_path(input_path, f'_{speed}x')
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    # Video: setpts divides by speed (faster = smaller PTS values)
    video_filter = f"setpts={1.0 / speed}*PTS"
    # Audio: atempo only accepts values in [0.5, 100.0], so chain multiple filters if needed
    audio_filters = _build_atempo_filter(speed)

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path]
    cmd += _tc_flags()
    cmd += ['-filter:v', video_filter, '-filter:a', audio_filters, output_path]

    _run_ffmpeg(cmd)

    return output_path


def desqueeze_anamorphic(input_path: str, squeeze_factor: float, output_path: str | None = None,
                         method: str = 'metadata', overwrite: bool = True) -> str:
    """Desqueeze video recorded with an anamorphic lens.

    Anamorphic lenses compress the horizontal field of view by a squeeze factor
    (e.g. 1.33x or 1.6x). This function restores the intended aspect ratio.

    Args:
        input_path: Path to the source video file.
        squeeze_factor: The anamorphic squeeze factor (e.g. 1.33, 1.6, 2.0).
            This is the horizontal stretch multiplier to apply.
        output_path: Path for the output file. If None, appends the factor to
            the filename (e.g. "video_desqueezed_1.33x.mp4").
        method: Desqueeze method:
            - 'metadata': Set the pixel aspect ratio (SAR) without re-encoding.
              Truly lossless and instant, but some players may ignore SAR.
            - 'scale': Re-encode with horizontal scaling. Visually lossless
              (CRF 18) but compatible everywhere.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created video file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        ValueError: If squeeze_factor is not greater than 0 or method is invalid.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    if squeeze_factor <= 0:
        raise ValueError(f"Squeeze factor must be positive, got {squeeze_factor}")
    if method not in ('metadata', 'scale'):
        raise ValueError(f"Method must be 'metadata' or 'scale', got '{method}'")

    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        output_path = _output_path(input_path, f'_desqueezed_{squeeze_factor}x')
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    # Probe dimensions for print info
    probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height',
                 '-of', 'csv=p=0:s=x', input_path]
    probe_result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
    width, height = (int(v) for v in probe_result.stdout.strip().split('x'))

    print(f"Desqueezing {os.path.basename(input_path)}")
    print(f"  Source:      {width}x{height}")
    print(f"  Squeeze:     {squeeze_factor}x")
    if method == 'metadata':
        display_w = round(width * squeeze_factor)
        print(f"  Display:     {display_w}x{height} (container metadata, no re-encode)")
    else:
        scaled_w = round(width * squeeze_factor / 2) * 2
        print(f"  Scaled to:   {scaled_w}x{height} (re-encoded)")
    print(f"  Output:      {os.path.basename(output_path)}")

    input_size = os.path.getsize(input_path) / (1024 * 1024)

    if method == 'metadata':
        out_ext = os.path.splitext(output_path)[1].lower()
        if out_ext in ('.mov', '.mxf'):
            # MOV: byte-copy the file and patch the pasp atom directly.
            # ffmpeg's MOV muxer corrupts H.264 High 4:2:2 Intra / 10-bit
            # profiles even with -c copy (green frames), so we bypass
            # ffmpeg entirely for MOV metadata desqueeze.
            if os.path.abspath(input_path) == os.path.abspath(output_path):
                print(f"  In-place metadata update ({input_size:.0f} MB)...")
            else:
                print(f"  Copying {input_size:.0f} MB...")
                shutil.copy2(input_path, output_path)
            h_spacing = round(squeeze_factor * 1000)
            v_spacing = 1000
            _set_mov_pixel_aspect_ratio(output_path, h_spacing, v_spacing)
        else:
            # MP4/others: ffmpeg's -aspect sets container DAR reliably.
            dar = f'{width * squeeze_factor / height}'
            cmd = ['ffmpeg']
            if overwrite:
                cmd.append('-y')
            cmd += ['-i', input_path, '-c', 'copy', '-aspect', dar, output_path]
            _run_ffmpeg(cmd)
    else:
        # Re-encode: scales pixels, works with any container.
        vf = f"scale=trunc(iw*{squeeze_factor}/2)*2:ih"
        cmd = ['ffmpeg']
        if overwrite:
            cmd.append('-y')
        cmd += ['-i', input_path]
        cmd += _tc_flags()
        cmd += ['-vf', vf, '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
                '-pix_fmt', 'yuv420p'] + _audio_flags(output_path) + [output_path]
        _run_ffmpeg(cmd)

    output_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  Done:        {input_size:.1f} MB -> {output_size:.1f} MB")

    return output_path


def crop(input_path: str, top: int | float = 0, bottom: int | float = 0,
         left: int | float = 0, right: int | float = 0,
         output_path: str | None = None, overwrite: bool = True) -> str:
    """Crop a video by removing pixels from each edge.

    Values are interpreted by type:
        - int: absolute pixels (e.g. 100 = 100px)
        - float: fraction of the respective dimension (e.g. 0.23 = 23%)

    You can mix types freely (e.g. top=100, left=0.1).

    Args:
        input_path: Path to the source video file.
        top: Amount to crop from the top edge.
        bottom: Amount to crop from the bottom edge.
        left: Amount to crop from the left edge.
        right: Amount to crop from the right edge.
        output_path: Path for the output file. If None, appends '_cropped' to
            the filename.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created video file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        ValueError: If crop values are negative or floats are >= 1.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    for name, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        if val < 0:
            raise ValueError(f"{name} must be non-negative, got {val}")
        if isinstance(val, float) and val >= 1.0:
            raise ValueError(f"{name} is a float >= 1.0 ({val}). Floats are interpreted as "
                             f"fractions (0.0-1.0). Use an int for pixel values.")

    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        output_path = _output_path(input_path, '_cropped')
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    # Build pixel expressions. Floats become fractions of iw/ih,
    # ints become literal pixel values.
    def _expr(val, dim):
        if isinstance(val, float):
            return f'{dim}*{val}'
        return str(int(val))

    # Probe source dimensions and file size for print output
    probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height',
                 '-show_entries', 'format=size',
                 '-of', 'json', input_path]
    probe_result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
    probe_data = json.loads(probe_result.stdout)
    src_stream = probe_data.get('streams', [{}])[0]
    src_fmt = probe_data.get('format', {})
    src_w = int(src_stream.get('width', 0))
    src_h = int(src_stream.get('height', 0))
    src_size = int(src_fmt.get('size', 0))

    # Resolve pixel crop values for display
    def _resolve(val, dim_px):
        if isinstance(val, float):
            return round(val * dim_px)
        return int(val)

    crop_t = _resolve(top, src_h)
    crop_b = _resolve(bottom, src_h)
    crop_l = _resolve(left, src_w)
    crop_r = _resolve(right, src_w)
    out_w = round((src_w - crop_l - crop_r) / 2) * 2
    out_h = round((src_h - crop_t - crop_b) / 2) * 2

    print(f"Cropping {os.path.basename(input_path)}")
    print(f"  Source:      {src_w}x{src_h}, {src_size / (1024**2):.1f} MB")
    print(f"  Crop:        top={crop_t}px, bottom={crop_b}px, left={crop_l}px, right={crop_r}px")
    print(f"  Target:      {out_w}x{out_h}")
    print(f"  Output:      {os.path.basename(output_path)}")

    cl, cr = _expr(left, 'iw'), _expr(right, 'iw')
    ct, cb = _expr(top, 'ih'), _expr(bottom, 'ih')
    vf = f"crop=iw-{cl}-{cr}:ih-{ct}-{cb}:{cl}:{ct}"

    # Pad to even dimensions for codec compatibility
    vf += ",pad=ceil(iw/2)*2:ceil(ih/2)*2"

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path]
    cmd += _tc_flags()
    cmd += ['-vf', vf, '-c:v', 'libx264', '-preset', 'medium',
            '-crf', '18', '-pix_fmt', 'yuv420p'] + _audio_flags(output_path) + [output_path]

    _run_ffmpeg(cmd)

    output_size = os.path.getsize(output_path) / (1024 * 1024)
    ratio = output_size / (src_size / (1024 * 1024)) * 100 if src_size else 0
    print(f"  Done:        {src_size / (1024**2):.1f} MB -> {output_size:.1f} MB ({ratio:.1f}%)")

    return output_path


REENCODE_PRESETS = {
    'preview': {
        'description': 'Fast preview, small file. 720p, CRF 28, 30fps.',
        'max_height': 720,
        'crf': 28,
        'preset': 'fast',
        'fps': 30,
    },
    'medium': {
        'description': 'Good quality, reasonable size. 1080p, CRF 23.',
        'max_height': 1080,
        'crf': 23,
        'preset': 'medium',
        'fps': None,
    },
    'high': {
        'description': 'High quality, moderate compression. Original resolution, CRF 18.',
        'max_height': None,
        'crf': 18,
        'preset': 'medium',
        'fps': None,
    },
    'proxy': {
        'description': 'Editing proxy. 1080p, CRF 20, fast decode.',
        'max_height': 1080,
        'crf': 20,
        'preset': 'fast',
        'fps': None,
    },
}


def reencode(input_path: str, output_path: str | None = None,
             max_height: int | None = None, crf: int = 23,
             preset: str = 'medium', fps: int | None = None,
             audio_bitrate: str = '192k', overwrite: bool = True) -> str:
    """Re-encode a video to reduce file size.

    Converts to H.264 with yuv420p, handling any input format, resolution,
    and aspect ratio. Preserves timecode and metadata. Dimensions are always
    rounded to even numbers. Output container matches the input by default
    (e.g. .mov stays .mov, preserving PCM audio and timecode natively).

    Args:
        input_path: Path to the source video file.
        output_path: Path for the output file. If None, appends '_reencoded'
            and preserves the input file extension.
        max_height: Maximum output height in pixels. The video is scaled down
            proportionally if it exceeds this. None keeps the original resolution.
        crf: Constant Rate Factor (0-51). Lower = better quality, larger file.
            Typical values: 18 (visually lossless), 23 (good), 28 (smaller).
        preset: x264 encoding preset. Controls speed vs compression efficiency.
            Options: ultrafast, superfast, veryfast, faster, fast, medium, slow,
            slower, veryslow. 'medium' is a good default.
        fps: Output frame rate. None keeps the original. Set to a fixed value
            (e.g. 24, 25, 30) to conform the output frame rate.
        audio_bitrate: AAC audio bitrate, used only when the output container
            requires transcoding (e.g. MP4). MOV outputs copy audio as-is.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created video file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        ValueError: If crf is out of range.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    if not 0 <= crf <= 51:
        raise ValueError(f"CRF must be 0-51, got {crf}")

    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        output_path = _output_path(input_path, '_reencoded')
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    # Probe source info for print output
    probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height,r_frame_rate,bit_rate',
                 '-show_entries', 'format=duration,size',
                 '-of', 'json', input_path]
    probe_result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
    probe_data = json.loads(probe_result.stdout)
    src_stream = probe_data.get('streams', [{}])[0]
    src_fmt = probe_data.get('format', {})
    src_w = int(src_stream.get('width', 0))
    src_h = int(src_stream.get('height', 0))
    src_fps_str = src_stream.get('r_frame_rate', '0/1')
    src_fps_num, src_fps_den = (int(x) for x in src_fps_str.split('/'))
    src_fps = src_fps_num / src_fps_den if src_fps_den else 0
    src_size = int(src_fmt.get('size', 0))
    src_duration = float(src_fmt.get('duration', 0))

    # Compute target resolution
    if max_height is not None and src_h > max_height:
        target_h = max_height
        target_w = round(src_w * max_height / src_h / 2) * 2
    else:
        target_h = src_h
        target_w = src_w
    target_fps = fps if fps is not None else src_fps

    print(f"Re-encoding {os.path.basename(input_path)}")
    print(f"  Source:      {src_w}x{src_h}, {src_fps:.1f} fps, {src_size / (1024**2):.1f} MB, "
          f"{_format_duration(src_duration)}")
    settings = f"{target_w}x{target_h}, {target_fps:.0f} fps, CRF {crf}, preset {preset}"
    print(f"  Target:      {settings}")
    out_ext = os.path.splitext(output_path)[1]
    audio_mode = "copy" if out_ext.lower() in ('.mov', '.mxf') else f"AAC {audio_bitrate}"
    print(f"  Audio:       {audio_mode}")
    print(f"  Output:      {os.path.basename(output_path)}")

    # Build video filter chain
    vf_parts = []

    if max_height is not None:
        # Scale down only if the video is taller than max_height.
        # -2 ensures width is rounded to even, and we clamp height to even too.
        vf_parts.append(
            f"scale=-2:'min({max_height},ih)':force_original_aspect_ratio=decrease"
        )

    if fps is not None:
        vf_parts.append(f"fps={fps}")

    # Always ensure even dimensions for H.264 compatibility
    vf_parts.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path]
    cmd += _tc_flags()
    cmd += ['-vf', ','.join(vf_parts)]
    cmd += ['-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p']
    cmd += _audio_flags(output_path, audio_bitrate)
    cmd += [output_path]

    _run_ffmpeg(cmd)

    output_size = os.path.getsize(output_path) / (1024 * 1024)
    ratio = output_size / (src_size / (1024 * 1024)) * 100 if src_size else 0
    print(f"  Done:        {src_size / (1024**2):.1f} MB -> {output_size:.1f} MB ({ratio:.1f}%)")

    return output_path


def reencode_preset(input_path: str, preset_name: str = 'medium',
                    output_path: str | None = None, overwrite: bool = True) -> str:
    """Re-encode a video using a named preset.

    Available presets:
        - 'preview': 720p, CRF 28, 30fps — small file for quick review
        - 'medium': 1080p, CRF 23 — good quality, reasonable size
        - 'high': Original resolution, CRF 18 — high quality, moderate compression
        - 'proxy': 1080p, CRF 20, fast preset — editing proxy

    Args:
        input_path: Path to the source video file.
        preset_name: One of the preset names above.
        output_path: Path for the output file. If None, appends the preset name.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created .mp4 file.

    Raises:
        ValueError: If preset_name is not recognized.
    """
    if preset_name not in REENCODE_PRESETS:
        available = ', '.join(f"'{k}'" for k in REENCODE_PRESETS)
        raise ValueError(f"Unknown preset '{preset_name}'. Available: {available}")

    p = REENCODE_PRESETS[preset_name]

    if output_path is None:
        abs_input = os.path.abspath(os.path.expanduser(input_path))
        output_path = _output_path(abs_input, f'_{preset_name}')

    return reencode(
        input_path=input_path,
        output_path=output_path,
        max_height=p.get('max_height'),
        crf=p['crf'],
        preset=p['preset'],
        fps=p.get('fps'),
        overwrite=overwrite,
    )


def _build_atempo_filter(speed: float) -> str:
    """Build an atempo filter chain for the given speed.

    ffmpeg's atempo filter only accepts values in [0.5, 100.0], so extreme
    slow-downs need to be chained (e.g. 0.25x = atempo=0.5,atempo=0.5).
    """
    if speed >= 0.5:
        return f"atempo={speed}"

    parts = []
    remaining = speed
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining}")
    return ",".join(parts)





if __name__ == '__main__':
    ...