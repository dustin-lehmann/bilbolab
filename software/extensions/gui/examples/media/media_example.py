"""
Media Widgets Example
=====================

Demonstrates image display widgets:
  - ImageWidget with a static image file
  - UpdatableImageWidget that can be refreshed from Python
  - CameraWidget (auto-discovers local webcams)

The updatable image is regenerated every second as a simple colour gradient,
showing how to push dynamic visual content from the backend.

Run from the `software/` directory:
    python -m extensions.gui.examples.media.media_example
"""

import base64
import io
import math
import os
import time

from core.utils.network.network import getHostIP
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.image import ImageWidget, UpdatableImageWidget
from extensions.gui.src.lib.objects.python.text import TextWidget


# ---------------------------------------------------------------------------
# Helper: generate a simple PNG gradient in pure Python (no matplotlib needed)
# Uses a minimal raw RGBA buffer -> PNG via built-in zlib
# ---------------------------------------------------------------------------
def _make_gradient_data_uri(width: int, height: int, phase: float) -> str:
    """Create a data URI of a colour gradient PNG that shifts with `phase`."""
    import struct
    import zlib

    # Build raw RGBA rows
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # PNG filter byte (None)
        for x in range(width):
            r = int(127.5 + 127.5 * math.sin(2 * math.pi * x / width + phase))
            g = int(127.5 + 127.5 * math.sin(2 * math.pi * y / height + phase * 0.7))
            b = int(127.5 + 127.5 * math.sin(phase + 1.0))
            raw_rows.extend([r, g, b, 255])

    # Minimal PNG encoder
    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xFFFFFFFF)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    compressed = zlib.compress(bytes(raw_rows))

    png = b'\x89PNG\r\n\x1a\n'
    png += png_chunk(b'IHDR', ihdr)
    png += png_chunk(b'IDAT', compressed)
    png += png_chunk(b'IEND', b'')

    b64 = base64.b64encode(png).decode('ascii')
    return f'data:image/png;base64,{b64}'


def main():
    host = getHostIP()
    app = GUI(id='gui', host=host, run_js=True)

    category = Category(id='media', name='Media', icon='I')
    app.addCategory(category)

    page = Page(id='main', name='Images')
    category.addPage(page, position=1)

    # =========================================================================
    # Static image — loaded from file
    # =========================================================================
    label_static = TextWidget(
        widget_id='label_static', text='Static Image (from file)',
        font_size=12, font_weight='bold', horizontal_alignment='left',
        vertical_alignment='center', text_color=[0.8, 0.8, 0.8])
    page.addWidget(label_static, row=1, column=1, width=8, height=1)

    # Path relative to the working directory (software/)
    cat_image_path = os.path.join(
        os.path.dirname(__file__), '..', 'assets', 'cat.png')

    static_img = ImageWidget(
        widget_id='static_img',
        image=cat_image_path,
        fit='contain',
        title='Cat',
        parse_local_image=True,
    )
    page.addWidget(static_img, row=2, column=1, width=8, height=8)

    # =========================================================================
    # Updatable image — regenerated from Python every second
    # =========================================================================
    label_dynamic = TextWidget(
        widget_id='label_dynamic', text='Dynamic Image (generated in Python)',
        font_size=12, font_weight='bold', horizontal_alignment='left',
        vertical_alignment='center', text_color=[0.8, 0.8, 0.8])
    page.addWidget(label_dynamic, row=1, column=10, width=10, height=1)

    dynamic_img = UpdatableImageWidget(
        widget_id='dynamic_img',
        fit='contain',
    )
    page.addWidget(dynamic_img, row=2, column=10, width=8, height=8)

    # Refresh button
    btn_refresh = Button(
        widget_id='btn_refresh', text='Refresh Now',
        color=[0.2, 0.4, 0.5])
    page.addWidget(btn_refresh, row=10, column=10, width=4, height=2)

    phase = {'v': 0.0}

    def refresh_image(*args, **kwargs):
        phase['v'] += 0.5
        data_uri = _make_gradient_data_uri(128, 128, phase['v'])
        dynamic_img.updateImage(data_uri)
        print(f'[media] Image refreshed (phase={phase["v"]:.1f})')

    btn_refresh.callbacks.click.register(refresh_image)

    # =========================================================================
    # Info text
    # =========================================================================
    info = TextWidget(
        widget_id='info',
        text='The dynamic image auto-updates every second.\n'
             'Click "Refresh Now" to advance the phase manually.\n\n'
             'For camera streaming, see CameraWidget\n'
             '(requires a connected webcam).',
        font_size=10, horizontal_alignment='left', vertical_alignment='top',
        text_color=[0.6, 0.6, 0.6],
    )
    page.addWidget(info, row=12, column=1, width=16, height=4)

    # --- Start ---------------------------------------------------------------
    app.start()

    # --- Auto-update loop ----------------------------------------------------
    t0 = time.time()
    while True:
        t = time.time() - t0
        data_uri = _make_gradient_data_uri(128, 128, t * 0.5)
        dynamic_img.updateImage(data_uri)
        time.sleep(1.0)


if __name__ == '__main__':
    main()
