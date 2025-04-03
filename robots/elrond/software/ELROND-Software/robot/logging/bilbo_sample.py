import dataclasses

# === OWN PACKAGES =====================================================================================================
from robot.control.bilbo_control import TWIPR_Control_Sample
from robot.estimation.bilbo_estimation import TWIPR_Estimation_Sample
from robot.drive.bilbo_drive import TWIPR_Drive_Sample
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from robot.sensors.bilbo_sensors import TWIPR_Sensors_Sample


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Sample_General:
    id: str = ''
    status: str = ''
    configuration: str = ''
    time: float = 0.0
    time_global: float = 0.0
    tick: int = 0
    sample_time: float = 0.0
    sample_time_ll: float = 0.0


# ======================================================================================================================
@dataclasses.dataclass(frozen=False)
class BILBO_Sample:
    general: BILBO_Sample_General = dataclasses.field(default_factory=BILBO_Sample_General)
    control: TWIPR_Control_Sample = dataclasses.field(default_factory=TWIPR_Control_Sample)
    estimation: TWIPR_Estimation_Sample = dataclasses.field(default_factory=TWIPR_Estimation_Sample)
    drive: TWIPR_Drive_Sample = dataclasses.field(default_factory=TWIPR_Drive_Sample)
    sensors: TWIPR_Sensors_Sample = dataclasses.field(default_factory=TWIPR_Sensors_Sample)
    lowlevel: BILBO_LL_Sample = dataclasses.field(default_factory=BILBO_LL_Sample)
