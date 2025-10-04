import time

import drivers.lowlevel.stm32_addresses as addresses

from exo_skeleton import Exo_Skeleton
from utils.logging_utils import setLoggerLevel, Logger

setLoggerLevel('wifi', 'ERROR')

logger = Logger('main')
logger.setLevel('DEBUG')


def main():

    # Set up exoskeleton
    exo = Exo_Skeleton()
    time.sleep(1)
    #exo.exoSetMode(addresses.EXO_mab_motor_mode_t.MAB_MOTOR_MODE_POS_PID)
    #exo.exoStartMotor()
    #exo.exoSetTargetPosition(0.0)
    #time.sleep(3)
    #exo.exoSetTargetPosition(6.2)
    #time.sleep(3)
    #exo.exoSetTargetPosition(0.0)
    #time.sleep(3)
    #exo.exoSetTargetPosition(-6.2)
    #time.sleep(3)
    #exo.exoSetMode(addresses.EXO_mab_motor_mode_t.MAB_MOTOR_MODE_IMPEDANCE)
    #exo.exoSetImpedanceParams(0.1, 0.0)

    while True:
        cmd = input("Command: \n")
        cmds = cmd.split(" ")
        if(cmds[0] == "torque"):
            exo.exoSetMode(addresses.EXO_mab_motor_mode_t.MAB_MOTOR_MODE_RAW_TORQUE)
            exo.exoSetTorque(float(cmds[1]))
        elif(cmds[0] == "position"):
            exo.exoSetMode(addresses.EXO_mab_motor_mode_t.MAB_MOTOR_MODE_POS_PID)
            exo.exoSetTargetPosition(float(cmds[1]))
        elif(cmds[0] == "stop"):
            exo.exoStopMotor()
        elif(cmds[0] == "start"):
            exo.exoStartMotor()
        elif(cmds[0] == "impedance"):
            exo.exoSetMode(addresses.EXO_mab_motor_mode_t.MAB_MOTOR_MODE_IMPEDANCE)
            exo.exoSetImpedanceParams(float(cmds[1]), float(cmds[2]))
            if len(cmds) > 3:
                if(cmds[3] == "pos"):
                    exo.exoSetTargetPosition(float(cmds[4]))
                elif(cmds[3] == "vel"):            
                    exo.exoSetTargetVelocity(float(cmds[4]))
                                         
        else:
            logger.warning(f"Unknow Command: {cmd}")



if __name__ == '__main__':
    main()