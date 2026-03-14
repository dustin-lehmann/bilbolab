import io
import base64
import os
from typing import Any, Optional

from PIL import Image

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from core.utils.dict_utils import update_dict
from extensions.gui.src.lib.objects.objects import Widget


class ImageWidget(Widget):
    type = 'image'

    def __init__(self, widget_id: str, image: str | list, **kwargs):
        """
        :param widget_id: Unique identifier for this widget
        :param image: Either a filesystem path (str) or a pre-parsed list/URI
        :param kwargs: Overrides for default_config keys:
                       - background_color: CSS color (default 'transparent')
                       - fit: one of 'contain', 'cover', 'fill'
                       - parse_local_image: if True and `image` is str, will load & encode
                       - title: optional tooltip/text
                       - clickable: if True, will emit click events to Python via onMessage
        """
        super().__init__(widget_id)

        default_config = {
            'background_color': 'transparent',
            'fit': 'contain',  # 'cover', 'contain', 'fill'
            'parse_local_image': True,
            'title': None,
            'clickable': False,
        }
        self.config = {**default_config, **kwargs}
        # call through setter
        self.image = image

    @property
    def image(self) -> str | list:
        return self._image

    @image.setter
    def image(self, new_image: str | list):
        # If it's a file path and we want to parse locally, produce a data-URI
        if isinstance(new_image, str) and self.config.get('parse_local_image', False):
            try:
                with Image.open(new_image) as img:
                    # convert everything to RGBA so browsers handle transparency consistently
                    img = img.convert('RGBA')
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
                    uri = f"data:image/png;base64,{b64}"
                    self._image = uri
            except Exception as e:
                raise ValueError(f"Could not load or parse image '{new_image}': {e}")
        else:
            # either already a data-URI string, or a numeric array / list
            self._image = new_image

    def getConfiguration(self) -> dict:
        """
        Returns the full config payload your JS widget will need.
        """
        payload = {
            'image': self._image,
            **self.config
        }
        return payload

    def init(self, websocket) -> None:
        """
        Called once the widget is registered on the client.
        Default behavior: push initial configuration.
        """
        config = self.getConfiguration()
        websocket.send_json({
            'action': 'init_widget',
            'payload': config
        })

    def handleEvent(self, message: dict, sender=None) -> None:
        """
        Handle incoming messages from the frontend.
        Example: click events if `clickable=True`.
        """
        self.logger.debug(f"Received message: {message}")


# ======================================================================================================================
def _to_pil_from_numpy(arr: "np.ndarray") -> Image.Image:
    """
    Convert a HxW, HxWx3, or HxWx4 numpy array to a PIL image.
    Values may be float [0..1] or uint8 [0..255].
    """
    if np is None:
        raise RuntimeError("NumPy is not available but a numpy array was provided.")

    if arr.dtype.kind in ("f", "d"):
        arr = np.clip(arr, 0.0, 1.0)
        arr = (arr * 255.0 + 0.5).astype("uint8")

    if arr.ndim == 2:
        mode = "L"
    elif arr.ndim == 3 and arr.shape[2] == 3:
        mode = "RGB"
    elif arr.ndim == 3 and arr.shape[2] == 4:
        mode = "RGBA"
    else:
        raise ValueError("Unsupported numpy array shape; expected HxW, HxWx3, or HxWx4")
    return Image.fromarray(arr, mode=mode)


def _pil_to_data_uri(img: Image.Image, fmt: str = "PNG", **save_kwargs) -> str:
    """
    Encode a PIL image to a data URI (default PNG).
    """
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save_kwargs)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = f"image/{fmt.lower()}"
    return f"data:{mime};base64,{b64}"


def _bytes_to_data_uri(raw: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ======================================================================================================================
class UpdatableImageWidget(Widget):
    """
    A dynamic image widget. Send serialized images (data-URI) to the frontend.

    Helper methods included:
      - setFromMatplotLib(fig=None, ax=None, ...)
      - setFromFile(filepath)
      - setFromPIL(img)
      - setFromBytes(raw_bytes, mime="image/png")
      - setFromArray(np_array)
      - updateImage(image_data)   # accepts a ready-made data-URI string
    """
    type = 'updatable_image'
    image_data: Optional[str]

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'background_color': 'transparent',
            'fit': 'fill',  # 'cover', 'contain', 'fill'
            'title': None,
            'clickable': False,
        }
        self.config = update_dict(default_config, kwargs)
        self.image_data = None  # store current data-URI string

    # === HELPERS ======================================================================================================

    def _send_init_or_update(self):
        """
        Push either an init or an incremental update depending on your framework.
        Here we just use sendUpdate() which GUI_Object typically provides.
        """
        self.sendUpdate(self.getPayload())

    # === METHODS ======================================================================================================

    def setFromMatplotLib(
            self,
            fig: Figure | None = None,
            ax: Axes | None = None,
            *,
            dpi: int = 150,
            fmt: str = "png",
            transparent: bool = True,
            facecolor: str | None = None,
            bbox_inches: str | None = "tight",
            pad_inches: float = 0.05
    ) -> str:
        """
        Render a Matplotlib Figure/Axes to a PNG or other format and update the widget.

        Returns the data-URI string for convenience.
        """
        if plt is None or (Figure is None):
            raise RuntimeError("Matplotlib not available; cannot serialize a figure.")

        if fig is None and ax is not None:
            fig = ax.figure
        if fig is None:
            fig = plt.gcf()

        buf = io.BytesIO()
        fig.savefig(
            buf,
            format=fmt,
            dpi=dpi,
            transparent=transparent,
            facecolor=facecolor,
            bbox_inches=bbox_inches,
            pad_inches=pad_inches,
        )
        uri = _bytes_to_data_uri(buf.getvalue(), mime=f"image/{fmt.lower()}")
        self.updateImage(uri)
        return uri

    # ------------------------------------------------------------------------------------------------------------------
    def setFromFile(self, filepath: str, *, to_format: str = "PNG") -> str:
        """
        Load an image from disk and convert it to a data URI (default PNG).
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Image file not found: {filepath}")
        with Image.open(filepath) as img:
            # keep alpha if present
            img = img.convert("RGBA") if img.mode in ("LA", "P", "RGBA") else img.convert("RGB")
            uri = _pil_to_data_uri(img, fmt=to_format)
        self.updateImage(uri)
        return uri

    # ------------------------------------------------------------------------------------------------------------------
    def setFromPIL(self, img: Image.Image, *, to_format: str = "PNG", **save_kwargs) -> str:
        """
        Accept a PIL Image and convert it to a data URI.
        """
        # normalize mode for browser friendliness
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        uri = _pil_to_data_uri(img, fmt=to_format, **save_kwargs)
        self.updateImage(uri)
        return uri

    # ------------------------------------------------------------------------------------------------------------------
    def setFromBytes(self, raw: bytes, *, mime: str = "image/png") -> str:
        """
        Accept raw image bytes and wrap as data URI (assumes provided mime).
        """
        uri = _bytes_to_data_uri(raw, mime=mime)
        self.updateImage(uri)
        return uri

    # ------------------------------------------------------------------------------------------------------------------
    def setFromArray(self, arr: np.ndarray, *, to_format: str = "PNG") -> str:
        """
        Accept a numpy array (HxW, HxWx3, or HxWx4) and convert to data URI.
        """
        if np is None:
            raise RuntimeError("NumPy not available; cannot convert array to image.")
        img = _to_pil_from_numpy(arr)
        return self.setFromPIL(img, to_format=to_format)

    # ------------------------------------------------------------------------------------------------------------------
    def updateImage(self, image_data: Any) -> None:
        """
        Update widget image. Prefer passing a data-URI string.
        """
        # If a dict like {"mime": "...", "b64": "..."} comes in, normalize
        if isinstance(image_data, dict) and "b64" in image_data:
            mime = image_data.get("mime", "image/png")
            self.image_data = _bytes_to_data_uri(base64.b64decode(image_data["b64"]), mime=mime)
        else:
            # assume data-URI string
            self.image_data = str(image_data)

        # Send to frontend
        self._send_init_or_update()

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        """
        Initial config sent on widget registration.
        """
        return {
            **self.config,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        """
        Incremental update payload (what frontend `update()` will receive).
        """

        payload = super().getPayload()
        payload['image'] = self.image_data
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        """
        Handle incoming frontend events (e.g., clicks if clickable).
        """
        evt = message.get('event')
        self.logger.debug(f"[UpdatableImageWidget {self.id}] Event: {evt} | Msg: {message}")
