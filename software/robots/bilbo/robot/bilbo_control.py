import dataclasses

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict_auto
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_ControlConfig, VelocityControl_Config, \
    PID_Config, VelocityConfig, Feedforward_Config, TIC_Config, VIC_Config, PSI_Config, PositionControl_Config
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals


@event_definition
class BILBO_Control_Events:
    mode_changed: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    configuration_changed: Event
    tic_mode_changed: Event
    vic_mode_changed: Event
    psi_mode_changed: Event
    error: Event


@callback_definition
class BILBO_Control_Callbacks:
    mode_changed: CallbackContainer
    configuration_changed: CallbackContainer


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
                                    predicate=pred_flag_equals('container', 'control'))

        self.core.events.stream.on(callback=self._sampleStreamHandler)

    # ------------------------------------------------------------------------------------------------------------------
    def setControlMode(self, mode: int | BILBO_Control_Mode, *args, **kwargs):
        if isinstance(mode, int):
            mode = BILBO_Control_Mode(mode)

        self.logger.info(f"Robot {self.id}: Set Control Mode to {mode.name}")
        self.device.executeFunction(function_name='set_control_mode', arguments={'mode': mode})

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
        self.device.executeFunction('set_external_input_forward_turn',
                                    arguments={'forward': forward, 'turn': turn, 'normalized': True})

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_command(self, v, psi_dot):
        self.device.executeFunction('set_velocity',
                                    arguments={'forward': v, 'turn': psi_dot})

    # ------------------------------------------------------------------------------------------------------------------
    def nudge(self, distance: float = 0.2):
        """One-shot position nudge to free the robot from a wall. Works only in OFF
        mode and when the robot is lying over; the firmware picks the direction
        (away from the fall, from theta) and bounds the move so it cannot run away.
        distance is the travel magnitude in meters."""
        accepted = self.device.executeFunction('nudge', arguments={'distance': distance},
                                                return_type=bool, request_response=True, timeout=2)
        if accepted:
            self.logger.info(f"Robot {self.id}: nudge {distance} m accepted")
        else:
            self.logger.warning(
                f"Robot {self.id}: nudge rejected (needs OFF mode and the robot lying over)")
        return accepted

    # ------------------------------------------------------------------------------------------------------------------
    def get_velocity_control_config(self) -> VelocityControl_Config:
        v_config_dict = self.device.executeFunction('get_velocity_config_forward',
                                                    arguments=None,
                                                    return_type=dict,
                                                    request_response=True)
        v_config = from_dict_auto(VelocityConfig, v_config_dict)

        psi_dot_config_dict = self.device.executeFunction('get_velocity_config_turn',
                                                          arguments=None,
                                                          return_type=dict,
                                                          request_response=True)

        psi_dot_config = from_dict_auto(VelocityConfig, psi_dot_config_dict)

        velocity_config = VelocityControl_Config(
            v=v_config,
            psidot=psi_dot_config
        )

        return velocity_config

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_control_config_v(self, config: PID_Config):
        self.device.executeFunction('set_velocity_pid_config_forward',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_control_config_psi_dot(self, config: PID_Config):
        self.device.executeFunction('set_velocity_pid_config_turn',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_pid(self, P: float | None = None, I: float | None = None, D: float | None = None):
        # Get the current PID config
        pid_config = self.get_velocity_control_config().psidot.pid
        if P is not None: pid_config.Kp = P
        if I is not None: pid_config.Ki = I
        if D is not None: pid_config.Kd = D
        self.set_velocity_control_config_psi_dot(pid_config)

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_pid(self, P: float | None = None, I: float | None = None, D: float | None = None):
        # Get the current PID config
        pid_config = self.get_velocity_control_config().v.pid
        if P is not None: pid_config.Kp = P
        if I is not None: pid_config.Ki = I
        if D is not None: pid_config.Kd = D
        self.set_velocity_control_config_v(pid_config)

    # ------------------------------------------------------------------------------------------------------------------
    def load_default_control_config(self) -> BILBO_ControlConfig | None:
        """Load and apply default control config from the robot's default.yaml file."""
        self.logger.info(f"Robot {self.id}: Loading default control config")
        config = self.device.executeFunction(
            function_name='load_default_control_config',
            arguments=None,
            return_type=dict,
            request_response=True
        )
        if config is None:
            self.logger.error(f"Could not load default control config for robot {self.id}")
            return None
        return from_dict_auto(BILBO_ControlConfig, config)

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_ff_config_v(self, config: Feedforward_Config):
        self.device.executeFunction('set_velocity_ff_config_forward',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_ff_config_psi_dot(self, config: Feedforward_Config):
        self.device.executeFunction('set_velocity_ff_config_turn',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_tic_config(self, config: TIC_Config):
        self.device.executeFunction('set_tic_config',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_vic_config(self, config: VIC_Config):
        self.device.executeFunction('set_vic_config',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_psi_config(self, config: PSI_Config):
        self.device.executeFunction('set_psi_config',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def enablePSI(self, state):
        if self.mode not in [BILBO_Control_Mode.BALANCING]:
            return
        self.device.executeFunction(function_name='enable_psi', arguments={
            'enable': state
        })

    # ------------------------------------------------------------------------------------------------------------------
    def set_psi_setpoint(self, psi: float):
        self.device.executeFunction(function_name='set_psi_setpoint', arguments={
            'psi': psi
        })

    # ------------------------------------------------------------------------------------------------------------------
    def set_general_config(self, max_wheel_torque: float, max_wheel_speed: float):
        self.device.executeFunction('set_general_config',
                                    arguments={'max_wheel_torque': max_wheel_torque,
                                               'max_wheel_speed': max_wheel_speed})

    # ------------------------------------------------------------------------------------------------------------------
    def set_statefeedback_gain(self, K: list):
        self.device.executeFunction('set_statefeedback_gain',
                                    arguments={'K': K})

    # ------------------------------------------------------------------------------------------------------------------
    def fall_down(self, direction: str = 'forward'):
        self.device.executeFunction('fall_down', arguments={'direction': direction})

    # ------------------------------------------------------------------------------------------------------------------
    def set_position_control_config(self, config: PositionControl_Config):
        self.device.executeFunction('set_position_control_config',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def readControlConfiguration(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def enableTIC(self, state):
        if self.mode not in [BILBO_Control_Mode.BALANCING, BILBO_Control_Mode.VELOCITY, BILBO_Control_Mode.POSITION]:
            return

        self.device.executeFunction(function_name='enable_tic', arguments={
            'enable': state
        })

    # # ------------------------------------------------------------------------------------------------------------------
    # def setWaypoints(self, waypoints):
    #     self.device.executeFunction(function_name='setWaypoints', arguments={
    #         'waypoints': waypoints
    #     })

    # ------------------------------------------------------------------------------------------------------------------
    def handleEventMessage(self, event_data, **kwargs):
        event_name = event_data.get('event', None)
        data = event_data.get('data', {}) or {}
        match event_name:
            case 'mode_change':
                self._handleModeChangeEvent(data)
            case 'configuration_change':
                self._handleConfigurationChangeEvent(data)
            case 'tic_change':
                self._handle_tic_change_event(data)
            case 'vic_change':
                self._handle_vic_change_event(data)
            case 'psi_change':
                self._handle_psi_change_event(data)
            case 'error':
                ...
            case _:
                self.core.logger.warning(f"Unknown control event message: {event_name}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleModeChangeEvent(self, message):
        self.callbacks.mode_changed.call(BILBO_Control_Mode(message['mode']))
        self.events.mode_changed.set(data=BILBO_Control_Mode(message['mode']))
        self.core.events.control_mode_changed.set(data=BILBO_Control_Mode(message['mode']))

    # ------------------------------------------------------------------------------------------------------------------
    def _handleConfigurationChangeEvent(self, data):
        self.callbacks.configuration_changed.call(data)
        self.events.configuration_changed.set(data)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_tic_change_event(self, data):
        self.logger.debug(f"TIC mode changed to {data['tic_enabled']}")
        tic_enabled = data['tic_enabled']
        self.events.tic_mode_changed.set(tic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_vic_change_event(self, data):
        self.logger.debug(f"VIC mode changed to {data['vic_enabled']}")
        vic_enabled = data['vic_enabled']
        self.events.vic_mode_changed.set(vic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_psi_change_event(self, data):
        self.logger.debug(f"PSI mode changed to {data['psi_enabled']}")
        psi_enabled = data['psi_enabled']
        self.events.psi_mode_changed.set(psi_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _sampleStreamHandler(self, sample: BILBO_Sample):
        new_mode = sample.control.mode
        if new_mode != self.mode:
            self.mode = new_mode
            self.events.mode_changed.set(data=new_mode)
            self.core.events.control_mode_changed.set(data=new_mode)
        else:
            self.mode = new_mode
