import time

import robots.frodo.applications.navigation.navigator as agent_navigator
from robots.frodo.applications.simulation.frodo_simulation import FRODO_VisionAgent
from core.utils.logging_utils import Logger
from robots.frodo.robot.frodo import FRODO


# ======================================================================================================================
class FRODO_Sim_NavigatedObject(agent_navigator.NavigatedObject):
    agent: FRODO_VisionAgent

    def __init__(self, agent: FRODO_VisionAgent):
        super().__init__(id=agent.agent_id)

        self.agent = agent
        self.agent.navigator.events.element_finished.on(self._on_event_finished)

    def add_navigation_element(self, element: agent_navigator.NavigationElement):
        self.agent.navigator.addElement(element, force_element=False)

    def start_navigation(self):
        self.agent.navigator.startNavigation()

    def stop_navigation(self):
        self.agent.navigator.stopNavigation()

    def _on_event_finished(self, data: agent_navigator.NavigationElement, **kwargs):
        if not isinstance(data, agent_navigator.NavigationElement):
            raise Exception(f"Invalid navigation element: {data}")
        self.events.finished.set(data.id)

    def abort_current_element(self):
        self.agent.navigator.skip_element()


# ======================================================================================================================
class FRODO_Real_NavigatedObject(agent_navigator.NavigatedObject):
    def __init__(self, robot: FRODO):
        super().__init__(id=robot.id)
        self.robot = robot

        self.robot.control.navigation_events.started.on(self._on_element_started)
        self.robot.control.navigation_events.finished.on(self._on_element_finished)
        self.robot.control.navigation_events.skipped.on(self._on_element_skipped)
        self.robot.control.navigation_events.aborted.on(self._on_element_aborted)
        self.robot.control.navigation_events.timeout.on(self._on_element_timeout)
        self.robot.control.navigation_events.error.on(self._on_element_error)

        self.logger = Logger(f"FRODO_Real_NavigatedObject {id(self)}")
        # self.robot.control.

    def add_navigation_element(self, element: agent_navigator.NavigationElement):
        if isinstance(element, agent_navigator.MoveTo):
            result = self.robot.control.addMoveTo(x=element.x, y=element.y)
            self.start_navigation()
        elif isinstance(element, agent_navigator.TurnTo):
            result = self.robot.control.addTurnTo(psi=element.psi)
            self.start_navigation()
        else:
            raise Exception(f"Invalid navigation element: {element}. Not yet supported")

        if not result:
            raise Exception("Could not add navigation element")

    def start_navigation(self):
        result = self.robot.control.startNavigation()
        if not result:
            raise Exception("Could not start navigation")

    def stop_navigation(self):
        result = self.robot.control.stopNavigation()
        if not result:
            raise Exception("Could not stop navigation")

    def abort_current_element(self):
        result = self.robot.control.skip_element()
        if not result:
            raise Exception("Could not abort navigation")

    def _on_element_started(self, element_id: str, **kwargs):
        self.events.started.set(element_id, flags={'id': element_id})

    def _on_element_finished(self, element_id: str, **kwargs):
        self.events.finished.set(element_id, flags={'id': element_id})

    def _on_element_skipped(self, element_id: str, **kwargs):
        self.events.skipped.set(element_id, flags={'id': element_id})

    def _on_element_aborted(self, element_id: str, **kwargs):
        self.events.aborted.set(element_id, flags={'id': element_id})

    def _on_element_timeout(self, element_id: str, **kwargs):
        self.events.timeout.set(element_id, flags={'id': element_id})

    def _on_element_error(self, element_id: str, error: str, **kwargs):
        self.events.error.set(element_id, flags={'id': element_id, 'error': error})
