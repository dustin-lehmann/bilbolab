from core.utils.dict_utils import update_dict
from extensions.gui.src.lib.objects.objects import Widget


class BILBO_Widget(Widget):

    type = 'bilbo_overview'


    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, **kwargs):
        super().__init__(widget_id, **kwargs)

        default_config = {
            'robot_id': 'bilbo',
            'robot_color': [0.7, 0.2, 0.2, 1]
        }

        self.config = update_dict(default_config, self.config, kwargs)


    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            **self.config,
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> None:
        self.logger.debug(f"Received message: {message}")