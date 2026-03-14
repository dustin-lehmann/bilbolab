class TiledGround{
    constructor(scene,id,config){
        let default_config = {
            'color1': [0.5,0.5,0.5],
            'color2': [0.65,0.65,0.65]
        }
        this.config = {...default_config, ...config}
        let tile_size = this.config['tile_size']
        let tiles_x = this.config['tiles_x']
        let tiles_y = this.config['tiles_y']
        let color1 = this.config['color1']
        let color2 = this.config['color2']

        var grid = {
            'h' : tiles_x,
            'w' : tiles_y
        };

        this.tiledGround = new BABYLON.MeshBuilder.CreateTiledGround("Tiled Ground", {xmin: -tile_size*tiles_x/2, zmin: -tile_size*tiles_y/2, xmax: tile_size*tiles_x/2, zmax: tile_size*tiles_y/2, subdivisions: grid}, scene);

    //Create the multi material
    // Create differents material
    this.whiteMaterial = new BABYLON.StandardMaterial("White", scene);
    this.whiteMaterial.diffuseColor = new BABYLON.Color3(color1[0],color1[1],color1[2]);
    this.whiteMaterial.specularColor = new BABYLON.Color3(0, 0, 0);

    this.blackMaterial = new BABYLON.StandardMaterial("White", scene);
    this.blackMaterial.diffuseColor = new BABYLON.Color3(color2[0],color2[1],color2[2]);
    this.blackMaterial.specularColor = new BABYLON.Color3(0, 0, 0);

    // Create Multi Material
    this.multimat = new BABYLON.MultiMaterial("multi", scene);
    this.multimat.subMaterials.push(this.whiteMaterial);
    this.multimat.subMaterials.push(this.blackMaterial);


    // Apply the multi material
    // Define multimat as material of the tiled ground
    this.tiledGround.material = this.multimat;

    // Needed variables to set subMeshes
    this.verticesCount = this.tiledGround.getTotalVertices();
    this.tileIndicesLength = this.tiledGround.getIndices().length / (grid.w * grid.h);

    // Set subMeshes of the tiled ground
    this.tiledGround.subMeshes = [];
    var base = 0;
    for (var row = 0; row < grid.h; row++) {
        for (var col = 0; col < grid.w; col++) {
            this.tiledGround.subMeshes.push(new BABYLON.SubMesh(row%2 ^ col%2, 0, this.verticesCount, base , this.tileIndicesLength, this.tiledGround));
            base += this.tileIndicesLength;
        }
    }
}
}


function drawCoordinateSystem(scene, length) {
        const points_x = [
            ToBabylon([0, 0, 0]),
            ToBabylon([length, 0, 0])
        ]
        const points_y = [
            ToBabylon([0, 0, 0]),
            ToBabylon([0, length, 0])
        ]
        const points_z = [
            ToBabylon([0, 0, 0]),
            ToBabylon([0, 0, length])
        ]
        new BABYLON.Color3(1, 0, 0);
        var line_x = BABYLON.MeshBuilder.CreateLines("line_x", {points: points_x}, scene);
        line_x.color = new BABYLON.Color3(1, 0, 0);

        var line_y = BABYLON.MeshBuilder.CreateLines("line_y", {points: points_y}, scene);
        line_y.color = new BABYLON.Color3(0, 1, 0);

        var line_z = BABYLON.MeshBuilder.CreateLines("line_z", {points: points_z}, scene);
        line_z.color = new BABYLON.Color3(0, 0, 1);
    }