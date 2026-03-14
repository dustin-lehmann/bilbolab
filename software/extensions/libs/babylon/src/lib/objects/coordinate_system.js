import {CreateLines} from "@babylonjs/core";
import {coordinatesToBabylon, getBabylonColor3} from "../babylon_utils.js";

export function drawCoordinateSystemThin(scene, length) {
    const z_offset = 0.001;
    const points_x = [
        coordinatesToBabylon([0, 0, z_offset]),
        coordinatesToBabylon([length, 0, z_offset])
    ]
    const points_y = [
        coordinatesToBabylon([0, 0, z_offset]),
        coordinatesToBabylon([0, length, z_offset])
    ]
    const points_z = [
        coordinatesToBabylon([0, 0, z_offset]),
        coordinatesToBabylon([0, 0, length + z_offset])
    ]
    const line_x = CreateLines("line_x", {points: points_x}, scene);
    line_x.color = getBabylonColor3([1, 0, 0]);

    const line_y = CreateLines("line_y", {points: points_y}, scene);
    line_y.color = getBabylonColor3([0, 1, 0]);

    const line_z = CreateLines("line_z", {points: points_z}, scene);
    line_z.color = getBabylonColor3([0, 0, 1]);
}

import { MeshBuilder, StandardMaterial } from "@babylonjs/core";

export function drawCoordinateSystem(scene, length, thickness = 0.02) {
  const z = 0.001;                 // your slight Z-offset
  const radius = thickness / 2;    // tube radius in world units

  const makeMat = (name, rgb) => {
    const m = new StandardMaterial(name, scene);
    m.disableLighting = true;                  // keep pure color
    m.emissiveColor = getBabylonColor3(rgb);  // reuse your helper
    return m;
  };

  const pathX = [ [0, 0, z], [length, 0, z] ].map(coordinatesToBabylon);
  const pathY = [ [0, 0, z], [0, length, z] ].map(coordinatesToBabylon);
  const pathZ = [ [0, 0, z], [0, 0, length + z] ].map(coordinatesToBabylon);

  const axisX = MeshBuilder.CreateTube("axisX", { path: pathX, radius, tessellation: 8 }, scene);
  axisX.isPickable = false;
  axisX.material = makeMat("matX", [1, 0, 0]);

  const axisY = MeshBuilder.CreateTube("axisY", { path: pathY, radius, tessellation: 8 }, scene);
  axisY.isPickable = false;
  axisY.material = makeMat("matY", [0, 1, 0]);

  const axisZ = MeshBuilder.CreateTube("axisZ", { path: pathZ, radius, tessellation: 8 }, scene);
  axisZ.isPickable = false;
  axisZ.material = makeMat("matZ", [0, 0, 1]);
}