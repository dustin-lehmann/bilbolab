"""GUI for the IdeenExpo 2026 application.

Subclasses the standard :class:`BILBO_Application_GUI` and adds groundwork for
the master-joystick controls (override / release / all-on / all-off). The actual
wiring of these GUI callbacks to the joystick control is done by the application
(see ``ideenexpo_2026.py``) so the GUI stays decoupled from the joystick logic.

The desktop GUI and the mobile app are both created by the base class
(``self.gui`` and ``self.app``). Master controls are added to the desktop GUI
here; the mobile-app equivalent is left as a documented stub
(:meth:`_build_master_app_controls`).
"""
from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from extensions.gui.src.lib.objects.python.buttons import Button
# bilbo_gui must be imported before any other robots.bilbo.* heavy module (resolves the
# import graph / avoids the settings<->dilc circular import). See bilbo-settings note.
from robots.bilbo.gui.bilbo_gui import BILBO_Application_GUI
from robots.bilbo.applications.ideenexpo_2026.app_master_folder import IdeenExpo2026_App_Master_Folder
from robots.bilbo.applications.ideenexpo_2026.big_view_page import IdeenExpo2026_BigViewPage
from robots.bilbo.applications.ideenexpo_2026.camera_page import IdeenExpo2026_CameraPage


# ======================================================================================================================
@callback_definition
class IdeenExpo2026_GUI_MasterCallbacks:
    override: CallbackContainer
    all_robots_on: CallbackContainer
    all_robots_off: CallbackContainer


# ======================================================================================================================
class IdeenExpo2026_GUI(BILBO_Application_GUI):
    """Expo GUI: standard BILBO GUI plus master-joystick controls."""

    master_callbacks: IdeenExpo2026_GUI_MasterCallbacks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.master_callbacks = IdeenExpo2026_GUI_MasterCallbacks()

        # NOTE: The big Babylon "Arena" page is temporarily disabled. Its widget
        # serializes a null babylon when the shared visualization isn't attached
        # in time (event-order race), which throws on the frontend and aborts the
        # whole Application category build. Re-enable once that attach is made
        # deterministic.
        self.big_view_page = None
        # self._build_big_view_page()
        self._build_camera_page()
        self._build_master_controls()
        self._build_master_app_controls()

    # ------------------------------------------------------------------------------------------------------------------
    def _application_category(self):
        """The standard 'Application' category (holds the Testbed page)."""
        return self.categories.get('application', {}).get('category')

    # ------------------------------------------------------------------------------------------------------------------
    def _build_big_view_page(self):
        """Add a full-screen 3D arena view as an extra page in the Application category.

        Re-uses the shared BabylonVisualization owned by the standard overview
        page (``self.testbed_page``), so the big view mirrors the small one live.
        """
        category = self._application_category()
        if category is None:
            self.logger.warning("Application category not found; skipping arena page")
            self.big_view_page = None
            return

        self.big_view_page = IdeenExpo2026_BigViewPage(
            manager=self.testbed_manager,
            overview_page=self.testbed_page,
        )
        category.addPage(self.big_view_page.page)
        self.categories['application'].setdefault('pages', {})['bigview'] = self.big_view_page.page

    # ------------------------------------------------------------------------------------------------------------------
    def _build_camera_page(self):
        """Add a full-screen USB testbed-camera view as an extra page in the Application category."""
        camera_settings = getattr(self.application_settings, 'camera', None)
        if camera_settings is None or not camera_settings.enabled:
            self.camera_page = None
            return

        category = self._application_category()
        if category is None:
            self.logger.warning("Application category not found; skipping camera page")
            self.camera_page = None
            return

        self.camera_page = IdeenExpo2026_CameraPage(
            settings=camera_settings,
            host=self.host,
            manager=self.testbed_manager,
            speed_settings=getattr(self.application_settings, 'speed', None),
            joystick_control=self.joystick_control,
        )
        category.addPage(self.camera_page.page)
        self.categories['application'].setdefault('pages', {})['camera'] = self.camera_page.page

    # ------------------------------------------------------------------------------------------------------------------
    def _build_master_controls(self):
        """Add master-joystick control buttons to the 'application' category.

        Groundwork: the buttons fire ``master_callbacks``; the application wires
        those to the joystick control. Placement/labelling will be refined.
        """
        category = self.categories.get('application', {}).get('category')
        if category is None:
            self.logger.warning("Application category not found; skipping master controls")
            return

        override_button = Button(
            widget_id='master_override_btn', text='Override', icon='🕹️',
            font_size=9, color=[0.25, 0.18, 0.1],
        )
        override_button.callbacks.click.register(
            Callback(function=self.master_callbacks.override.call, discard_inputs=True))
        category.bottom_group.addWidget(override_button, row=2, column=1, width=1, height=1)

        all_on_button = Button(
            widget_id='master_all_on_btn', text='All On', icon='🟢',
            font_size=9, color=[0.1, 0.25, 0.12],
        )
        all_on_button.callbacks.click.register(
            Callback(function=self.master_callbacks.all_robots_on.call, discard_inputs=True))
        category.bottom_group.addWidget(all_on_button, row=3, column=1, width=1, height=1)

        all_off_button = Button(
            widget_id='master_all_off_btn', text='All Off', icon='🔴',
            font_size=9, color=[0.3, 0.1, 0.1],
        )
        all_off_button.callbacks.click.register(
            Callback(function=self.master_callbacks.all_robots_off.call, discard_inputs=True))
        category.bottom_group.addWidget(all_off_button, row=3, column=2, width=1, height=1)

        # Keep references so they aren't garbage collected / can be updated later.
        self._master_buttons = {
            'override': override_button,
            'all_on': all_on_button,
            'all_off': all_off_button,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def _build_master_app_controls(self):
        """Add the Master folder (Target + Override Mode selectors) to the mobile App."""
        if self.joystick_control is None or not hasattr(self.joystick_control, 'setMasterMode'):
            self.master_app_folder = None
            return

        self.master_app_folder = IdeenExpo2026_App_Master_Folder(
            app=self.app,
            joystick_control=self.joystick_control,
            speed_settings=getattr(self.application_settings, 'speed', None),
        )
