"""Big OptiTrack / 3D arena view for the IdeenExpo 2026 application.

Provides a full-size BabylonJS page — the same live 3D scene shown (small) on
the standard Testbed overview page, but blown up to fill the whole page for the
expo audience. The page is added to the standard *Application* category by the
GUI (see ``gui.py``), next to the Testbed page.

The 3D scene itself is *shared*: this page does not build its own
:class:`BabylonVisualization`. It re-uses the one created by the standard
overview page (:class:`BILBO_GUI_OverviewPage`). Both the small overview widget
and this big widget connect to the same BabylonJS websocket server, so robots,
obstacles and planned paths show up in both views simultaneously without any
extra plumbing.
"""
from core.utils.logging_utils import Logger
from extensions.gui.src.gui import Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from robots.bilbo.gui.overview_page import BILBO_GUI_OverviewPage
from robots.bilbo.testbed.testbed_manager import TestbedManager


# ======================================================================================================================
class IdeenExpo2026_BigViewPage:
    """A full-size BabylonJS page that mirrors the shared testbed 3D scene.

    Exposes ``self.page``; the GUI adds it to the Application category.
    """

    page: Page

    def __init__(self, manager: TestbedManager, overview_page: BILBO_GUI_OverviewPage):
        self.manager = manager
        self.overview_page = overview_page
        self.logger = Logger("Big View Page")

        self.page = Page(id='bigview_page', name='Arena', icon='🛰️')

        # One big 3D widget filling the entire (18 x 50) page grid.
        self.babylon_widget = BabylonWidget(widget_id='bigview_babylon_widget')
        self.page.addWidget(self.babylon_widget, row=1, column=1, width=50, height=18)

        # Attach the shared visualization. It is built lazily by the overview page
        # in response to the testbed 'initialized' event, so handle both cases:
        # already initialized (attach now) or not yet (attach when it fires).
        if self.overview_page.babylon_visualization is not None:
            self._attach_babylon()
        else:
            self.manager.events.initialized.on(self._attach_babylon)

    # ------------------------------------------------------------------------------------------------------------------
    def _attach_babylon(self, *args, **kwargs):
        """Point the big widget at the overview page's shared BabylonVisualization."""
        babylon = self.overview_page.babylon_visualization
        if babylon is None:
            self.logger.warning("Shared BabylonVisualization not available; big arena view will be empty.")
            return
        self.babylon_widget.set_babylon(babylon)
        self.logger.info("Big arena view attached to shared 3D scene.")
