/*
  pysim_objects.js
  BabylonJS objects for Pysim simulation.
*/

function ToBabylon(coordinates) {
    return new BABYLON.Vector3(coordinates[0], coordinates[2], -coordinates[1]);
}

// =====================================================================================================================
// Base class for world objects.
class WorldObject {
    constructor(scene, object_id, config) {
        this.object_id = object_id;
        this.config = config;
        this.scene = scene;
        this.loaded = false;
    }

    setState(state) {
        // Override in subclasses if needed.
    }

    setPosition(position) {
        // To be implemented in subclasses.
    }

    setOrientation(orientation) {
        // To be implemented in subclasses.
    }

    highlight() {
        // To be implemented in subclasses.
    }

    setVisibility() {
        // To be implemented in subclasses.
    }

    delete() {
        // Cleanup code if needed.
    }

    set(parameter, value) {
        // To be implemented in subclasses.
    }

    update(newData) {
        // Merge new data into current config
        this.config = Object.assign({}, this.config, newData);
        if (this.config.configuration) {
            if (this.config.configuration.pos) {
                this.setPosition(this.config.configuration.pos);
            }
            if (this.config.configuration.ori) {
                this.setOrientation(this.config.configuration.ori);
            }
        }
    }
}

// =====================================================================================================================
// Box object using BabylonJS MeshBuilder.
class PysimBox extends WorldObject {
    constructor(scene, object_id, object_config) {
        super(scene, object_id, object_config);
        const default_visualization_config = {
            color: [1, 0, 0],
            texture: '',
            texture_uscale: 1,
            texture_vscale: 1,
            visible: true,
            wireframe: false,
            alpha: 1
        };
        let visualization_config = {}
        this.visualization_config = Object.assign({}, default_visualization_config, object_config);
        this.size = {
            x: object_config.size.x,
            y: object_config.size.y,
            z: object_config.size.z
        };
        this.position = object_config.configuration.pos;
        this.orientation = object_config.configuration.ori;
        this.body = BABYLON.MeshBuilder.CreateBox('box', { height: this.size.z, width: this.size.x, depth: this.size.y }, scene);
        this.material = new BABYLON.StandardMaterial(this.scene);
        if (this.visualization_config.texture) {
            this.material.diffuseTexture = new BABYLON.Texture(this.visualization_config.texture, this.scene);
            this.material.diffuseTexture.uScale = this.visualization_config.texture_uscale;
            this.material.diffuseTexture.vScale = this.visualization_config.texture_vscale;
            this.material.specularColor = new BABYLON.Color3(0, 0, 0);
        } else {
            this.material.diffuseColor = new BABYLON.Color3(this.visualization_config.color[0], this.visualization_config.color[1], this.visualization_config.color[2]);
        }
        this.body.material = this.material;
        this.body.material.alpha = this.visualization_config.alpha;
        if (this.visualization_config.wireframe) {
            this.body.enableEdgesRendering();
            this.body.edgesWidth = 0.75;
            this.body.edgesColor = new BABYLON.Color4(1, 0, 0, 1);
        }
        this.setPosition(this.position);
        this.setOrientation(this.orientation);
        this.loaded = true;
    }

    setPosition(position) {
        this.position = position;
        this.body.position = ToBabylon([position.x, position.y, position.z]);
    }

    setOrientation(orientation) {
        this.orientation = orientation;
        const q = Quaternion.fromRotationMatrix(orientation);
        this.body.rotationQuaternion = q.babylon();
    }
}

// =====================================================================================================================
// 2D Grid cell object.
class GridCell2D extends PysimBox {
    constructor(scene, object_id, object_type, object_config, visualization_config) {
        object_config.size.z = 0.05;
        super(scene, object_id, object_type, object_config, visualization_config);
    }

    setPosition(position) {
        position.z = -this.size.z / 2;
        super.setPosition(position);
    }

    highlight(state, color) {
        if (state) {
            this.body.material.diffuseColor = new BABYLON.Color3(color[0], color[1], color[2]);
        } else {
            this.body.material.diffuseColor = new BABYLON.Color3(1, 1, 1);
        }
    }

    update(newData) {
        super.update(newData);
        if (newData.highlight) {
            this.highlight(newData.highlight.state, newData.highlight.color);
        }
    }
}

// =====================================================================================================================
// TWIPR robot object.
class TWIPR_Robot extends WorldObject {
    constructor(scene, object_id, config) {
        super(scene, object_id, config);
        this.model_name = config.mesh + '.babylon';
        if (!config.physics) {
            this.config.physics = { wheel_diameter: 0.125 };
        }
        BABYLON.SceneLoader.ImportMesh("", "./", this.model_name, this.scene, this.onLoad.bind(this));
        return this;
    }

  onLoad(newMeshes, particleSystems, skeletons) {
        this.mesh = newMeshes[0];
        this.mesh.scaling.x = 1;
        this.mesh.scaling.y = 1;
        this.mesh.scaling.z = -1; // Causes mirroring.
        this.material = new BABYLON.StandardMaterial("material", this.scene);
        if (!this.config.color) {
            this.config.color = [0.5, 0.5, 0.5];
        }
        this.set('color', this.config.color);
        this.mesh.material = this.material;

        if ('text' in this.config) {
            // Create a dynamic texture with a larger size.
            const dynamicTexture = new BABYLON.DynamicTexture("DynamicTexture", {width: 256, height: 256}, this.scene);
            const ctx = dynamicTexture.getContext();
            ctx.clearRect(0, 0, 256, 256);

            // Draw a circle
            ctx.beginPath();
            ctx.arc(128, 128, 120, 0, Math.PI * 2, false); // Center (128,128) with a radius of 120.
            ctx.fillStyle = 'rgb(150, 150, 150)';
            ctx.fill();
            ctx.lineWidth = 20;
            ctx.strokeStyle = "black";
            ctx.stroke();

            // The text to display.
            const text = this.config.text; // Change this to any text.

            // Define the maximum allowed text width (in pixels) within the circle.
            const maxTextWidth = 200;
            let fontSize = 250; // Start with a large font size.
            let font = `bold ${fontSize}px Arial`;

            // Set the context font and measure the text width.
            ctx.font = font;
            let measuredWidth = ctx.measureText(text).width;

            // Reduce the font size until the text fits within the maxTextWidth.
            while (measuredWidth > maxTextWidth && fontSize > 10) {
                fontSize -= 10;
                font = `bold ${fontSize}px Arial`;
                ctx.font = font;
                measuredWidth = ctx.measureText(text).width;
            }

            // Optionally, you can log the chosen font size:
            // console.log("Using font:", font, "with measured width:", measuredWidth);

            // Compute a y-offset to vertically center the text in the circle.
            // This calculation can be adjusted based on your design needs.
            const yOffset = 128 + fontSize / 3;

            // Draw the text on top of the circle without clearing the canvas.
            // Passing null as clearColor ensures our circle remains.
            const brightnessFactor = 0.2;
            const [r, g, b] = this.config.color;
            const textColor = `rgb(${Math.floor(r * 255 * brightnessFactor)}, ${Math.floor(g * 255 * brightnessFactor)}, ${Math.floor(b * 255 * brightnessFactor)})`;


            dynamicTexture.drawText(text, null, yOffset, font, textColor, null, true);
            dynamicTexture.update();

            // Create a new material using the dynamic texture.
            const textMaterial = new BABYLON.StandardMaterial("textMaterial", this.scene);
            textMaterial.diffuseTexture = dynamicTexture;
            textMaterial.diffuseTexture.hasAlpha = true;
            textMaterial.useAlphaFromDiffuseTexture = true;
            textMaterial.backFaceCulling = false;

            textMaterial.emissiveColor = new BABYLON.Color3(0.99, 0.99, 0.99);

            // Create an intermediate transform node to counteract the parent's negative scaling.
            const textHolder = new BABYLON.TransformNode("textHolder", this.scene);
            textHolder.parent = this.mesh;
            textHolder.position = new BABYLON.Vector3(0.0325, 0.05, 0);
            textHolder.scaling = new BABYLON.Vector3(1, 1, -1);

            // Create the plane that will display the text.
            const textPlane = BABYLON.MeshBuilder.CreatePlane("textPlane", {width: 0.1, height: 0.1}, this.scene);
            textPlane.material = textMaterial;
            textPlane.parent = textHolder;
            textPlane.rotation = new BABYLON.Vector3(0, 1.57, 0);
        }
    this.loaded = true;
    this.setPosition({ x: 0, y: 0, z: this.config.physics.wheel_diameter / 2 });
    this.setOrientation([[0, 0, 0], [0, 0, 0], [0, 0, 0]]);
}


    setPosition(position) {
        this.position = position;
        this.mesh.position = ToBabylon([position.x, position.y, this.config.physics.wheel_diameter / 2]);
    }

    setOrientation(orientation) {
        this.orientation = orientation;
        let q = Quaternion.fromRotationMatrix(orientation);
        this.mesh.rotationQuaternion = q.babylon();
    }

    update(newData) {
        this.config = Object.assign({}, this.config, newData);
        if (this.config.configuration) {
            if (this.config.configuration.pos) {
                this.setPosition(this.config.configuration.pos);
            }
            if (this.config.configuration.ori) {
                this.setOrientation(this.config.configuration.ori);
            }
        }
    }

    set(parameter, value) {
        if (parameter === 'color') {
            this.material.diffuseColor = new BABYLON.Color3(value[0], value[1], value[2]);
        }
    }

    delete() {
        this.mesh.dispose();
    }
}

// =====================================================================================================================
// Diff Drive Robot object.
class DiffDriveRobot extends WorldObject {
    constructor(scene, object_id, object_type, object_config, visualization_config) {
        super(scene, object_id, object_config);
        this.visualization_config = visualization_config;
        this.loaded = false;
        this.model_name = visualization_config.base_model + object_config.agent_id + '.babylon';
        BABYLON.SceneLoader.ImportMesh("", "./", this.model_name, this.scene, this.onLoad.bind(this));
        if (visualization_config.show_collision_frame) {
            let scaling_factor = 1.01;
            this.collision_box = new PysimBox(this.scene, '', '', {
                size: {
                    x: scaling_factor * object_config.physics.size[0],
                    y: scaling_factor * object_config.physics.size[1],
                    z: scaling_factor * object_config.physics.size[2]
                },
                configuration: object_config.configuration
            }, { wireframe: true, alpha: 0 });
        }
        return this;
    }

    onLoad(newMeshes, particleSystems, skeletons) {
        this.mesh = newMeshes[0];
        this.mesh.scaling.x = 1;
        this.mesh.scaling.y = 1;
        this.mesh.scaling.z = -1;
        this.material = new BABYLON.StandardMaterial("material", this.scene);
        this.mesh.material = this.material;
        this.loaded = true;
    }

    setPosition(position) {
        this.position = position;
        this.mesh.position = ToBabylon([position.x, position.y, 0]);
    }

    setOrientation(orientation) {
        this.orientation = orientation;
        let q = Quaternion.fromRotationMatrix(orientation);
        this.mesh.rotationQuaternion = q.babylon();
        if (this.visualization_config.show_collision_frame) {
            this.collision_box.setOrientation(orientation);
        }
    }

    update(newData) {
        this.config = Object.assign({}, this.config, newData);
        if (this.config.configuration) {
            if (this.config.configuration.pos) {
                this.setPosition(this.config.configuration.pos);
            }
            if (this.config.configuration.ori) {
                this.setOrientation(this.config.configuration.ori);
            }
        }
        if (this.config.collision_box_pos && this.visualization_config.show_collision_frame) {
            this.collision_box.setPosition(this.config.collision_box_pos);
        }
    }

    setState(state) {
        this.setPosition(state.pos);
        this.setOrientation(state.ori);
    }
}
