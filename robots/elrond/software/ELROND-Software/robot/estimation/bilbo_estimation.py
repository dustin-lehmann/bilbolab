import ctypes
import dataclasses
import enum

import robot.lowlevel.stm32_addresses as addresses
from robot.communication.bilbo_communication import BILBO_Communication
from robot.hardware import get_hardware_definition
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from utils.logging_utils import Logger


@dataclasses.dataclass
class TWIPR_Estimation_State:
    x: float = 0.0
    y: float = 0.0
    v: float = 0.0
    theta: float = 0.0
    theta_dot: float = 0.0
    psi: float = 0.0
    psi_dot: float = 0.0


class TWIPR_Estimation_Status(enum.IntEnum):
    ERROR = 0,
    NORMAL = 1,


class TWIPR_Estimation_Mode(enum.IntEnum):
    TWIPR_ESTIMATION_MODE_VEL = 0,
    TWIPR_ESTIMATION_MODE_POS = 1


@dataclasses.dataclass(frozen=True)
class TWIPR_Estimation_Sample:
    status: TWIPR_Estimation_Status = TWIPR_Estimation_Status.ERROR
    state: TWIPR_Estimation_State = dataclasses.field(default_factory=TWIPR_Estimation_State)
    mode: TWIPR_Estimation_Mode = TWIPR_Estimation_Mode.TWIPR_ESTIMATION_MODE_VEL


# ======================================================================================================================

class BILBO_Estimation:
    _comm: BILBO_Communication

    state: TWIPR_Estimation_State
    status: TWIPR_Estimation_Status

    mode: TWIPR_Estimation_Mode

    def __init__(self, comm: BILBO_Communication):
        self._comm = comm

        self.state = TWIPR_Estimation_State()
        self.status = TWIPR_Estimation_Status.NORMAL
        self.mode = TWIPR_Estimation_Mode.TWIPR_ESTIMATION_MODE_VEL
        self._comm.callbacks.rx_stm32_sample.register(self._onSample)

        self.logger = Logger('Estimation')
        self.logger.setLevel('DEBUG')

    # ==================================================================================================================
    def init(self):
        hardware_definition = get_hardware_definition()
        theta_offset = hardware_definition.get('settings', {}).get('theta_offset', 0.0)
        self.setThetaOffset(theta_offset)

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> TWIPR_Estimation_Sample:
        # sample = TWIPR_Estimation_Sample(
        #     mode=self.mode,
        #     status=self.status,
        #     state=self.state
        # )
        sample = {
            'mode': self.mode,
            'status': self.status,
            'state': dataclasses.asdict(self.state)
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def setThetaOffset(self, offset: float):
        self.logger.info(f'Setting theta offset to {offset}')
        success = self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_EstimationAddresses.SET_THETA_OFFSET,
            data=offset,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool
        )

        if not success:
            self.logger.error('Could not set theta offset')

        # self._comm.serial.executeFunction(
        #     module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
        #     address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_MODE,
        #     data=mode.value,
        #     input_type=ctypes.c_uint8
        # )

    # ==================================================================================================================
    def _update(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: BILBO_LL_Sample, *args, **kwargs):
        self.state.v = sample.estimation.state.v
        self.state.theta = sample.estimation.state.theta
        self.state.theta_dot = sample.estimation.state.theta_dot
        self.state.psi = sample.estimation.state.psi
        self.state.psi_dot = sample.estimation.state.psi_dot

    # ------------------------------------------------------------------------------------------------------------------
    def _readState_LL(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
