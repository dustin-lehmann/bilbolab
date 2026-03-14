from core.utils.dict_utils import update_dict
from extensions.libs.babylon.src.babylon import BabylonVisualization
from extensions.gui.src.lib.objects.objects import Widget


class BabylonWidget(Widget):
    type = 'babylon_widget'

    babylon: BabylonVisualization | None = None

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'babylon_id': 'babylon'
        }

        self.config = update_dict(default_config, kwargs)

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            **self.config
        }
        return config

    def getPayload(self):
        payload = super().getPayload()
        payload['babylon'] = self.babylon.getPayload() if self.babylon else None
        return payload

    def handleEvent(self, message, sender=None) -> None:
        pass

    def set_babylon(self, babylon: BabylonVisualization) -> None:
        self.babylon = babylon

    # === RECORDING ====================================================================================================
    def start_recording(self,
                        filename: str = "babylonjs.webm",
                        fps: int = 60,
                        bitrate: int = 12_000_000,
                        save_path: str | None = None,
                        overlay: bool = False,
                        upscale: float = 1.0):
        """Start recording the BabylonJS visualization. Delegates to self.babylon."""
        if self.babylon is None:
            return
        self.babylon.start_recording(
            filename=filename, fps=fps, bitrate=bitrate,
            save_path=save_path, overlay=overlay, upscale=upscale,
        )

    def stop_recording(self):
        """Stop the current recording. Delegates to self.babylon."""
        if self.babylon is None:
            return
        self.babylon.stop_recording()

    @property
    def is_recording(self) -> bool:
        if self.babylon is None:
            return False
        return self.babylon.is_recording

    # === PRIVATE METHODS ==============================================================================================
