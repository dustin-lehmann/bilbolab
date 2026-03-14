import time

import numpy as np
import qmt
from bokeh.palettes import Category20c_20

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.network.network import getHostIP
from core.utils.sound.sound import SoundSystem
from core.utils.time import setInterval
from extensions.libs.babylon.src.babylon import BabylonVisualization, BabylonObject
from extensions.libs.babylon.src.lib.objects.box.box import Box
from extensions.libs.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.tools.cli.cli import CLI, CommandSet
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget


class ClusterToolGUI:
    babylon_visualization: BabylonVisualization
    cli: CLI
    gui: GUI
    command_set: CommandSet
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('ClusterTool', 'DEBUG')

        ip = getHostIP()
        if ip is None:
            ip = 'localhost'

        self.cli = CLI(id='clustertool', root=self._generate_command_set())
        self.gui = GUI(id='clustertool', host=ip, run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'ClusterTool'})

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        register_exit_callback(self.close, priority=0)

    # === METHODs ======================================================================================================
    def init(self):
        self._build_gui()
        self._build_babylon()
        self.babylon_visualization.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.babylon_visualization.start()
        self.logger.info("ClusterTool started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _build_babylon(self):
        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        box1 = Box('box1', size={'x': 2, 'y': 1, 'z': 0.5})
        self.babylon_visualization.addObject(box1)

        box1.setPosition(z=1)

        x = 0

        def set_box_position():
            nonlocal x
            x += 0.001
            box1.setPosition(x=x)

        setInterval(set_box_position, 0.01)

        quat = qmt.quatFromAngleAxis(angle=np.pi / 4, axis=[0, 1, 0])
        box1.setOrientation(quat)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_gui(self):
        main_category = Category('main')

        page_simulation = Page('simulation')
        main_category.addPage(page_simulation)

        self.gui.addCategory(main_category)

        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page_simulation.addWidget(self.babylon_widget, row=1, column=1, height=18, width=26)

    # ------------------------------------------------------------------------------------------------------------------
    def _generate_command_set(self) -> CommandSet:
        command_set = CommandSet('root')
        return command_set


def main():
    ctg = ClusterToolGUI()
    ctg.init()
    ctg.start()

    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
