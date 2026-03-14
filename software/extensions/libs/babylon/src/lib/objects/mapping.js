import {BabylonBilbo} from "./bilbo/bilbo.js";
import {BabylonFrodo} from "./frodo/frodo.js";
import {BabylonBox, BabylonWall, BabylonWall_Fancy} from "./box/box.js";
import {BabylonFloorInstanced, BabylonSimpleFloor} from "./floor/floor.js";
import {BabylonCircleDrawing, BabylonLineDrawing, BabylonPathDrawing, BabylonPointsDrawing, BabylonRectangleDrawing} from "./drawings";
import {ArucoStatic} from "./static/static";
import {ClusterTool} from "./clustertool/clustertool";
import {BabylonLaserLine} from "./laser/laser.js";
import {BabylonCylinder} from "./cylinder/cylinder.js";

export let BABYLON_OBJECT_MAPPINGS = {
    'bilbo': BabylonBilbo,
    'bilbo_simple': null,
    'frodo': BabylonFrodo,
    'box': BabylonBox,
    'floor': BabylonFloorInstanced,
    'floor_simple': BabylonSimpleFloor,
    'wall': BabylonWall,
    'wall_fancy': BabylonWall_Fancy,
    "rectangle_drawing": BabylonRectangleDrawing,
    "circle_drawing": BabylonCircleDrawing,
    "line_drawing": BabylonLineDrawing,
    "path_drawing": BabylonPathDrawing,
    "points_drawing": BabylonPointsDrawing,
    'static': ArucoStatic,
    'clustertool': ClusterTool,
    'laser_line': BabylonLaserLine,
    'cylinder': BabylonCylinder,
}