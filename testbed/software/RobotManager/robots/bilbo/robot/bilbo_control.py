from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict_auto
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_ControlConfig
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals


@event_definition
class BILBO_Control_Events:
    mode_changed: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    configuration_changed: Event
    tic_mode_changed: Event
    error: Event


@callback_definition
class BILBO_Control_Callbacks:
    mode_changed: CallbackContainer
    configuration_changed: CallbackContainer
    # error: CallbackContainer


# ======================================================================================================================
class BILBO_Control:
    mode: BILBO_Control_Mode | None

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core):
        self.id = core.id
        self.device = core.device
        self.logger = core.logger

        self.core = core
        self.events = BILBO_Control_Events()
        self.callbacks = BILBO_Control_Callbacks()

        self.mode = None

        self.device.events.event.on(callback=self.handleEventMessage,
                                    predicate=pred_flag_equals('event', 'control'))

        self.core.events.stream.on(callback=self._sampleStreamHandler)

    # ------------------------------------------------------------------------------------------------------------------
    def setControlMode(self, mode: int | BILBO_Control_Mode, *args, **kwargs):
        if isinstance(mode, int):
            mode = BILBO_Control_Mode(mode)

        self.logger.info(f"Robot {self.id}: Set Control Mode to {mode.name}")
        self.device.executeFunction(function_name='setControlMode', arguments={'mode': mode})

    # ------------------------------------------------------------------------------------------------------------------
    def get_control_config(self) -> BILBO_ControlConfig | None:
        config = self.device.executeFunction(function_name='get_control_config',
                                             arguments=None,
                                             return_type=dict,
                                             request_response=True)
        if config is None:
            self.logger.error(f"Could not read control configuration from robot {self.id}")

        config = from_dict_auto(BILBO_ControlConfig, config)
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedBalancingInput(self, forward, turn, *args, **kwargs):
        self.device.executeFunction('setNormalizedBalancingInput',
                                    arguments={'forward': forward, 'turn': turn})

    # ------------------------------------------------------------------------------------------------------------------
    def getControlState(self):
        ...

    def setStateFeedbackGain(self, gain: float):
        ...

    def setForwardPID(self, p, i, d):
        ...

    def setTurnPID(self, p, i, d):
        ...

    def readControlConfiguration(self):
        ...

    def enableTIC(self, state):
        self.device.executeFunction(function_name='enableTIC', arguments={
            'enable': state
        })

    def setWaypoints(self, waypoints):
        self.device.executeFunction(function_name='setPositionControlWaypoints', arguments={
            'waypoints': waypoints
        })

    def setStateFeedbackGainPos(self, KPos):
        # Waypoint als array [x, y] koordinate
        self.device.executeFunction(function_name='setPositionControlKPos', arguments={
            'K_Pos': KPos
        })

    def initKpos(self):
        K_Pos = [-0.35,-0.25,-0.35,-0.04,-0.04,-0.025,0.5,0.0,-0.35,-0.25,-0.35,-0.04, 0.04,0.025,0.5,0.0]

        self.device.executeFunction(function_name='setPositionControlKPos', arguments={'K_Pos': K_Pos})

    def setPosConfig(self, PosConfig):
        # Waypoint als array [x, y] koordinate
        self.device.executeFunction(function_name='setPositionConfig', arguments={
            'PosConfig': PosConfig
        })

    # ------------------------------------------------------------------------------------------------------------------
    def handleEventMessage(self, message):
        match message.data['event']:
            case 'mode_change':
                self._handleModeChangeEvent(message.data)
            case 'configuration_change':
                self._handleConfigurationChangeEvent(message.data)
            case 'tic_change':
                self._handle_tic_change_event(message.data)
            case 'error':
                ...
            case _:
                self.core.logger.warning(f"Unknown control event message: {message.data['event']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleModeChangeEvent(self, message):
        self.callbacks.mode_changed.call(BILBO_Control_Mode(message['mode']))
        self.events.mode_changed.set(data=BILBO_Control_Mode(message['mode']))

    # ------------------------------------------------------------------------------------------------------------------
    def _handleConfigurationChangeEvent(self, data):
        self.callbacks.configuration_changed.call(data['configuration'])
        self.events.configuration_changed.set(data['configuration'])

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_tic_change_event(self, data):
        tic_enabled = data['tic_enabled']
        self.events.tic_mode_changed.set(tic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _sampleStreamHandler(self, sample: BILBO_Sample):
        self.mode = sample.control.mode
