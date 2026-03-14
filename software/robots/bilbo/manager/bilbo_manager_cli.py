from __future__ import annotations

from extensions.tools.cli.cli import CommandSet, Command, CommandArgument


# ======================================================================================================================
class BILBO_Manager_CommandSet(CommandSet):
    name = 'robots'
    description = 'Functions related to connected BILBO'

    def __init__(self, bilbo_manager) -> None:

        self.bilbo_manager = bilbo_manager

        stop_command = Command(name='stop',
                               function=self.bilbo_manager.emergencyStop,
                               description='Deactivates the control on all BILBO robots', )

        list_command = Command(name='list',
                               function=self._list_robots,
                               description='', )

        super().__init__(self.name, commands=[stop_command, list_command], children=[], description=self.description)

    def _list_robots(self):
        output = ""
        for robot in self.bilbo_manager.robots.values():
            output += f"{robot.id} \t {robot.device.config.revision} \n"

        if output == "":
            output = "No robots connected"
        self.bilbo_manager.logger.info(output)
        return output

