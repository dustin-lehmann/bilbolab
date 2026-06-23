"""Application-level CLI for the IdeenExpo 2026 application.

Provides an ``expo`` command namespace for expo-wide actions. Robot- and
joystick-specific commands continue to live in their own command sets
(``robots`` and ``joysticks``); this set is for expo-level convenience commands.

Groundwork: a couple of commands are wired up; extend as needed.
"""
from __future__ import annotations

from extensions.tools.cli.cli import CommandSet, Command


# ======================================================================================================================
class IdeenExpo2026_CommandSet(CommandSet):
    name = 'expo'
    description = 'IdeenExpo 2026 application commands'

    def __init__(self, application) -> None:
        self.application = application

        panic_command = Command(name='panic',
                                function=self._panic,
                                description='Switch all robots off immediately')

        all_on_command = Command(name='all-on',
                                 function=self._all_on,
                                 description='Switch all robots on')

        info_command = Command(name='info',
                               function=self._info,
                               description='Show expo application status')

        super().__init__(self.name,
                         commands=[panic_command, all_on_command, info_command],
                         children=[],
                         description=self.description)

    # ------------------------------------------------------------------------------------------------------------------
    def _panic(self):
        jc = self.application.joystick_control
        if jc is not None and hasattr(jc, 'allRobotsOff'):
            jc.allRobotsOff()
        else:
            self.application.manager.emergency_stop()
        return 'All robots OFF'

    # ------------------------------------------------------------------------------------------------------------------
    def _all_on(self):
        jc = self.application.joystick_control
        if jc is not None and hasattr(jc, 'allRobotsOn'):
            jc.allRobotsOn()
            return 'All robots ON'
        return 'Master joystick control not available'

    # ------------------------------------------------------------------------------------------------------------------
    def _info(self):
        robots = list(self.application.manager.robot_manager.robots.keys())
        jc = self.application.joystick_control
        master = getattr(jc, 'master_joystick', None) if jc is not None else None
        output = (
            f"Robots connected: {robots if robots else 'none'}\n"
            f"Master joystick : {master.id if master is not None else 'not connected'}"
        )
        return output
