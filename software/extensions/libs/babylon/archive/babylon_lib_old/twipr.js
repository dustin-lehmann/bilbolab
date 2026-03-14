class TWIPR_simple {
    constructor(scene, options) {
        this.scene = scene;
        const defaults = {
            box_height: 160,
            box_width: 110,
            box_depth: 50,
            box_color: COLORS.C1,
            wheel_diameter: 130,
            wheel_width: 20,
            scale: 1.0,
        };
        options = {...defaults, ...options};

        const body_opts = {
            width: options.box_width,
            height: options.box_height,
            depth: options.box_depth
        }
        const mat = new BABYLON.StandardMaterial('mat', scene);

        this.materialBody = new BABYLON.StandardMaterial(this.scene);
        this.materialBody.alpha = 1;
        this.materialBody.diffuseColor = new BABYLON.Color3(0.4,0.4,0.4);

        this.materialWheels = new BABYLON.StandardMaterial(this.scene);
        this.materialWheels.alpha = 1;
        this.materialWheels.diffuseColor = new BABYLON.Color3(0.2,0.2,0.2);

        // BILBO body
        this.body = BABYLON.MeshBuilder.CreateBox('box', body_opts, scene);
        this.body.material = this.materialBody;

        // BILBO Wheels
        this.wheel1 = BABYLON.MeshBuilder.CreateCylinder("cone", {diameterTop: options.wheel_diameter, tessellation: 0,
        diameter: options.wheel_diameter, height: options.wheel_width}, this.scene);
        // this.wheel1.position.y = options.wheel_diameter/2
        this.wheel1.position.x = options.box_width/2 + options.wheel_width/2 + 5
        this.wheel1.rotation.z = 3.14159/2;
        this.wheel1.material = this.materialWheels

        this.wheel2 = BABYLON.MeshBuilder.CreateCylinder("cone", {diameterTop: options.wheel_diameter, tessellation: 0,
        diameter: options.wheel_diameter, height: options.wheel_width}, this.scene);
        // this.wheel2.position.y = options.wheel_diameter/2
        this.wheel2.position.x = - (options.box_width/2 + options.wheel_width/2 + 5)
        this.wheel2.rotation.z = 3.14159/2;
        this.wheel2.material = this.materialWheels

        // Pivot points
        this.body.position.y = options.box_height/2
        this.pivotPointBody = new BABYLON.MeshBuilder.CreateSphere("pivotPoint", {diameter:0}, this.scene);
        this.pivotPointBody.position.y = options.wheel_diameter/2;
        this.pivotPointBody.rotation.x = 0
        this.body.parent = this.pivotPointBody;


        // Create a small sphere to set a new pivot point for the wheels (cylinder)
        this.pivotPointWheels = new BABYLON.MeshBuilder.CreateSphere("pivotPoint", {diameter:0.1}, this.scene);
        this.pivotPointWheels.position.y = options.wheel_diameter/2
        this.wheel1.parent = this.pivotPointWheels;
        this.wheel2.parent = this.pivotPointWheels;


        self.indicator = new AgentIndicator(self.scene, this.pivotPointWheels,{color: [1,0,1]})

        return this;
    }

    setPosition(x, y) {
        this.pivotPointWheels.position.x = y
        this.pivotPointWheels.position.z = x
        this.pivotPointBody.position.x = y
        this.pivotPointBody.position.z = x
    }
    setOrientation(theta, psi){
        this.pivotPointWheels.rotation.y = psi
        this.pivotPointBody.rotation.y = psi
        this.pivotPointBody.rotation.x = theta
    }
}

class AgentIndicator {
    constructor(scene, parent, options) {
        this.scene = scene;
        const defaults = {
            color: [0.8,0,0],
            size: 30,
            id: 1,
        };
        options = {...defaults, ...options};

        this.sphere = BABYLON.MeshBuilder.CreateSphere("sphere", {diameter: options.size}, scene);
        this.sphere.position.y = 200
        this.sphere.parent = parent


        var myMaterial = new BABYLON.StandardMaterial("myMaterial", this.scene);

        myMaterial.diffuseColor = new BABYLON.Color3(options.color[0],options.color[1],options.color[2]);
        myMaterial.emissiveColor = new BABYLON.Color3(1*options.color[0],1*options.color[1],1*options.color[2]);
        myMaterial.alpha = 0.75;

        // var gl = new BABYLON.GlowLayer("glow", this.scene);
        // gl.intensity = 1;

        this.sphere.material = myMaterial;

        return this;
    }
    setPosition(x, y) {

    }

}

class TWIPR_Realistic_1 {
    constructor(scene, shadowGenerator, options) {
        this.scene = scene;
        this.shadowGenerator = shadowGenerator
        const defaults = {
            id: 1,
            indicator: true,
        };
        options = {...defaults, ...options};
        this.options = options
        if (this.options.id === 1) {
            this.model = "twipr_a_blue.babylon"
            this.color = [46/255, 137/255, 214/255]
            this.initial_pos = [0, 0]
        }
        if (this.options.id === 2) {
            this.model = "twipr_a_red.babylon"
            this.color = [139/255, 17/255, 126/255]
            this.initial_pos = [0, 250]
        }
        if (this.options.id === 3) {
            this.model = "twipr_a_green.babylon"
            this.color = [108/255, 190/255, 15/255]
            this.initial_pos = [0, -250]
        }

        this.loaded = false
        //[108/255, 190/255, 15/255]
        BABYLON.SceneLoader.ImportMesh("", "twipr_models/", this.model, this.scene, this.onLoad.bind(this));

        return this;
    }

    onLoad(newMeshes, particleSystems, skeletons){
        this.mesh = newMeshes[0]
        this.pivotPointBody = new BABYLON.MeshBuilder.CreateSphere("pivotPoint2", {diameter:10}, this.scene);
        this.mesh.position.y = this.mesh.position.y - 65
        this.pivotPointBody.position.y = 65;
        this.mesh.parent = this.pivotPointBody

        this.pivotPointWheels = new BABYLON.MeshBuilder.CreateSphere("pivotPoint2", {diameter:10}, this.scene);
        this.pivotPointWheels.position.y = 65;

        if (this.options.indicator){
            this.indicator = new AgentIndicator(this.scene, this.pivotPointBody,{color: this.color})
        }

        this.shadowGenerator.addShadowCaster(this.mesh)
        this.setPosition(this.initial_pos[0], this.initial_pos[1])
        this.loaded = true
    }

    setPosition(x, y) {
        this.pivotPointBody.position.x = y
        this.pivotPointBody.position.z = x

        this.pivotPointWheels.position.x = y
        this.pivotPointWheels.position.z = x
    }
    setOrientation(theta, psi){
        this.pivotPointBody.rotation.y = psi
        this.pivotPointBody.rotation.x = theta
    }
}

class CommunicationLine {
    constructor(scene, gl, options) {
        this.scene = scene;
        const defaults = {
            color: [0.9,0.9,0.9],
            diameter: 5,
            height: 265,
        };
        options = {...defaults, ...options};
        this.options = options
        this.points = [
            new BABYLON.Vector3(1000,options.height,1000),
            new BABYLON.Vector3(-1000,options.height,-1000)
        ]
        this.line = BABYLON.MeshBuilder.CreateLines("line", {points: this.points, updatable: true});

        gl.addIncludedOnlyMesh(this.line)
        gl.customEmissiveColorSelector = (mesh, subMesh, material, result) => {
            if (mesh === this.line) {
                result.r = 0;
                result.g = 10;
                result.b = 10;
            }
        }

        return this;
    }
    setPosition(x1, y1, x2, y2) {
        this.points[0].x = y1
        this.points[0].z = x1

        this.points[1].x = y2
        this.points[1].z = x2
        this.line = BABYLON.MeshBuilder.CreateLines("line", {points: this.points, instance: this.line});
    }
}