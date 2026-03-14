from core.utils.dict_utils import update_dict
from core.utils.logging_utils import Logger
from extensions.tools.cli.cli import CLI, CommandSet, Command, CommandArgument
from extensions.gui.src.lib.objects.objects import ObjectMessage, FunctionMessage


class CLI_Terminal:
    type = 'cli_terminal'

    parent = None

    # === INIT =========================================================================================================
    def __init__(self, id: str, cli: CLI = None, **kwargs):
        self.id = id
        self.cli = cli

        default_config = {
            'save_history': True,
        }

        self.config = update_dict(default_config, kwargs)
        self.logger = Logger(f"CLI_Terminal {self.id}", 'WARNING')

    # === PROPERTIES ===================================================================================================
    @property
    def uid(self):
        if self.parent is not None:
            return f"{self.parent.id}/terminals/{self.id}"
        else:
            return f"{self.id}"

    # === METHODS ======================================================================================================
    def setCLI(self, cli: CLI) -> None:
        self.cli = cli

        self.cli.callbacks.update.register(self._onCliUpdated)

        if self.parent is not None and hasattr(self.parent, 'updateConfig'):
            ...
            # self.parent.updateConfig

    # ------------------------------------------------------------------------------------------------------------------
    def print(self, text, color='white'):
        self.function('print', args=[text, color], spread_args=True)

    # ------------------------------------------------------------------------------------------------------------------
    def sendMessage(self, data, client=None):

        gui = self.parent
        if gui is None:
            return

        message = ObjectMessage(
            id=self.uid,
            data=data,
        )

        try:
            gui.send(message, client=client)
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    # ------------------------------------------------------------------------------------------------------------------
    def function(self, function_name, args, spread_args=True, client=None):

        message = FunctionMessage(
            function_name=function_name,
            args=args,
            spread_args=spread_args,
        )
        self.sendMessage(message, client=client)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self) -> dict:
        return {
            **self.config
        }

    # ------------------------------------------------------------------------------------------------------------------
    def getPayload(self) -> dict:
        payload = {
            'id': self.uid,
            'type': self.type,
            'config': self.getConfiguration(),
            'cli': self.cli.getPayload() if self.cli else None,
            'history': []
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def handleMessage(self, message: dict, sender=None) -> None:
        self.logger.debug(f"Received message: {message}")

        if self.cli is not None:
            command_string = message['data']['command']
            command_set = message['data']['set']

            self.cli.runCommand(command_string=command_string,
                                set=command_set,
                                allow_set_change=False)

    # === PRIVATE METHODS =============================================================================================
    def _onCliUpdated(self):
        self.function(function_name='updateRootSet',
                      args=self.cli.root.getPayload())
