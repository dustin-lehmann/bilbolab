from __future__ import annotations

import dataclasses
import time

from robots.frodo.applications.agent_manager import FRODO_AgentManager
from robots.frodo.applications.algorithm.algorithm_manager import FRODO_AlgorithmManager, AlgorithmSettings
from robots.frodo.applications.experiments.frodo_experiment import FRODO_ExperimentManager, ExperimentSettings
from robots.frodo.applications.gui.frodo_gui import FRODO_GUI
from robots.frodo.applications.simulation.frodo_simulation import FRODO_Simulation
from robots.frodo.applications.testbed.testbed_manager import FRODO_TestbedManager
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.sound.sound import SoundSystem, speak
from extensions.tools.cli.cli import CLI, CommandSet


# ======================================================================================================================
@dataclasses.dataclass
class FRODO_Application_Settings:
    update_time_algorithm: float = 0.2
    update_time_agents: float = 0.1
    update_time_simulation: float = 0.02


# ======================================================================================================================
class FRODO_Application:
    settings: FRODO_Application_Settings

    simulation: FRODO_Simulation
    testbed: FRODO_TestbedManager
    agent_manager: FRODO_AgentManager
    experiment_manager: FRODO_ExperimentManager
    algorithm_manager: FRODO_AlgorithmManager

    gui: FRODO_GUI
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self, settings: FRODO_Application_Settings):
        self.settings = settings
        self.logger = Logger('App', 'DEBUG')

        # Create the necessary modules
        self.simulation = FRODO_Simulation(Ts=self.settings.update_time_simulation)
        self.testbed = FRODO_TestbedManager()
        self.agent_manager = FRODO_AgentManager(simulation=self.simulation, testbed_manager=self.testbed)

        self.algorithm_manager = FRODO_AlgorithmManager(
            settings=AlgorithmSettings(Ts=self.settings.update_time_algorithm)
        )

        self.experiment_manager = FRODO_ExperimentManager(
            agent_manager=self.agent_manager,
            algorithm_manager=self.algorithm_manager,
            settings=ExperimentSettings(
                update_time_agents=self.settings.update_time_agents,
                update_time_algorithm=self.settings.update_time_algorithm
            ))

        # Create the GUI
        self.gui = FRODO_GUI(self.testbed.robot_manager.host, self, self.testbed)
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # CLI
        self.command_set = self.Commands(self)
        self.cli = CLI(id='frodo_app_cli', root=self.command_set)

        register_exit_callback(self.close)

    # === MODULES ======================================================================================================
    def init(self):
        self.simulation.init()
        self.testbed.init()
        self.experiment_manager.init()
        self.gui.init()
        self.gui.gui.cli_terminal.setCLI(self.cli)

        self.cli.root.addChild(self.testbed.robot_manager.cli)
        self.cli.root.addChild(self.simulation.cli)
        self.cli.root.addChild(self.experiment_manager.algorithm_manager.commands)
        self.cli.root.addChild(self.agent_manager.commands)

        self.cli.root.addChild(self.experiment_manager.commands)
        self.cli.root.addChild(self.gui.commands)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.testbed.start()
        # self.joystick_manager.start()
        self.simulation.start()
        self.agent_manager.start()
        self.experiment_manager.start()
        speak("Start Frodo Application")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        speak("Closing Frodo Application")
        self.simulation.stop()

    # === PRIVATE MODULES ==============================================================================================

    # === CLASSES ======================================================================================================
    class Commands(CommandSet):
        def __init__(self, app: FRODO_Application):
            super().__init__('app')


if __name__ == '__main__':
    settings = FRODO_Application_Settings()
    app = FRODO_Application(settings)
    app.init()
    app.start()

    while True:
        time.sleep(10)
