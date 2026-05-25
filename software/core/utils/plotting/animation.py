from typing import Optional
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from core.utils.plotting.plot import Plot, Series, PlotConfig, AxisConfig, Axis
from core.utils.timecode.helpers import smpte_to_seconds
from core.utils.timecode.timecode import Timecode


# def animate_plot(
#         plot: Plot,
#         file: str,
#         transparent_background: bool = True,
#         fps: float = 30.0,
#         include_end_dots: bool = True,
#         timecode: Optional[float] = None,
#         variable_frame_rate: bool = True,
#         output_fps: Optional[float] = None,
#         drop_frame_timecode: bool = False,
# ) -> str:
#     """
#     Animate all Series in a Plot into a time-based overlay video.
#
#     - Assumes the x-axis of all Series represents time (in seconds).
#     - Axes, titles, labels, legends, etc. are taken from the existing plot.
#     - Axis limits:
#         * If AxisConfig.xlim/ylim are set, they are respected.
#         * If not set, limits are computed from the full data (as in the final
#           static plot) before rendering any frames.
#     - Animation:
#         * Lines are progressively revealed over time, based on their x_data.
#         * All axes/series are updated in lockstep w.r.t. a global time axis.
#     - Video:
#         * Frames are saved as PNGs with optional alpha.
#         * ffmpeg is used to create a ProRes 4444 .mov with alpha channel.
#         * If `output_fps` is None and `variable_frame_rate=True`:
#             - Variable frame durations reflect the time spacing in the data.
#           Otherwise:
#             - Frames are rendered on a constant-rate time grid at `output_fps`.
#     - Timecode:
#         * If `timecode` is not None, a SMPTE timecode is embedded in the
#           video metadata so you can sync in NLEs (e.g. Premiere).
#         * `timecode` is given in seconds for the START of the video.
#         * `fps` is the nominal fps to use for SMPTE conversion (e.g. 59.94).
#         * `drop_frame_timecode` enables NTSC-style drop-frame TC
#           (useful for 29.97 / 59.94).
#
#     Parameters
#     ----------
#     plot : Plot
#         The Plot object whose Series will be animated.
#     file : str
#         Target video file path. If no extension is given, '.mov' is added.
#     transparent_background : bool, default True
#         If True, save frames with transparent figure background (alpha).
#     fps : float, default 30.0
#         Nominal frame-rate to use for SMPTE timecode conversion only.
#         (Does not control actual video frame rate unless you also set
#          output_fps := fps.)
#     include_end_dots : bool, default True
#         If True, draw small circles at the *current* end of each time series
#         in every frame (moving tip indicator).
#     timecode : float | None, default None
#         Start timecode in seconds for the video metadata. If None, no
#         explicit timecode is embedded.
#     variable_frame_rate : bool, default True
#         If True and `output_fps` is None: use variable frame durations
#         based on data times. If `output_fps` is not None, this flag is
#         ignored and a constant frame rate is used.
#     output_fps : float | None, default None
#         If not None: target constant frame-rate for the rendered video
#         (e.g. 59.94 to match your Sony camera). Frames are rendered at
#         multiples of 1/output_fps relative to the earliest data time.
#     drop_frame_timecode : bool, default False
#         Whether to use SMPTE drop-frame timecode formatting (NTSC-style)
#         when embedding the starting timecode.
#
#     Returns
#     -------
#     str
#         Absolute path to the generated video file.
#
#     Raises
#     ------
#     ValueError
#         If the plot has no series or timestamps are not strictly increasing.
#     RuntimeError
#         If ffmpeg fails.
#     """
#
#     def seconds_to_timecode(seconds: float, fps_: float, drop_frame: bool = False) -> str:
#         """
#         Convert seconds → SMPTE timecode.
#
#         - Non–drop-frame: HH:MM:SS:FF (all colons)
#         - Drop-frame (NTSC ~29.97/59.94): HH:MM:SS;FF (semicolon before frames)
#         """
#         # Basic non-DF case (works for integers and fractional fps)
#         if not drop_frame:
#             total_frames = int(round(seconds * fps_))
#             fps_int = int(round(fps_))
#
#             frames = total_frames % fps_int
#             total_seconds = total_frames // fps_int
#             s = total_seconds % 60
#             total_minutes = total_seconds // 60
#             m = total_minutes % 60
#             h = total_minutes // 60
#             # Non-DF has ":" before frames
#             return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"
#
#         # --- Drop-frame timecode (NTSC-style) -------------------------------
#         # Only well-defined for ~29.97 and ~59.94
#         fps_int = int(round(fps_))
#         if fps_int not in (30, 60):
#             raise ValueError(
#                 "Drop-frame timecode is only standardised for ~29.97 or ~59.94 fps."
#             )
#
#         # how many frame numbers are dropped per minute
#         # 29.97 DF @ 30fps nominal -> 2
#         # 59.94 DF @ 60fps nominal -> 4
#         drop_frames = int(round(fps_int * 0.0666666667))  # ≈ fps * 2/30
#
#         frames_per_hour = fps_int * 60 * 60
#         frames_per_minute = fps_int * 60
#         frames_per_10mins = frames_per_minute * 10
#
#         # frame count at true video fps (e.g. 29.97, 59.94)
#         total_frames = int(round(seconds * fps_))
#
#         # constrain to 24h to avoid overflow
#         total_frames = total_frames % (frames_per_hour * 24)
#
#         # Apply SMPTE DF algorithm: convert "real" frame counter to timecode frame-numbering
#         d = total_frames // frames_per_10mins
#         m = total_frames % frames_per_10mins
#
#         total_frames += drop_frames * (9 * d)
#         if m >= drop_frames:
#             total_frames += drop_frames * ((m - drop_frames) // (frames_per_minute - drop_frames))
#
#         frames = total_frames % fps_int
#         total_seconds = total_frames // fps_int
#         s = total_seconds % 60
#         total_minutes = total_seconds // 60
#         m = total_minutes % 60
#         h = total_minutes // 60
#
#         # DF uses semicolon before frames
#         return f"{h:02d}:{m:02d}:{s:02d};{frames:02d}"
#
#     # --- Collect all series and their full data ---------------------------------
#     if not plot.axes:
#         raise ValueError("Plot has no axes to animate.")
#
#     series_data: dict[Series, tuple[np.ndarray, np.ndarray]] = {}
#     all_times_list: list[np.ndarray] = []
#
#     for axis in plot.axes.values():
#         for series in axis.series.values():
#             x = np.asarray(series.x_data, dtype=float)
#             y = np.asarray(series.y_data, dtype=float)
#
#             if x.size == 0:
#                 continue
#
#             series_data[series] = (x, y)
#             all_times_list.append(x)
#
#     if not series_data:
#         raise ValueError("Plot has no Series with data to animate.")
#
#     # Flatten all times and get global min/max, unique sorted times
#     all_times = np.concatenate(all_times_list)
#     finite_mask = np.isfinite(all_times)
#     if not np.any(finite_mask):
#         raise ValueError("All time values (x_data) are NaN/inf.")
#
#     all_times = all_times[finite_mask]
#     t_min = float(np.min(all_times))
#     t_max = float(np.max(all_times))
#
#     # Unique, sorted times for frames (in original axis time)
#     unique_times = np.unique(all_times).astype(float)
#     if unique_times.size == 0:
#         raise ValueError("No valid frame times found from x_data.")
#
#     # Infer data fps (for info / fallback CFR when output_fps is None)
#     data_fps: Optional[float] = None
#     if unique_times.size > 1:
#         diffs = np.diff(unique_times)
#         diffs = diffs[diffs > 0]
#         if diffs.size > 0:
#             median_dt = float(np.median(diffs))
#             if median_dt > 0:
#                 data_fps = 1.0 / median_dt
#
#     # --- Build frame time grid --------------------------------------------------
#     if output_fps is not None:
#         # Constant frame-rate grid at output_fps
#         duration = max(0.0, t_max - t_min)
#         if duration == 0.0:
#             # Degenerate case: single frame
#             n_frames = 1
#         else:
#             # Ensure we include the last moment
#             n_frames = int(np.floor(duration * output_fps)) + 1
#
#         frame_indices = np.arange(n_frames, dtype=float)
#         rel_frame_times = frame_indices / float(output_fps)  # relative to t_min
#         frame_times = t_min + rel_frame_times
#     else:
#         # Use actual data times (original behavior)
#         frame_times = unique_times
#         rel_frame_times = frame_times - t_min  # >= 0
#
#     # Timestamps used for ffmpeg concat (absolute in "seconds since 0")
#     # Adding a constant offset does not change durations; it only matters
#     # for SMPTE timecode start.
#     base_offset = float(timecode) if timecode is not None else 0.0
#     timestamps = [float(t_rel + base_offset) for t_rel in rel_frame_times]
#
#     # Sanity: timestamps strictly increasing
#     for i in range(1, len(timestamps)):
#         if timestamps[i] <= timestamps[i - 1]:
#             raise ValueError("Timestamps must be strictly increasing.")
#
#     fig = plot.figure
#
#     # --- Ensure axis limits if not explicitly set in AxisConfig -----------------
#     for axis in plot.axes.values():
#         xs_axis: list[np.ndarray] = []
#         ys_axis: list[np.ndarray] = []
#         for series, (x_full, y_full) in series_data.items():
#             if series.ax is axis.ax:
#                 xs_axis.append(x_full)
#                 ys_axis.append(y_full)
#
#         if axis.ax is None:
#             continue
#
#         mpl_ax = axis.ax
#
#         # X limits: if not set in config, compute from full data
#         if axis.config.xlim is None and xs_axis:
#             x_min = float(min(np.nanmin(x) for x in xs_axis))
#             x_max = float(max(np.nanmax(x) for x in xs_axis))
#             mpl_ax.set_xlim(x_min, x_max)
#
#         # Y limits: if not set in config, compute from full data
#         if axis.config.ylim is None and ys_axis:
#             y_min = float(min(np.nanmin(y) for y in ys_axis))
#             y_max = float(max(np.nanmax(y) for y in ys_axis))
#             if not np.isfinite(y_min) or not np.isfinite(y_max):
#                 # Fallback to current limits if data are degenerate
#                 y_min, y_max = mpl_ax.get_ylim()
#
#             if y_min == y_max:
#                 # Expand a bit so the line is visible
#                 margin = 0.5 if y_min == 0 else abs(y_min) * 0.05
#                 y_min -= margin
#                 y_max += margin
#             mpl_ax.set_ylim(y_min, y_max)
#
#     # --- Make legend backgrounds transparent (for overlay use) ------------------
#     for axis in plot.axes.values():
#         if axis.ax is None:
#             continue
#         leg = axis.ax.get_legend()
#         if leg is not None:
#             frame = leg.get_frame()
#             # frame.set_facecolor("none")
#             # frame.set_alpha(0.0)
#
#     # Use same dpi as saving still images
#     save_dpi = plot.config.save_dpi if plot.config.save_dpi is not None else plot.config.dpi
#
#     # Normalize output path (default to .mov / ProRes 4444)
#     output_path = Path(file)
#     if output_path.suffix == "":
#         output_path = output_path.with_suffix(".mov")
#     output_path = output_path.resolve()
#
#     # --- Generate frames and ffmpeg concat file in a temp dir -------------------
#     try:
#         with tempfile.TemporaryDirectory() as tmpdir_str:
#             tmpdir = Path(tmpdir_str)
#             frame_paths: list[Path] = []
#
#             # Generate frames by progressively revealing data
#             for idx, t_current in enumerate(frame_times):
#                 extra_artists = []
#
#                 # Update all series for this frame
#                 for series, (x_full, y_full) in series_data.items():
#                     if series.ax is None:
#                         continue
#
#                     # Show data up to current time
#                     mask = x_full <= t_current
#                     if np.any(mask):
#                         x_frame = x_full[mask]
#                         y_frame = y_full[mask]
#                     else:
#                         x_frame = np.asarray([])
#                         y_frame = np.asarray([])
#
#                     # Update line data (without autoscaling)
#                     series.set_data(x_frame, y_frame, autoscale=False)
#
#                 # Draw moving end dots at the *current* end of each series
#                 if include_end_dots:
#                     for axis in plot.axes.values():
#                         if axis.ax is None:
#                             continue
#                         mpl_ax = axis.ax
#                         for series, (x_full, y_full) in series_data.items():
#                             if series.ax is not mpl_ax or x_full.size == 0:
#                                 continue
#
#                             # Points included up to current time
#                             mask = x_full <= t_current
#                             if not np.any(mask):
#                                 continue
#
#                             # Last visible point in this frame
#                             x_end = float(x_full[mask][-1])
#                             y_end = float(y_full[mask][-1])
#
#                             if series.line is not None:
#                                 color = series.line.get_color()
#                                 zorder = series.line.get_zorder() + 1
#                                 base_ms = getattr(series.line, "get_markersize", lambda: None)()
#                                 if base_ms is None:
#                                     base_ms = series.config.marker_size
#                             else:
#                                 color = "black"
#                                 zorder = 5
#                                 base_ms = series.config.marker_size
#
#                             # Slightly smaller than configured, but at least 2
#                             ms = max(float(base_ms) * 0.75, 2.0)
#
#                             (dot,) = mpl_ax.plot(
#                                 [x_end],
#                                 [y_end],
#                                 marker="o",
#                                 markersize=ms,
#                                 linestyle="",
#                                 color=color,
#                                 zorder=zorder,
#                             )
#                             extra_artists.append(dot)
#
#                 # Render and save frame
#                 fig.canvas.draw()
#                 frame_path = tmpdir / f"frame_{idx:05d}.png"
#                 fig.savefig(
#                     frame_path,
#                     dpi=save_dpi,
#                     transparent=transparent_background,
#                     facecolor=fig.get_facecolor(),
#                     bbox_inches="tight",
#                     pad_inches=0.05,
#                 )
#                 frame_paths.append(frame_path)
#
#                 # Clean up temporary end-dot artists so they don't persist
#                 for artist in extra_artists:
#                     try:
#                         artist.remove()
#                     except Exception:
#                         pass
#
#             # Build ffmpeg concat file with durations based on timestamps
#             concat_file = tmpdir / "frames.txt"
#             with concat_file.open("w", encoding="utf-8") as f:
#                 for i, frame_path in enumerate(frame_paths):
#                     f.write(f"file '{frame_path.as_posix()}'\n")
#                     if i < len(timestamps) - 1:
#                         duration = timestamps[i + 1] - timestamps[i]
#                         if duration <= 0:
#                             raise ValueError("Timestamps must be strictly increasing.")
#                         f.write(f"duration {duration:.10f}\n")
#
#             # Pad to even width/height and preserve alpha
#             pad_filter = (
#                 "pad=width=ceil(iw/2)*2:"
#                 "height=ceil(ih/2)*2:"
#                 "color=black@0.0"
#             )
#
#             cmd = [
#                 "ffmpeg",
#                 "-y",
#                 "-f", "concat",
#                 "-safe", "0",
#                 "-i", str(concat_file),
#                 "-vf", pad_filter,
#             ]
#
#             # Decide CFR / VFR behavior
#             if output_fps is not None:
#                 # Explicit constant output fps (e.g. 59.94)
#                 cmd.extend([
#                     "-vsync", "cfr",
#                     "-r", f"{output_fps:.8f}",
#                 ])
#             elif not variable_frame_rate and data_fps is not None:
#                 # Fallback: force CFR at inferred data fps
#                 cmd.extend([
#                     "-vsync", "cfr",
#                     "-r", f"{data_fps:.8f}",
#                 ])
#             # else: keep VFR (no vsync/r), using concat durations
#
#             # ProRes + alpha
#             cmd.extend([
#                 "-c:v", "prores_ks",
#                 "-profile:v", "4",  # ProRes 4444
#                 "-pix_fmt", "yuva444p10le",  # YUV + alpha, 10-bit
#             ])
#
#             # Add SMPTE timecode if requested
#             if timecode is not None:
#                 # timecode is "start of video" in seconds
#                 start_tc = seconds_to_timecode(timecode, fps, drop_frame_timecode)
#                 cmd.extend(["-timecode", start_tc])
#
#             cmd.append(str(output_path))
#
#             try:
#                 subprocess.run(cmd, check=True)
#             except subprocess.CalledProcessError as e:
#                 raise RuntimeError("FFmpeg failed while encoding the animation.") from e
#
#     finally:
#         # Restore original series data (without autoscaling)
#         for series, (x_full, y_full) in series_data.items():
#             try:
#                 series.set_data(x_full, y_full, autoscale=False)
#             except Exception:
#                 pass
#         try:
#             if plot.figure.canvas is not None:
#                 plot.figure.canvas.draw_idle()
#         except Exception:
#             pass
#
#     return str(output_path)


def animate_plot(
        plot: Plot,
        file: str,
        data_rate: float = 0.01,
        target_fps: float = 25.0,
        timecode: Timecode | None = None,
) -> str:
    """
    Animate all Series in a Plot into a time-based overlay video with constant fps.

    Parameters
    ----------
    plot : Plot
        The Plot object whose Series will be animated.
    file : str
        Target video file path. If no extension is given, '.mov' is added.
    data_rate : float, default 0.01
        Nominal time step of the underlying data in seconds (Δt between samples).
        This is checked against the time vector (x_data) for sanity.
    target_fps : float, default 25.0
        Constant frame rate of the output video (ffmpeg `-r` and `-vsync cfr`).
    timecode : Timecode | None, default None
        Starting SMPTE timecode for the video. If provided and its internal
        fps differs from `target_fps`, it is rebased via `timecode.rebase_fps`
        so that the absolute time is preserved but the frame number is
        expressed at `target_fps`.

    Returns
    -------
    str
        Absolute path to the generated video file.
    """
    import warnings

    # --- Collect all series and their full data ---------------------------------
    if not plot.axes:
        raise ValueError("Plot has no axes to animate.")

    series_data: dict[Series, tuple[np.ndarray, np.ndarray]] = {}
    all_times_list: list[np.ndarray] = []

    for axis in plot.axes.values():
        for series in axis.series.values():
            x = np.asarray(series.x_data, dtype=float)
            y = np.asarray(series.y_data, dtype=float)

            if x.size == 0:
                continue

            series_data[series] = (x, y)
            all_times_list.append(x)

    if not series_data:
        raise ValueError("Plot has no Series with data to animate.")

    # Flatten all times and get global min/max, unique sorted times
    all_times = np.concatenate(all_times_list)
    finite_mask = np.isfinite(all_times)
    if not np.any(finite_mask):
        raise ValueError("All time values (x_data) are NaN/inf.")

    all_times = all_times[finite_mask]
    t_min = float(np.min(all_times))
    t_max = float(np.max(all_times))

    unique_times = np.unique(all_times).astype(float)
    if unique_times.size == 0:
        raise ValueError("No valid frame times found from x_data.")

    # Infer data fps from time vector
    data_fps: Optional[float] = None
    inferred_data_rate: Optional[float] = None
    if unique_times.size > 1:
        diffs = np.diff(unique_times)
        diffs = diffs[diffs > 0]
        if diffs.size > 0:
            median_dt = float(np.median(diffs))
            if median_dt > 0.0:
                inferred_data_rate = median_dt
                data_fps = 1.0 / median_dt

    # --- Sanity check: data_rate vs time vector ---------------------------------
    if inferred_data_rate is not None and data_rate > 0:
        rel_diff = abs(inferred_data_rate - data_rate) / data_rate
        if rel_diff > 0.05:  # more than 5% off
            warnings.warn(
                f"Provided data_rate={data_rate:.6f}s does not closely match the "
                f"median Δt from x_data ({inferred_data_rate:.6f}s). "
                f"Check that your time axis and data_rate are consistent.",
                RuntimeWarning,
            )

    # --- Build constant frame-rate time grid at target_fps ----------------------
    if target_fps <= 0:
        raise ValueError("target_fps must be positive")

    duration = max(0.0, t_max - t_min)
    if duration == 0.0:
        n_frames = 1
    else:
        n_frames = int(np.floor(duration * target_fps)) + 1

    frame_indices = np.arange(n_frames, dtype=float)
    rel_frame_times = frame_indices / float(target_fps)  # relative to t_min
    frame_times = t_min + rel_frame_times

    # Timestamps used for ffmpeg concat (seconds since 0).
    # Absolute offset doesn't matter for durations; we start at 0.
    timestamps = [float(t_rel) for t_rel in rel_frame_times]

    # Sanity: timestamps strictly increasing
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            raise ValueError("Timestamps must be strictly increasing.")

    fig = plot.figure

    # --- Ensure axis limits if not explicitly set in AxisConfig -----------------
    for axis in plot.axes.values():
        xs_axis: list[np.ndarray] = []
        ys_axis: list[np.ndarray] = []
        for series, (x_full, y_full) in series_data.items():
            if series.ax is axis.ax:
                xs_axis.append(x_full)
                ys_axis.append(y_full)

        if axis.ax is None:
            continue

        mpl_ax = axis.ax

        # X limits: if not set in config, compute from full data
        if axis.config.xlim is None and xs_axis:
            x_min = float(min(np.nanmin(x) for x in xs_axis))
            x_max = float(max(np.nanmax(x) for x in xs_axis))
            mpl_ax.set_xlim(x_min, x_max)

        # Y limits: if not set in config, compute from full data
        if axis.config.ylim is None and ys_axis:
            y_min = float(min(np.nanmin(y) for y in ys_axis))
            y_max = float(max(np.nanmax(y) for y in ys_axis))
            if not np.isfinite(y_min) or not np.isfinite(y_max):
                y_min, y_max = mpl_ax.get_ylim()

            if y_min == y_max:
                margin = 0.5 if y_min == 0 else abs(y_min) * 0.05
                y_min -= margin
                y_max += margin
            mpl_ax.set_ylim(y_min, y_max)

    # --- Make legend backgrounds transparent (for overlay use) ------------------
    for axis in plot.axes.values():
        if axis.ax is None:
            continue
        leg = axis.ax.get_legend()
        if leg is not None:
            frame = leg.get_frame()
            # If you want a fully transparent legend box, uncomment:
            # frame.set_facecolor("none")
            # frame.set_alpha(0.0)

    # Use the same dpi as saving still images
    save_dpi = plot.config.save_dpi if plot.config.save_dpi is not None else plot.config.dpi

    # Normalize an output path (default to .mov / ProRes 4444)
    output_path = Path(file)
    if output_path.suffix == "":
        output_path = output_path.with_suffix(".mov")
    output_path = output_path.resolve()

    include_end_dots = True  # keep behavior from the original helper

    # --- Generate frames and ffmpeg concat file in a temp dir -------------------
    try:
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            frame_paths: list[Path] = []

            # Generate frames by progressively revealing data
            for idx, t_current in enumerate(frame_times):
                extra_artists = []

                # Update all series for this frame
                for series, (x_full, y_full) in series_data.items():
                    if series.ax is None:
                        continue

                    mask = x_full <= t_current
                    if np.any(mask):
                        x_frame = x_full[mask]
                        y_frame = y_full[mask]
                    else:
                        x_frame = np.asarray([])
                        y_frame = np.asarray([])

                    series.set_data(x_frame, y_frame, autoscale=False)

                # Draw moving end dots at the *current* end of each series
                if include_end_dots:
                    for axis in plot.axes.values():
                        if axis.ax is None:
                            continue
                        mpl_ax = axis.ax
                        for series, (x_full, y_full) in series_data.items():
                            if series.ax is not mpl_ax or x_full.size == 0:
                                continue

                            mask = x_full <= t_current
                            if not np.any(mask):
                                continue

                            x_end = float(x_full[mask][-1])
                            y_end = float(y_full[mask][-1])

                            if series.line is not None:
                                color = series.line.get_color()
                                zorder = series.line.get_zorder() + 1
                                base_ms = getattr(series.line, "get_markersize", lambda: None)()
                                if base_ms is None:
                                    base_ms = series.config.marker_size
                            else:
                                color = "black"
                                zorder = 5
                                base_ms = series.config.marker_size

                            ms = max(float(base_ms) * 0.75, 2.0)

                            (dot,) = mpl_ax.plot(
                                [x_end],
                                [y_end],
                                marker="o",
                                markersize=ms,
                                linestyle="",
                                color=color,
                                zorder=zorder,
                            )
                            extra_artists.append(dot)

                # Render and save frame
                fig.canvas.draw()
                frame_path = tmpdir / f"frame_{idx:05d}.png"
                fig.savefig(
                    frame_path,
                    dpi=save_dpi,
                    transparent=True,
                    facecolor=fig.get_facecolor(),
                    bbox_inches="tight",
                    pad_inches=0.05,
                )
                frame_paths.append(frame_path)

                # Clean up temporary end-dot artists so they don't persist
                for artist in extra_artists:
                    try:
                        artist.remove()
                    except Exception:
                        pass

            # Build ffmpeg concat file with durations based on timestamps
            concat_file = tmpdir / "frames.txt"
            with concat_file.open("w", encoding="utf-8") as f:
                for i, frame_path in enumerate(frame_paths):
                    f.write(f"file '{frame_path.as_posix()}'\n")
                    if i < len(timestamps) - 1:
                        duration = timestamps[i + 1] - timestamps[i]
                        if duration <= 0:
                            raise ValueError("Timestamps must be strictly increasing.")
                        f.write(f"duration {duration:.10f}\n")

            # Pad to even width/height and preserve alpha
            pad_filter = (
                "pad=width=ceil(iw/2)*2:"
                "height=ceil(ih/2)*2:"
                "color=black@0.0"
            )

            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-vf", pad_filter,
            ]

            # Force constant frame rate at target_fps
            cmd.extend([
                "-vsync", "cfr",
                "-r", f"{target_fps:.8f}",
            ])

            # ProRes + alpha
            cmd.extend([
                "-c:v", "prores_ks",
                "-profile:v", "4",  # ProRes 4444
                "-pix_fmt", "yuva444p10le",  # YUV + alpha, 10-bit
            ])

            # Add SMPTE timecode if requested, rebased to target_fps if needed
            if timecode is not None:
                tc = timecode
                if tc.fps is None:
                    raise ValueError("Timecode.fps must be set")
                if abs(tc.fps - target_fps) > 1e-3:
                    tc = tc.rebase_fps(new_fps=target_fps, df=tc.df)
                cmd.extend(["-timecode", tc.to_string()])

            cmd.append(str(output_path))

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError("FFmpeg failed while encoding the animation.") from e

    finally:
        # Restore original series data (without autoscaling)
        for series, (x_full, y_full) in series_data.items():
            try:
                series.set_data(x_full, y_full, autoscale=False)
            except Exception:
                pass
        try:
            if plot.figure.canvas is not None:
                plot.figure.canvas.draw_idle()
        except Exception:
            pass

    return str(output_path)
