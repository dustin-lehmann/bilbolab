import dataclasses
from typing import List, Optional, Union

from numpy.matlib import empty

from core.utils.logging_utils import Logger
import robot.lowlevel.stm32_addresses as addresses
from robot.communication.bilbo_communication import BILBO_Communication
from robot.lowlevel.stm32_control import *

import ctypes

class PositionControlInput(ctypes.LittleEndianStructure):
    _fields_ = [("forward", ctypes.c_float),
                ("angle", ctypes.c_float)]
    
@dataclasses.dataclass
class Waypoint:
    x: float = 0.0
    y: float = 0.0


class BilboPositionControl:
    waypoints: List[Waypoint]
    current_waypoint: Optional[Waypoint]

    def __init__(self, comm: BILBO_Communication, logger: Optional[Logger] = None):
        self._comm = comm


        self.waypoints = []
        self.current_waypoint = None
        self.logger = logger if logger else Logger("PositionControl")
        self.logger.setLevel("DEBUG")

    def update(self):
        ...

    def setWaypoints(self, waypoints: Union[dict, list]):
        #bekommt Zielkoordinaten als dict oder list --> sendet [x, drehwinkel] an Stm
         if not isinstance(waypoints, (list)) and len(waypoints) != 2:
             raise ValueError("waypoints must be a dict or a list of dicts")
         new_waypoint = Waypoint(waypoints[0], waypoints[1])
         self.waypoints.append(new_waypoint)

         self.logger.info(f"Received {len(self.waypoints)} waypoints")
         self.current_waypoint = new_waypoint
         data = {
            'u_1': float(self.current_waypoint.x),
            'u_2': float(self.current_waypoint.y)
        }
         self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_POSITION,  # <- richtige Adresse!
            data=data,
            input_type=bilbo_control_position_input_t
    )

    def setConfig(self, PosConfig: list[float]):
        if len(PosConfig) != 8 or not all(isinstance(p, float) for p in PosConfig):
            raise ValueError("Pos_Config must be a list of 8 floats")

        self.logger.info(f"Received: {PosConfig}")
        #self.logger.debug(bilbo_control_position_input_t)
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_POSITION_CONFIG,
            data=PosConfig,
            input_type=ctypes.c_float * 8
        )

    def setKPos(self, K_Pos:list[float]):
        if len(K_Pos) != 16 or not all(isinstance(k, float) for k in K_Pos):
            raise ValueError("K_Pos must be a list of 16 floats")

        self.logger.info(f"Received: {K_Pos}")
        #self.logger.debug(bilbo_control_position_gain_t)
        self._comm.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_ControlAddresses.ADDRESS_CONTROL_SET_K_POS,
            data=K_Pos,
            input_type=ctypes.c_float * 16
        )