from core.communication.device_server import Device
from core.utils.events import pred_flag_equals
from core.utils.events import event_definition, Event, EventFlag
from core.utils.logging_utils import Logger
from robots.frodo.robot.frodo_definitions import FRODO_ControlMode, FRODO_Config


class FRODO_Control_Events:
    ...


@event_definition
class FRODO_Navigation_Events:
    started: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    finished: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    skipped: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    timeout: Event = Event(data_type=str, flags=EventFlag('id', str))
    aborted: Event = Event(data_type=str, flags=EventFlag('id', str))
    error: Event = Event(data_type=str, flags=EventFlag('id', str))


# === FRODO CONTROL ====================================================================================================
class FRODO_Control:
    mode: FRODO_ControlMode | None = None
    navigation_events: FRODO_Navigation_Events

    # === INIT =========================================================================================================
    def __init__(self, device: Device, information: FRODO_Config):
        self.device = device
        self.information = information
        self.logger = Logger(f"{self.information.id} Control")

        self.navigation_events = FRODO_Navigation_Events()
        self.device.events.event.on(self._on_navigation_event, predicate=pred_flag_equals('container', 'navigation'))

    # === METHODS ======================================================================================================
    def setSpeed(self, speed_left, speed_right):
        self.device.executeFunction(function_name='setSpeed',
                                    arguments={
                                        'speed_left': speed_left,
                                        'speed_right': speed_right
                                    })

    # ------------------------------------------------------------------------------------------------------------------
    def setSpeedNormalized(self, speed_left_normalized: float, speed_right_normalized: float):
        """Pass-through to robot-side setSpeedNormalized (expects values in [-1..1])."""
        self.device.executeFunction(function_name='setSpeedNormalized',
                                    arguments={
                                        'speed_left_normalized': speed_left_normalized,
                                        'speed_right_normalized': speed_right_normalized
                                    })

    # ------------------------------------------------------------------------------------------------------------------
    def setMode(self, mode: FRODO_ControlMode):
        """Switch control mode on the robot (EXTERNAL/NAVIGATION)."""
        success = self.device.executeFunction(function_name='setMode',
                                              arguments={'mode': mode.value},
                                              request_response=True)
        if success:
            self.mode = mode
        return success

    # ------------------------------------------------------------------------------------------------------------------
    def startNavigation(self):
        """Start the navigator on the robot (process queue)."""
        return self.device.executeFunction(function_name='startNavigation',
                                           arguments={},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def stopNavigation(self):
        """Stop the navigator and command zero speed."""
        return self.device.executeFunction(function_name='stopNavigation',
                                           arguments={},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def pauseNavigation(self):
        """Pause the navigator (robot will hold with zero speed)."""
        return self.device.executeFunction(function_name='pauseNavigation',
                                           arguments={},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def resumeNavigation(self):
        """Resume the navigator if it was paused."""
        return self.device.executeFunction(function_name='resumeNavigation',
                                           arguments={},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def clearNavigation(self):
        """Stop navigation and clear the queued elements."""
        return self.device.executeFunction(function_name='clearNavigation',
                                           arguments={},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def skip_element(self):
        return self.device.executeFunction(function_name='skip_element', arguments={}, request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def moveTo(self, x: float, y: float):
        """Enqueue a MoveTo(x, y) on the robot; robot starts nav if not running."""
        return self.device.executeFunction(function_name='moveTo',
                                           arguments={'x': x, 'y': y},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addMoveTo(self, x: float, y: float, element_id: str | None = None):
        return self.device.executeFunction(function_name='addMoveTo',
                                           arguments={'x': x, 'y': y, 'element_id': element_id},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addMoveToRelative(self, dx: float, dy: float):
        return self.device.executeFunction(function_name='addMoveToRelative',
                                           arguments={'dx': dx, 'dy': dy},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addRelativeStraightMove(self, distance: float):
        return self.device.executeFunction(function_name='addRelativeStraightMove',
                                           arguments={'distance': distance},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addTurnTo(self, psi: float):
        return self.device.executeFunction(function_name='addTurnTo',
                                           arguments={'psi': psi},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addRelativeTurn(self, dpsi: float):
        return self.device.executeFunction(function_name='addRelativeTurn',
                                           arguments={'dpsi': dpsi},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addTurnToPoint(self, x: float, y: float):
        return self.device.executeFunction(function_name='addTurnToPoint',
                                           arguments={'x': x, 'y': y},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addTimeWait(self, duration: float, reference: str = "PRIMITIVE"):
        return self.device.executeFunction(function_name='addTimeWait',
                                           arguments={'duration': duration, 'reference': reference},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addAbsoluteTimeWait(self, unix_time: float):
        return self.device.executeFunction(function_name='addAbsoluteTimeWait',
                                           arguments={'unix_time': unix_time},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addEventWait(self, event: str):
        return self.device.executeFunction(function_name='addEventWait',
                                           arguments={'event': event},
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def addCoordinatedMoveTo(self, x: float, y: float, psi_end: float | None = None):
        args = {'x': x, 'y': y}
        if psi_end is not None:
            args['psi_end'] = psi_end
        return self.device.executeFunction(function_name='addCoordinatedMoveTo',
                                           arguments=args,
                                           request_response=True)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_navigation_event(self, event_data, *args, **kwargs):
        self.logger.important(f"Navigation event: {event_data}")
        data = event_data.get('data', {}) or {}
        navigation_event_type = data.get('type', None)
        navigation_event_data = data.get('data', {}) or {}
        element_id = navigation_event_data.get('element_id', '')

        match navigation_event_type:
            case 'started':
                self.navigation_events.started.set(data=element_id, flags={'id': element_id})
            case 'finished':
                self.logger.info("Set finished event")
                self.navigation_events.finished.set(data=element_id, flags={'id': element_id})
            case 'skipped':
                self.navigation_events.skipped.set(data=element_id, flags={'id': element_id})
            case 'timeout':
                self.navigation_events.timeout.set(data=element_id, flags={'id': element_id})
            case 'aborted':
                self.navigation_events.aborted.set(data=element_id, flags={'id': element_id})
            case 'error':
                self.navigation_events.error.set(data=element_id, flags={'id': element_id})
            case _:
                self.logger.warning(f"Unknown navigation event: {navigation_event_type}")
