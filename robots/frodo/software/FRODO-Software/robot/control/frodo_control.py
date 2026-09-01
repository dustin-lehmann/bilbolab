import dataclasses
import enum
import queue
import threading
import time
from typing import Callable, Tuple, Optional

import math

from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.data import clamp
from core.utils.delayed_executor import setTimeout
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from robot.common import FRODO_Common
from robot.control.navigator import NavigatorSample, Navigator, NavigatorExecutionMode, MoveTo, TurnTo, \
    CoordinatedMoveTo, TimeWait, TimeRef, NavigatorStatus, MoveToRelative, RelativeStraightMove, RelativeTurn, \
    TurnToPoint, AbsoluteTimeWait, EventWait, NavigationElement, NavigatedObjectState, NavigatorSpeedControlMode
from robot.definitions import MAX_TRACK_SPEED
from robot.estimation.frodo_estimation import FRODO_DynamicState
from robot.frodo_core.frodo_core import FRODO_Core
from robot.frodo_core.lowlevel_definitions import motor_input_struct, FRODO_LL_ADDRESS_TABLE, FRODO_LL_Functions
from robot.communication.frodo_communication import FRODO_Communication


# ======================================================================================================================
class FRODO_ControlMode(enum.StrEnum):
    EXTERNAL = 'EXTERNAL'
    NAVIGATION = 'NAVIGATION'


@dataclasses.dataclass
class FRODO_Control_Input:
    left: float
    right: float


@dataclasses.dataclass
class FRODO_Control_Sample:
    mode: FRODO_ControlMode
    input: FRODO_Control_Input
    navigator: NavigatorSample


class FRODO_Control_Update_Mode(enum.StrEnum):
    SYNCHRONOUS = 'SYNCHRONOUS'  # Sets the actual speed only after calling update()
    ASYNCHRONOUS = 'ASYNCHRONOUS'  # Sets the actual speed immediately


# === FRODO CONTROL ====================================================================================================
class FRODO_Control:
    mode: FRODO_ControlMode = FRODO_ControlMode.EXTERNAL
    update_mode: FRODO_Control_Update_Mode = FRODO_Control_Update_Mode.SYNCHRONOUS
    navigator: Navigator
    _exit: bool = False

    input: FRODO_Control_Input

    # === INIT =========================================================================================================
    def __init__(self, common: FRODO_Common,
                 core: FRODO_Core,
                 communication: FRODO_Communication):

        self.logger = Logger("CONTROL", "DEBUG")
        self.core = core
        self.common = common
        self.communication = communication

        self.navigator = Navigator(
            mode=NavigatorExecutionMode.THREAD,
            speed_control_mode=NavigatorSpeedControlMode.TRACKS,
            speed_command_function=self._setTrackSpeedPrivate,
            state_fetch_function=self._navigator_state_fetch_function)

        self.navigator.events.element_finished.on(self._on_navigation_element_finished)
        self.navigator.events.element_started.on(self._on_navigation_element_started)
        self.navigator.events.element_skipped.on(self._on_navigation_element_skipped)
        self.navigator.events.element_timeout.on(self._on_navigation_element_timeout)
        self.navigator.events.element_error.on(self._on_navigation_element_error)

        self.input = FRODO_Control_Input(left=0.0, right=0.0)

        register_exit_callback(self.close, priority=2)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.navigator.start()
        self.logger.info("Starting FRODO Control")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        # Directly write zero to the lowlevel board: _setTrackSpeedPrivate() is a no-op in
        # EXTERNAL mode, and the SYNCHRONOUS setTrackSpeed() path depends on the main task loop
        # still being alive to flush self.input, which is not guaranteed during shutdown.
        self._setLowlevelTrackSpeed(0, 0)
        self.logger.info("Exit FRODO Control")

    # ------------------------------------------------------------------------------------------------------------------
    def setMode(self, mode: FRODO_ControlMode | str):
        if isinstance(mode, str):
            mode = FRODO_ControlMode(mode)
        if mode == FRODO_ControlMode.EXTERNAL:
            self.mode = FRODO_ControlMode.EXTERNAL
            self.logger.info("FRODO Control mode set to EXTERNAL")
        elif mode == FRODO_ControlMode.NAVIGATION:
            self.mode = FRODO_ControlMode.NAVIGATION
            self.logger.info("FRODO Control mode set to NAVIGATION")
        else:
            raise ValueError(f"Invalid mode: {mode}")

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        self._setLowlevelTrackSpeed(self.input.left, self.input.right)

    # ------------------------------------------------------------------------------------------------------------------
    def testNavigator(self):
        # movement1 = TurnToPoint(x=1.75, y=0.25)
        # movement2 = MoveTo(x=1.75, y=0.25)
        # movement1 = TurnToPoint(x=0.5, y=1)
        # movement2 = MoveTo(x=0.5, y=1)

        # movement1 = CoordinatedMoveTo(x=0.5, y=0.5)
        # movement2 = CoordinatedMoveTo(x=1.75, y=0.25)
        # movement3 = CoordinatedMoveTo(x=1.75, y=1.25)
        # movement4 = CoordinatedMoveTo(x=0.25, y=1.25)
        # movement1 = TurnTo(psi=1)
        # movement0 = MoveTo(x=0.25, y=1.15)
        # wait0 = TimeWait(duration=5.0)
        movement1 = MoveTo(x=0.5, y=0.5)
        wait1 = TimeWait(duration=5.0)
        movement2 = MoveTo(x=1, y=1)
        wait2 = TimeWait(duration=5.0)
        movement3 = MoveTo(x=1.75, y=1.25)
        wait3 = TimeWait(duration=5.0)
        movement4 = MoveTo(x=0.25, y=1.25)
        # self.navigator.addElement(movement0)
        # self.navigator.addElement(wait0)
        self.navigator.addElement(movement1)
        self.navigator.addElement(wait1)
        self.navigator.addElement(movement2)
        self.navigator.addElement(wait2)
        self.navigator.addElement(movement3)
        self.navigator.addElement(wait3)
        self.navigator.addElement(movement4)
        self.mode = FRODO_ControlMode.NAVIGATION
        self.navigator.startNavigation()

    # ------------------------------------------------------------------------------------------------------------------
    def setTrackSpeed(self, speed_left, speed_right):

        if self.mode == FRODO_ControlMode.NAVIGATION:
            # self.logger.warning("Setting speed while in NAVIGATION mode is not allowed")
            return

        self.input = FRODO_Control_Input(left=speed_left, right=speed_right)

        if self.update_mode == FRODO_Control_Update_Mode.ASYNCHRONOUS:
            self._setLowlevelTrackSpeed(speed_left, speed_right)

    # ------------------------------------------------------------------------------------------------------------------
    def setTrackSpeedNormalized(self, speed_left_normalized, speed_right_normalized):
        self.setTrackSpeed(speed_left_normalized * MAX_TRACK_SPEED,
                           speed_right_normalized * MAX_TRACK_SPEED)

    # ------------------------------------------------------------------------------------------------------------------
    def moveTo(self, x, y):
        self.input = FRODO_Control_Input(left=0.0, right=0.0)
        self.setMode(FRODO_ControlMode.NAVIGATION)
        self.navigator.addElement(MoveTo(x=x, y=y))
        if not self.navigator.status == NavigatorStatus.RUNNING:
            self.navigator.startNavigation()

    # ------------------------------------------------------------------------------------------------------------------
    def addMoveTo(self, x: float, y: float,
                  speed: float | None = None,
                  arrive_tolerance: float | None = None,
                  element_id: str | None = None,):
        el = MoveTo(id=element_id, x=x, y=y)
        if speed is not None:
            el.speed = speed
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addMoveToRelative(self, dx: float, dy: float,
                          speed: float | None = None,
                          arrive_tolerance: float | None = None):
        el = MoveToRelative(dx=dx, dy=dy)
        if speed is not None:
            el.speed = speed
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addRelativeStraightMove(self, distance: float,
                                speed: float | None = None,
                                arrive_tolerance: float | None = None):
        el = RelativeStraightMove(distance=distance)
        if speed is not None:
            el.speed = speed
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addTurnTo(self, psi: float, arrive_tolerance: float | None = None):
        el = TurnTo(psi=psi)
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addRelativeTurn(self, dpsi: float, arrive_tolerance: float | None = None):
        el = RelativeTurn(dpsi=dpsi)
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addTurnToPoint(self, x: float, y: float, arrive_tolerance: float | None = None):
        el = TurnToPoint(x=x, y=y)
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addTimeWait(self, duration: float, reference: str | TimeRef = TimeRef.PRIMITIVE):
        # accept "PRIMITIVE"/"EXPERIMENT" strings too for simple serialization
        if isinstance(reference, str):
            reference = TimeRef(reference)
        el = TimeWait(duration=duration, reference=reference)
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addAbsoluteTimeWait(self, unix_time: float):
        el = AbsoluteTimeWait(unix_time=unix_time)
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addEventWait(self, event: str):
        el = EventWait(event=event)
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def addCoordinatedMoveTo(self, x: float, y: float,
                             psi_end: float | None = None,
                             speed: float | None = None,
                             pre_rotate_tolerance: float | None = None,
                             arrive_tolerance: float | None = None,
                             final_heading_tolerance: float | None = None):
        el = CoordinatedMoveTo(x=x, y=y, psi_end=psi_end)
        if speed is not None:
            el.speed = speed
        if pre_rotate_tolerance is not None:
            el.pre_rotate_tolerance = pre_rotate_tolerance
        if arrive_tolerance is not None:
            el.arrive_tolerance = arrive_tolerance
        if final_heading_tolerance is not None:
            el.final_heading_tolerance = final_heading_tolerance
        self.navigator.addElement(el)

    # ------------------------------------------------------------------------------------------------------------------
    def clearNavigation(self):
        self.navigator.stopNavigation()
        self.navigator.clearQueue()

    # ------------------------------------------------------------------------------------------------------------------
    def stopNavigation(self):
        self.navigator.stopNavigation()
        self.setMode(FRODO_ControlMode.EXTERNAL)

    # ------------------------------------------------------------------------------------------------------------------
    def startNavigation(self):
        if self.mode == FRODO_ControlMode.EXTERNAL:
            self.setMode(FRODO_ControlMode.NAVIGATION)
        self.navigator.startNavigation()

    # ------------------------------------------------------------------------------------------------------------------
    def skip_element(self):
        self.navigator.skip_element()

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> FRODO_Control_Sample:
        sample = FRODO_Control_Sample(
            mode=self.mode,
            input=self.input,
            navigator=self.navigator.getSample()
        )

        return sample

    # === PRIVATE METHODS ==============================================================================================
    def _setTrackSpeedPrivate(self, speed_left, speed_right):
        """
        This can be used to give to the navigator and circumvents the blocked setSpeed() in navigation mode
        Args:
            speed_left: left track speed
            speed_right: right track speed

        Returns:

        """
        if self.mode == FRODO_ControlMode.EXTERNAL:
            # self.logger.warning("Navigator tries to set speed while in EXTERNAL mode")
            return

        self.input.left = speed_left
        self.input.right = speed_right
        self._setLowlevelTrackSpeed(speed_left, speed_right)

    # ------------------------------------------------------------------------------------------------------------------
    def _setLowlevelTrackSpeed(self, left, right):

        left_normalized = left / MAX_TRACK_SPEED
        right_normalized = right / MAX_TRACK_SPEED

        left_normalized = clamp(left_normalized, -1.0, 1.0)
        right_normalized = clamp(right_normalized, -1.0, 1.0)

        self._setLowlevelTrackSpeedNormalized(left_normalized, right_normalized)

    # ------------------------------------------------------------------------------------------------------------------
    def _setLowlevelTrackSpeedNormalized(self, left: float, right: float):
        input_struct = motor_input_struct(left=left, right=right)
        self.core.lowlevel.executeFunction(module=FRODO_LL_ADDRESS_TABLE,
                                           address=FRODO_LL_Functions.FRODO_LL_FUNCTION_SET_SPEED,
                                           data=input_struct,
                                           input_type=motor_input_struct)

    # ------------------------------------------------------------------------------------------------------------------
    def _navigator_state_fetch_function(self) -> NavigatedObjectState:
        state = self.common.getDynamicState()
        return NavigatedObjectState(
            x=state.x,
            y=state.y,
            psi=state.psi,
            v=state.v,
            psi_dot=state.psi_dot,
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_element_finished(self, element: NavigationElement, *args, **kwargs):
        self.logger.info(f"Navigation element finished: {element.id}")
        event = {
            "type": "finished",
            "data": {
                'element_id': element.id,
            }
        }
        self.communication.send_event(event_name='navigation', event_data=event)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_element_started(self, element: NavigationElement, *args, **kwargs):
        self.logger.info(f"Navigation element started: {element.id}")
        event = {
            "type": "started",
            "data": {
                'element_id': element.id,
            }
        }
        self.communication.send_event(event_name='navigation', event_data=event)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_element_skipped(self, element: NavigationElement, *args, **kwargs):
        self.logger.info(f"Navigation element skipped: {element.id}")
        event = {
            "type": "skipped",
            "data": {
                'element_id': element.id,
            }
        }
        self.communication.send_event(event_name='navigation', event_data=event)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_element_timeout(self, element: NavigationElement, *args, **kwargs):
        self.logger.info(f"Navigation element timeout: {element.id}")
        event = {
            "type": "timeout",
            "data": {
                'element_id': element.id,
            }
        }
        self.communication.send_event(event_name='navigation', event_data=event)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_element_error(self, element: NavigationElement, *args, **kwargs):
        self.logger.info(f"Navigation element error: {element.id}")
        event = {
            "type": "error",
            "data": {
                'element_id': element.id,
                'reason': 'unknown'
            }
        }
    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
