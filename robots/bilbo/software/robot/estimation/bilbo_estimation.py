import ctypes
import dataclasses
import enum

import numpy as np

import robot.lowlevel.stm32_addresses as addresses
from robot.bilbo_common import BILBO_Common
from robot.bilbo_definitions import BILBO_DynamicState, BILBO_ConfigurationState
from robot.communication.bilbo_communication import BILBO_Communication
from robot.estimation.optitrack_tracker import BILBO_OptiTrackListener
from robot.lowlevel.stm32_control import bilbo_position_state_t
from robot.lowlevel.stm32_sample import (
    BILBO_LL_Sample,
    velocity_lowpass_filter_config_t,
    VelocityLowpassFilterConfig,
    theta_dot_lowpass_filter_config_t,
    ThetaDotLowpassFilterConfig,
    psi_dot_lowpass_filter_config_t,
    PsiDotLowpassFilterConfig,
    position_ekf_config_t,
    PositionEkfConfig,
    bilbo_estimation_config_t,
    EstimationConfig,
)
from core.utils.logging_utils import Logger


@dataclasses.dataclass
class BILBO_TrackerSettings:
    enabled: bool = True
    server: str = 'palantir.lan'


class BILBO_Estimation_Status(enum.IntEnum):
    ERROR = 0,
    NORMAL = 1,


@dataclasses.dataclass(frozen=True)
class BILBO_Estimation_Sample:
    status: BILBO_Estimation_Status = dataclasses.field(default=BILBO_Estimation_Status.NORMAL)
    state: BILBO_DynamicState = dataclasses.field(default_factory=BILBO_DynamicState)
    state_optitrack: BILBO_ConfigurationState = dataclasses.field(default_factory=BILBO_ConfigurationState)
    static: bool = False
    is_dead_reckoning: bool = True


@dataclasses.dataclass(slots=True)
class StaticCheckerConfig:
    # Thresholds
    upright_threshold_rad: float = float(np.deg2rad(0.15))  # |theta| <= this
    static_threshold_mps: float = 0.02  # |v|     <= this

    # Horizon / robustness
    time_window_s: float = 2.0
    allowed_outlier_fraction: float = 0.10  # ignore worst 10%
    min_samples: int = 8  # need at least this many samples

    # Update period on robot (your _update() is every 100 ms)
    dt_s: float = 0.1


class StaticChecker:
    """
    Efficient rolling-window checker:
      - feeds one (theta, v) per update
      - returns True if, over the last window, the 'robust max' of |theta| and |v|
        is within thresholds, ignoring allowed_outlier_fraction worst spikes.
    """

    __slots__ = (
        "config",
        "_N",
        "_abs_theta",
        "_abs_v",
        "_tmp_theta",
        "_tmp_v",
        "_idx",
        "_count",
        "_keep",
    )

    def __init__(self, config: StaticCheckerConfig | None = None):
        if config is None:
            config = StaticCheckerConfig()
        self.config = config

        # window length in samples
        N = int(np.ceil(float(config.time_window_s) / float(config.dt_s)))
        self._N = max(1, N)

        # ring buffers (absolute values only)
        self._abs_theta = np.empty(self._N, dtype=np.float32)
        self._abs_v = np.empty(self._N, dtype=np.float32)

        # temp arrays to build "window view" without allocations
        self._tmp_theta = np.empty(self._N, dtype=np.float32)
        self._tmp_v = np.empty(self._N, dtype=np.float32)

        self._idx = 0
        self._count = 0

        # number of samples to keep after trimming outliers
        # robust_max = kth order statistic of abs values (k = keep-1)
        self._recompute_keep()

    def _recompute_keep(self) -> None:
        frac = float(self.config.allowed_outlier_fraction)
        frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)
        keep = int(np.floor(self._N * (1.0 - frac)))
        self._keep = max(1, min(keep, self._N))

    def reset(self) -> None:
        self._idx = 0
        self._count = 0

    def update(self, theta: float, v: float) -> bool:
        """
        Push newest sample into the horizon and return "static now?".
        """
        # fast absolute conversion; keep float32 in buffers
        self._abs_theta[self._idx] = np.float32(abs(float(theta)))
        self._abs_v[self._idx] = np.float32(abs(float(v)))

        self._idx += 1
        if self._idx >= self._N:
            self._idx = 0

        if self._count < self._N:
            self._count += 1

        # require enough samples in the current horizon
        if self._count < int(self.config.min_samples):
            return False

        # Build the window in chronological order into temp arrays:
        # oldest .. newest, by copying two slices from ring buffer.
        # idx points to the NEXT write position => it's the oldest element.
        start = self._idx
        n = self._count

        if n == self._N:
            # full window
            # copy [start:N) then [0:start)
            k1 = self._N - start
            self._tmp_theta[:k1] = self._abs_theta[start:]
            self._tmp_theta[k1:] = self._abs_theta[:start]
            self._tmp_v[:k1] = self._abs_v[start:]
            self._tmp_v[k1:] = self._abs_v[:start]
            view_theta = self._tmp_theta
            view_v = self._tmp_v
            n_view = self._N
        else:
            # not full yet: ring order is [0:n)
            # oldest is at 0, newest at n-1 (since we haven't wrapped)
            self._tmp_theta[:n] = self._abs_theta[:n]
            self._tmp_v[:n] = self._abs_v[:n]
            view_theta = self._tmp_theta[:n]
            view_v = self._tmp_v[:n]
            n_view = n

        # Determine trimmed robust max using np.partition:
        # robust_max = kth smallest of abs-values, where k = keep-1 after trimming.
        frac = float(self.config.allowed_outlier_fraction)
        frac = 0.0 if frac < 0.0 else (1.0 if frac > 1.0 else frac)
        keep = int(np.floor(n_view * (1.0 - frac)))
        keep = max(1, min(keep, n_view))
        k = keep - 1

        # np.partition mutates the array; operate on temp views (safe).
        theta_k = float(np.partition(view_theta, k)[k])
        v_k = float(np.partition(view_v, k)[k])

        return (theta_k <= float(self.config.upright_threshold_rad)) and \
            (v_k <= float(self.config.static_threshold_mps))


# ======================================================================================================================
class BILBO_Estimation:
    _comm: BILBO_Communication

    state: BILBO_DynamicState
    status: BILBO_Estimation_Status
    tracker: BILBO_OptiTrackListener

    static: bool = False
    is_dead_reckoning: bool = True
    tracker_connected: bool = False
    _dead_reckoning_enabled: bool = True  # Config setting for dead-reckoning
    _tracker_updates_enabled: bool = True  # Whether to send tracker updates to lowlevel

    def __init__(self, common: BILBO_Common, comm: BILBO_Communication,
                 tracker_settings: BILBO_TrackerSettings | None = None):
        self._comm = comm
        self.common = common
        self.state = BILBO_DynamicState()

        self.tracker_settings = tracker_settings or BILBO_TrackerSettings()

        if self.tracker_settings.enabled:
            self.tracker = BILBO_OptiTrackListener(common=self.common, server_address=self.tracker_settings.server)
            self.tracker.callbacks.sample.register(self._on_tracker_sample_callback)
        else:
            self.tracker = None
        self.static_checker = StaticChecker()
        self.status = BILBO_Estimation_Status.NORMAL
        self.is_dead_reckoning = True
        self._dead_reckoning_enabled = True
        self._tracker_updates_enabled = True
        self._comm.events.rx_stm32_sample.on(self._onSample)

        self.logger = Logger('Estimation')
        self.logger.setLevel('INFO')

        # Register WiFi commands
        self._register_wifi_commands()

    # ==================================================================================================================
    def init(self):
        theta_offset = self.common.config.model.theta_offset
        self.setThetaOffset(theta_offset)

        # Set dead-reckoning enable from config
        enable_dead_reckoning = self.common.config.estimation.enable_dead_reckoning
        self._dead_reckoning_enabled = enable_dead_reckoning
        self.set_dead_reckoning_enabled(enable_dead_reckoning)
        self.reset()
        if self.tracker is not None:
            self.tracker.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if self.tracker is not None:
            self.tracker.start()

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> BILBO_Estimation_Sample | dict:
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_sample_callback(self, sample: BILBO_ConfigurationState):

        self.common.tracker_connected = True
        self.tracker_connected = True

        # Skip sending updates to lowlevel if tracker updates are disabled
        if not self._tracker_updates_enabled:
            return

        data = {
            'x': sample.x,
            'y': sample.y,
            'psi': sample.psi,
        }

        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_POSITION_UPDATE,
            data=data,
            input_type=bilbo_position_state_t,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        tracker_state = self.tracker.get_state() if self.tracker is not None else None

        if tracker_state is None:
            tracker_state = BILBO_ConfigurationState()

        tracker_state = dataclasses.asdict(tracker_state)

        sample = {
            'status': self.status,
            'state': dataclasses.asdict(self.state),
            'state_optitrack': tracker_state,
            'static': self.static,
            'is_dead_reckoning': self.is_dead_reckoning
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def setThetaOffset(self, offset: float):
        self.logger.info(f'Setting theta offset to {np.rad2deg(offset):.2f} deg')
        success = self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_THETA_OFFSET,
            data=offset,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool
        )

        if not success:
            self.logger.error('Could not set theta offset')

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        """Reset the lowlevel estimation (EKF, filters, position state)."""
        self.logger.info('Resetting lowlevel estimation')
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.RESET,
            data=None,
            input_type=None,
            output_type=None
        )
        self.is_dead_reckoning = True

    # ------------------------------------------------------------------------------------------------------------------
    def get_velocity_lpf_config(self) -> VelocityLowpassFilterConfig | None:
        """Get the velocity low-pass filter configuration from the lowlevel."""
        result = self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.GET_VELOCITY_LPF,
            data=None,
            input_type=None,
            output_type=velocity_lowpass_filter_config_t
        )
        if result is None:
            self.logger.error('Could not get velocity LPF config')
            return None
        return VelocityLowpassFilterConfig(
            enable=result.enable,
            cutoff_hz=result.cutoff_hz,
            reset_on_start=result.reset_on_start
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_lpf_config(self, config: VelocityLowpassFilterConfig):
        """Set the velocity low-pass filter configuration on the lowlevel."""
        self.logger.info(f'Setting velocity LPF: enable={config.enable}, cutoff_hz={config.cutoff_hz:.1f}')
        data = {
            'enable': config.enable,
            'cutoff_hz': config.cutoff_hz,
            'reset_on_start': config.reset_on_start,
        }
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_VELOCITY_LPF,
            data=data,
            input_type=velocity_lowpass_filter_config_t,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def get_psi_dot_lpf_config(self) -> PsiDotLowpassFilterConfig | None:
        """Get the psi_dot low-pass filter configuration from the lowlevel."""
        result = self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.GET_PSIDOT_LPF,
            data=None,
            input_type=None,
            output_type=psi_dot_lowpass_filter_config_t
        )
        if result is None:
            self.logger.error('Could not get psi_dot LPF config')
            return None
        return PsiDotLowpassFilterConfig(
            enable=result.enable,
            cutoff_hz=result.cutoff_hz,
            reset_on_start=result.reset_on_start
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_psi_dot_lpf_config(self, config: PsiDotLowpassFilterConfig):
        """Set the psi_dot low-pass filter configuration on the lowlevel."""
        self.logger.info(f'Setting psi_dot LPF: enable={config.enable}, cutoff_hz={config.cutoff_hz:.1f}')
        data = {
            'enable': config.enable,
            'cutoff_hz': config.cutoff_hz,
            'reset_on_start': config.reset_on_start,
        }
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_PSIDOT_LPF,
            data=data,
            input_type=psi_dot_lowpass_filter_config_t,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def get_theta_dot_lpf_config(self) -> ThetaDotLowpassFilterConfig | None:
        """Get the theta_dot low-pass filter configuration from the lowlevel."""
        result = self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.GET_THETA_DOT_LPF,
            data=None,
            input_type=None,
            output_type=theta_dot_lowpass_filter_config_t
        )
        if result is None:
            self.logger.error('Could not get theta_dot LPF config')
            return None
        return ThetaDotLowpassFilterConfig(
            enable=result.enable,
            cutoff_hz=result.cutoff_hz,
            reset_on_start=result.reset_on_start
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_theta_dot_lpf_config(self, config: ThetaDotLowpassFilterConfig):
        """Set the theta_dot low-pass filter configuration on the lowlevel."""
        self.logger.info(f'Setting theta_dot LPF: enable={config.enable}, cutoff_hz={config.cutoff_hz:.1f}')
        data = {
            'enable': config.enable,
            'cutoff_hz': config.cutoff_hz,
            'reset_on_start': config.reset_on_start,
        }
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_THETA_DOT_LPF,
            data=data,
            input_type=theta_dot_lowpass_filter_config_t,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_dead_reckoning_enabled(self, enable: bool):
        """Enable or disable dead-reckoning EKF on the lowlevel."""
        self.logger.info(f'Setting dead-reckoning EKF enable={enable}')
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_DEAD_RECKONING_ENABLE,
            data=enable,
            input_type=ctypes.c_bool,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> EstimationConfig | None:
        """Get the full estimation configuration from the lowlevel."""
        result = self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.GET_CONFIG,
            data=None,
            input_type=None,
            output_type=bilbo_estimation_config_t
        )
        if result is None:
            self.logger.error('Could not get estimation config')
            return None
        return EstimationConfig(
            velocity_filter_config=VelocityLowpassFilterConfig(
                enable=result.velocity_filter_config.enable,
                cutoff_hz=result.velocity_filter_config.cutoff_hz,
                reset_on_start=result.velocity_filter_config.reset_on_start,
            ),
            theta_dot_filter_config=ThetaDotLowpassFilterConfig(
                enable=result.theta_dot_filter_config.enable,
                cutoff_hz=result.theta_dot_filter_config.cutoff_hz,
                reset_on_start=result.theta_dot_filter_config.reset_on_start,
            ),
            psi_dot_filter_config=PsiDotLowpassFilterConfig(
                enable=result.psi_dot_filter_config.enable,
                cutoff_hz=result.psi_dot_filter_config.cutoff_hz,
                reset_on_start=result.psi_dot_filter_config.reset_on_start,
            ),
            position_ekf_config=PositionEkfConfig(
                enable=result.position_ekf_config.enable,
                std_dev_position=result.position_ekf_config.std_dev_position,
                std_dev_psi=result.position_ekf_config.std_dev_psi,
                sigma_v_base=result.position_ekf_config.sigma_v_base,
                sigma_v_scale=result.position_ekf_config.sigma_v_scale,
                sigma_psi_dot_base=result.position_ekf_config.sigma_psi_dot_base,
                sigma_psi_dot_scale=result.position_ekf_config.sigma_psi_dot_scale,
                min_position_variance=result.position_ekf_config.min_position_variance,
                min_psi_variance=result.position_ekf_config.min_psi_variance,
                dead_reckoning_timeout=result.position_ekf_config.dead_reckoning_timeout,
            ),
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_config(self, config: EstimationConfig):
        """Set the full estimation configuration on the lowlevel."""
        self.logger.info(f'Setting estimation config')
        data = {
            'velocity_filter_config': {
                'enable': config.velocity_filter_config.enable,
                'cutoff_hz': config.velocity_filter_config.cutoff_hz,
                'reset_on_start': config.velocity_filter_config.reset_on_start,
            },
            'theta_dot_filter_config': {
                'enable': config.theta_dot_filter_config.enable,
                'cutoff_hz': config.theta_dot_filter_config.cutoff_hz,
                'reset_on_start': config.theta_dot_filter_config.reset_on_start,
            },
            'psi_dot_filter_config': {
                'enable': config.psi_dot_filter_config.enable,
                'cutoff_hz': config.psi_dot_filter_config.cutoff_hz,
                'reset_on_start': config.psi_dot_filter_config.reset_on_start,
            },
            'position_ekf_config': {
                'enable': config.position_ekf_config.enable,
                'std_dev_position': config.position_ekf_config.std_dev_position,
                'std_dev_psi': config.position_ekf_config.std_dev_psi,
                'sigma_v_base': config.position_ekf_config.sigma_v_base,
                'sigma_v_scale': config.position_ekf_config.sigma_v_scale,
                'sigma_psi_dot_base': config.position_ekf_config.sigma_psi_dot_base,
                'sigma_psi_dot_scale': config.position_ekf_config.sigma_psi_dot_scale,
                'min_position_variance': config.position_ekf_config.min_position_variance,
                'min_psi_variance': config.position_ekf_config.min_psi_variance,
                'dead_reckoning_timeout': config.position_ekf_config.dead_reckoning_timeout,
            },
        }
        self._comm.serial.executeFunction(
            module=addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.BILBO_EstimationAddresses.SET_CONFIG,
            data=data,
            input_type=bilbo_estimation_config_t,
            output_type=None
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_origin(self, origin_config: 'BILBO_OriginConfig | None'):
        """Update the OptiTrack origin used for coordinate transformation.

        If the tracker is running, this replaces the tracked origin (or removes it if None).
        """
        if self.tracker is None:
            self.logger.warning('Cannot set origin: tracker is not enabled')
            return

        from robot.estimation.optitrack_tracker import TrackedOrigin

        if origin_config is not None:
            prev_id = self.tracker.tracked_origin.id if self.tracker.tracked_origin else None
            if prev_id and prev_id != origin_config.id:
                self.logger.info(f'Switching OptiTrack origin: {prev_id} -> {origin_config.id}')
            else:
                self.logger.info(f'Setting OptiTrack origin to \'{origin_config.id}\'')
            new_origin = TrackedOrigin(id=origin_config.id, definition=origin_config)
            self.tracker.tracked_origin = new_origin
            if self.tracker.tracked_object is not None:
                self.tracker.tracked_object.origin = new_origin
        else:
            self.logger.info('Clearing origin')
            self.tracker.tracked_origin = None
            if self.tracker.tracked_object is not None:
                self.tracker.tracked_object.origin = None

    # ==================================================================================================================
    def update(self):
        # This gets called every 100ms
        # Do the static check
        self.static = self.static_checker.update(self.state.theta, self.state.v)

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: BILBO_LL_Sample, *args, **kwargs):
        self.state.x = sample.estimation.state.x
        self.state.y = sample.estimation.state.y
        self.state.v = sample.estimation.state.v
        self.state.theta = sample.estimation.state.theta
        self.state.theta_dot = sample.estimation.state.theta_dot
        self.state.psi = sample.estimation.state.psi
        self.state.psi_dot = sample.estimation.state.psi_dot
        self.is_dead_reckoning = sample.estimation.is_dead_reckoning

    # ------------------------------------------------------------------------------------------------------------------
    def _readState_LL(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def get_dead_reckoning_enabled(self) -> bool:
        """Get the current dead-reckoning enabled state."""
        return self._dead_reckoning_enabled

    # ------------------------------------------------------------------------------------------------------------------
    def get_tracker_updates_enabled(self) -> bool:
        """Get whether tracker updates are being sent to lowlevel."""
        return self._tracker_updates_enabled

    # ------------------------------------------------------------------------------------------------------------------
    def set_tracker_updates_enabled(self, enable: bool):
        """Enable or disable sending tracker updates to lowlevel."""
        self.logger.info(f'Setting tracker updates enabled={enable}')
        self._tracker_updates_enabled = enable

    # ------------------------------------------------------------------------------------------------------------------
    def _register_wifi_commands(self):
        """Register WiFi commands for estimation module."""
        self._comm.wifi.newCommand(
            identifier='get_dead_reckoning_enabled',
            function=self.get_dead_reckoning_enabled,
            arguments=[],
            description='Gets the dead-reckoning enabled state'
        )

        self._comm.wifi.newCommand(
            identifier='set_dead_reckoning_enabled',
            function=self._set_dead_reckoning_enabled_command,
            arguments=['enable'],
            description='Sets the dead-reckoning enabled state'
        )

        self._comm.wifi.newCommand(
            identifier='get_tracker_updates_enabled',
            function=self.get_tracker_updates_enabled,
            arguments=[],
            description='Gets whether tracker updates are sent to lowlevel'
        )

        self._comm.wifi.newCommand(
            identifier='set_tracker_updates_enabled',
            function=self._set_tracker_updates_enabled_command,
            arguments=['enable'],
            description='Sets whether tracker updates are sent to lowlevel'
        )

        self._comm.wifi.newCommand(
            identifier='reset_estimation',
            function=self.reset,
            arguments=[],
            description='Resets the lowlevel estimation (EKF, filters, position state)'
        )

        self._comm.wifi.newCommand(
            identifier='get_estimation_config',
            function=self.get_config,
            arguments=[],
            description='Gets the full estimation configuration from lowlevel'
        )

        self._comm.wifi.newCommand(
            identifier='set_estimation_config',
            function=self.set_config,
            arguments=['config'],
            description='Sets the full estimation configuration on lowlevel'
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _set_dead_reckoning_enabled_command(self, enable: bool):
        """WiFi command handler to set dead-reckoning enabled state."""
        self._dead_reckoning_enabled = enable
        self.set_dead_reckoning_enabled(enable)
        return self._dead_reckoning_enabled

    # ------------------------------------------------------------------------------------------------------------------
    def _set_tracker_updates_enabled_command(self, enable: bool):
        """WiFi command handler to set tracker updates enabled state."""
        self.set_tracker_updates_enabled(enable)
        return self._tracker_updates_enabled

    # ------------------------------------------------------------------------------------------------------------------
