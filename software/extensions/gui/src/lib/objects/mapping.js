import {ButtonWidget, MultiStateButtonWidget} from './js/buttons.js';
import {ClassicSliderWidget, RotaryDialWidget, SliderWidget} from './js/sliders.js';
import {JoystickWidget} from './js/joystick.js';
import {MultiSelectWidget} from './js/select.js';
import {
    DigitalClockWidget,
    DigitalNumberWidget,
    InputWidget,
    LineScrollTextWidget,
    StatusWidget,
    TextWidget
} from './js/text.js';
import {ImageWidget, UpdatableImageWidget, VideoWidget} from './js/media.js';
import {MapWidget} from '../map/map.js';
import {RT_Plot_Widget} from '../plot/realtime/rt_plot.js';
import {Table} from './js/table.js';
import {PagedGroupsWidget, WidgetGroup} from './group.js';
import {CheckboxWidget} from "./js/checkbox.js";
import {
    BatteryIndicatorWidget,
    CircleIndicator, ConnectionIndicator,
    InternetIndicator, JoystickIndicator,
    LoadingIndicator, NetworkIndicator,
    ProgressIndicator
} from "./js/indicators.js";
import {DirectoryWidget} from "./js/directory.js";
import {TerminalWidget} from "./js/terminal.js";
import {BILBO_OverviewWidget} from "./js/bilbo.js";
import {LinePlotWidget} from "../plot/lineplot/lineplot.js";
import {BabylonWidget} from "./js/babylon_widget.js";
import {CollapsibleContainer, ContainerWrapperWidget, GUI_Container, GUI_Container_Stack} from "./objects.js";
import {JoystickAssignmentWidget} from "./js/joystick_assignment.js";
import {BilboModeWidget} from "./js/bilbo_mode.js";
import {CameraWidget} from "./js/camera.js";
import {BilboLimboWidget} from "./js/bilbo_limbo.js";
import {ExperimentDesignerWidget} from "./js/experiment_designer_widget.js";

export let OBJECT_MAPPING = {
    'ButtonWidget': ButtonWidget,
    'button': ButtonWidget,
    'slider': SliderWidget,
    'joystick': JoystickWidget,
    'rotary_dial': RotaryDialWidget,
    'multi_state_button': MultiStateButtonWidget,
    'multi_select': MultiSelectWidget,
    'classic_slider': ClassicSliderWidget,
    'digital_number': DigitalNumberWidget,
    'text': TextWidget,
    'input': InputWidget,
    'status': StatusWidget,
    'table': Table,
    'group': WidgetGroup,
    'rt_plot': RT_Plot_Widget,
    'image': ImageWidget,
    'video': VideoWidget,
    'checkbox': CheckboxWidget,
    'circle_indicator': CircleIndicator,
    'loading_indicator': LoadingIndicator,
    'progress_indicator': ProgressIndicator,
    'directory': DirectoryWidget,
    'terminal': TerminalWidget,
    'bilbo_overview': BILBO_OverviewWidget,
    'battery_indicator': BatteryIndicatorWidget,
    'internet_indicator': InternetIndicator,
    'connection_indicator': ConnectionIndicator,
    'joystick_indicator': JoystickIndicator,
    'network_indicator': NetworkIndicator,
    'lineplot': LinePlotWidget,
    'group_container': PagedGroupsWidget,
    'updatable_image': UpdatableImageWidget,
    'babylon_widget': BabylonWidget,
    'line_scroll_widget': LineScrollTextWidget,
    'map': MapWidget,
    'ContainerWrapper': ContainerWrapperWidget,
    'container_stack': GUI_Container_Stack,
    'collapsivle_container': CollapsibleContainer,
    'container': GUI_Container,
    'digital_clock': DigitalClockWidget,
    'joystick_assignment': JoystickAssignmentWidget,
    'bilbo_mode': BilboModeWidget,
    'camera': CameraWidget,
    'bilbo_limbo': BilboLimboWidget,
    'experiment_designer': ExperimentDesignerWidget
}