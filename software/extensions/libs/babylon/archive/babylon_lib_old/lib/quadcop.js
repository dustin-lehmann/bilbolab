"use strict";

class QuadcopScene extends Scene {
    constructor(id, options) {
        super(id);
        const defaults = {
            groundLevel: -55,
            scale: 50,
            offsetZ: -5,
            droneColor: COLORS.grey,
            droneRefColor: COLORS.C1,
            droneRefAlpha: 0.5,
        };
        options = {...defaults, ...options};
        this.options = options;

        this.createScene();
    }

    createScene() {
        this.camera = new BABYLON.ArcRotateCamera('ArcRotateCamera', 0, 1.3, 130, new BABYLON.Vector3(0, 0, 0), this.scene);
        this.camera.attachControl(this.canvas, false);
        this.light = new BABYLON.HemisphericLight('light1', new BABYLON.Vector3(0,1,0), this.scene);
        this.light2 = new BABYLON.DirectionalLight('DirectionalLight', new BABYLON.Vector3(0, -1, 0.2), this.scene);

        // https://babylonjsguide.github.io/intermediate/Skybox
        const skybox = BABYLON.MeshBuilder.CreateBox('skyBox', {size:1000.0}, this.scene);
        const skyboxMaterial = new BABYLON.StandardMaterial('skyBox', this.scene);
        skyboxMaterial.backFaceCulling = false;
        skyboxMaterial.reflectionTexture = new BABYLON.CubeTexture('lib/textures.json/skybox', this.scene);
        skyboxMaterial.reflectionTexture.coordinatesMode = BABYLON.Texture.SKYBOX_MODE;
        skyboxMaterial.diffuseColor = new BABYLON.Color3(0, 0, 0);
        skyboxMaterial.specularColor = new BABYLON.Color3(0, 0, 0);
        skybox.material = skyboxMaterial;

        this.ground = new Ground(this.scene, this.options.groundLevel);

        // pos_x, pos_y, dim_x, dim_y, height
        this.buildings = this.createBuildings();

        this.obstacles = this.buildings.map(function(o) {return o.box;});
        this.obstacles.push(this.ground.obj);

        this.scene.enablePhysics(new BABYLON.Vector3(0,-2*9.81, 0), new BABYLON.OimoJSPlugin());
        for (let o of this.obstacles) {
            o.physicsImpostor = new BABYLON.PhysicsImpostor(o, BABYLON.PhysicsImpostor.BoxImpostor, { mass: 0, restitution: 0.5 }, this.scene);
        }

        this.drone = new Drone(this.scene, {
            color: this.options.droneColor,
            obstacles: this.obstacles,
            scale: this.options.scale,
            canBurn: true,
            offsetZ: this.options.offsetZ,
        });
        this.droneRef = new Drone(this.scene, {
            color: this.options.droneRefColor,
            alpha: this.options.droneRefAlpha,
            posSignal: 'pos_ref',
            quatSignal: 'quat_ref',
            obstacles: [],
            scale: this.options.scale,
            canBurn: false,
            offsetZ: this.options.offsetZ,
        });
    }

    createBuildings() {
        return [
            new Skyscraper(this.scene, this.options, -1, 0, 0.3, 0.3, 0, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, 0.72, 0, 0.3, 0.3, 0.18, COLORS.lightgrey),

            new Skyscraper(this.scene, this.options, 0, 0, 0.25, 0.25, 0.4, COLORS.lightgrey),

            new Skyscraper(this.scene, this.options, -0.5, 0.3, 0.4, 0.4, 0.25, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, 0.35, 0.0, 0.2, 0.2, -0.3, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, -0.5, -0.4, 0.4, 0.25, -0.5, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, 1.2, -0.2, 0.42, 0.42, 0.8, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, -1.35, -0.2, 0.2, 0.3, 0.3, COLORS.lightgrey),

            new Skyscraper(this.scene, this.options, -0.35, 0.8, 0.2, 0.3, 0.13, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, 0.74, 0.9, 0.4, 0.4, -0.18, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, -1.4, 1.1, 0.3, 0.4, 0.1, COLORS.lightgrey),
            new Skyscraper(this.scene, this.options, 1.5, 1.2, 0.45, 0.4, 0.3, COLORS.lightgrey),
        ];
    }

    onSample(sample) {
        this.drone.onSample(sample);
        this.droneRef.onSample(sample);
    }
}

class Ground {
    constructor(scene, groundLevel) {
        this.scene = scene;
        this.obj = BABYLON.Mesh.CreatePlane('ground', 350, scene);
        this.obj.position.y = groundLevel;
        this.obj.rotation.x = Math.PI / 2;

        const materialPlane = new BABYLON.StandardMaterial('texturePlane', scene);
        materialPlane.diffuseColor = COLORS.lightgrey;
        materialPlane.backFaceCulling = false;

        this.obj.material = materialPlane;
    }
}

class Skyscraper {
    constructor(scene, options, pos_x, pos_y, dim_x, dim_y, height, col) {
        const defaults = {
            groundLevel: -55,
            scale: 50,
            offsetZ: -5,
        };
        options = {...defaults, ...options};
        this.scene = scene;

        pos_x = options.scale*pos_x;
        pos_y = options.scale*pos_y;
        dim_x = options.scale*dim_x;
        dim_y = options.scale*dim_y;
        height = options.scale*height - options.groundLevel + options.offsetZ - 2.5; // 2.5 is half of the uav height

        // const col = COLORS.lightgrey;
        const boxopts = {
            width: dim_y,
            height: height,
            depth: dim_x,
            // faceColors: faceColors
            faceColors: [col, col, col, col, col, col]
        };
        this.box = BABYLON.MeshBuilder.CreateBox('box', boxopts, scene);
        this.box.position.y = options.groundLevel + height/2;
        this.box.position.x = -pos_y;
        this.box.position.z = -pos_x;
    }
}

class Drone {
    constructor(scene, options) {
        const defaults = {
            color: COLORS.grey,
            alpha: 1,
            posSignal: 'pos',
            quatSignal: 'quat',
            resetSignal: 'reset',
            obstacles: [],
            scale: 1,
            canBurn: true,
            offsetZ: 0,
        };
        options = {...defaults, ...options};

        this.scene = scene;
        this.options = options;
        this.crashed = false;

        this.lastResetVal = undefined;

        this.createDrone();
    }

    createDrone() {
        const scene = this.scene;

        this.bbox = BABYLON.MeshBuilder.CreateBox('bbox', {height: 3, width: 13, depth: 13}, scene);
        this.bbox.visibility = false;
        this.obj = this.bbox;

        // center sphere (name of the sphere, segments, diameter, scene)
        const sphere = BABYLON.Mesh.CreateSphere('sphere', 5.0, 5.0, scene);
        sphere.parent = this.bbox;

        // bars (name, height, diameter, tessellation, scene, updatable)
        const cylinderlu = BABYLON.Mesh.CreateCylinder("cylinderlu", 4, 0.4, 0.4, 30, 1, scene, false);
        const cylinderlo = BABYLON.Mesh.CreateCylinder("cylinderlu", 4, 0.4, 0.4, 30, 1, scene, false);
        const cylinderru = BABYLON.Mesh.CreateCylinder("cylinderlu", 4, 0.4, 0.4, 30, 1, scene, false);
        const cylinderro = BABYLON.Mesh.CreateCylinder("cylinderlu", 4, 0.4, 0.4, 30, 1, scene, false);
        cylinderlu.parent = sphere;
        cylinderlo.parent = sphere;
        cylinderru.parent = sphere;
        cylinderro.parent = sphere;

        // rotor cylinders
        const cylinderLU = BABYLON.Mesh.CreateCylinder("cylinderlu", 3, 3, 3, 6, 1, scene, false);
        const cylinderLO = BABYLON.Mesh.CreateCylinder("cylinderlu", 3, 3, 3, 6, 1, scene, false);
        const cylinderRU = BABYLON.Mesh.CreateCylinder("cylinderlu", 3, 3, 3, 6, 1, scene, false);
        const cylinderRO = BABYLON.Mesh.CreateCylinder("cylinderlu", 3, 3, 3, 6, 1, scene, false);
        cylinderLU.parent = sphere;
        cylinderLO.parent = sphere;
        cylinderRU.parent = sphere;
        cylinderRO.parent = sphere;

        // center torus (name, diameter, thickness, tessellation, scene, updatable)
        const torus = BABYLON.Mesh.CreateTorus("torus", 5, 1, 10, scene, false);
        torus.parent = sphere;

        // move and rotate elements
        sphere.position = new BABYLON.Vector3(0, 0, 0);
        cylinderlu.position = new BABYLON.Vector3(-3, 0, -3);
        cylinderlu.rotation.x = Math.PI/2;
        cylinderlu.rotation.y = Math.PI/4;
        cylinderLU.position = new BABYLON.Vector3(-5, 0, -5);

        cylinderlo.position = new BABYLON.Vector3(-3, 0, 3);
        cylinderlo.rotation.x = Math.PI/2;
        cylinderlo.rotation.y = -Math.PI/4;
        cylinderLO.position = new BABYLON.Vector3(-5, 0, 5);

        cylinderru.position = new BABYLON.Vector3(3, 0, -3);
        cylinderru.rotation.x = Math.PI/2;
        cylinderru.rotation.y = -Math.PI/4;
        cylinderRU.position = new BABYLON.Vector3(5, 0, -5);

        cylinderro.position = new BABYLON.Vector3(3, 0, 3);
        cylinderro.rotation.x = Math.PI/2;
        cylinderro.rotation.y = Math.PI/4;
        cylinderRO.position = new BABYLON.Vector3(5, 0, 5);

        const material = new BABYLON.StandardMaterial('spheretexture', scene);
        material.diffuseColor = this.options.color;
        material.alpha = this.options.alpha;

        sphere.material = material;
        cylinderlu.material = material;
        cylinderlo.material = material;
        cylinderro.material = material;
        cylinderru.material = material;
        torus.material = material;

        cylinderLU.material = material;
        cylinderLO.material = material;
        cylinderRO.material = material;
        cylinderRU.material = material;

        this.burningObjects = [sphere, cylinderLU, cylinderLO, cylinderRO, cylinderRU];
        this.burningProxies = [];
        for (let o of this.burningObjects) {
            const p = BABYLON.MeshBuilder.CreateBox('bbox', {height: 1, width: 1, depth: 1}, scene);
            p.visibility = false;
            this.burningProxies.push(p);
        }

        if (this.options.canBurn) {
            this.fire = [
                new Fire(this.burningProxies[0], this.scene, 3),
                new Fire(this.burningProxies[1], this.scene, 2),
                new Fire(this.burningProxies[2], this.scene, 2),
                new Fire(this.burningProxies[3], this.scene, 2),
                new Fire(this.burningProxies[4], this.scene, 2),
            ];
        } else {
            this.fire = [];
        }

        this.updateProxies();
    }


    onSample(sample) {
        const pos = sample[this.options.posSignal];
        const quat = sample[this.options.quatSignal];
        const reset = sample[this.options.resetSignal];

        if (this.crashed) {
            if(reset !== this.lastResetVal) {
                console.log('quadcop reset');
                this.crashed = false;
                this.stopFire();
                this.bbox.physicsImpostor.dispose();
            }
        } else if(reset === this.lastResetVal) { // don't update the quadcop pos while reset is active to avoid strange effects
            const quatBabylon = [quat[0], -quat[2], quat[3], -quat[1]];

            const lastPos = this.obj.position;
            this.obj.position = new BABYLON.Vector3(-this.options.scale*pos[1], this.options.scale*pos[2]+this.options.offsetZ, -this.options.scale*pos[0]);
            this.obj.rotationQuaternion = new Quaternion(quatBabylon).babylon();

            this.bbox.computeWorldMatrix(true);

            for (let o of this.options.obstacles) {
                const intersects = this.bbox.intersectsMesh(o, true);
                if (intersects) {
                    console.log('quadcop crashed!');
                    this.crashed = true;
                    this.startFire();
                    this.bbox.physicsImpostor = new BABYLON.PhysicsImpostor(this.bbox, BABYLON.PhysicsImpostor.BoxImpostor, { mass: 10, restitution: 0.5 }, this.scene);

                    const vel = this.obj.position.subtract(lastPos).scale(5);
                    this.bbox.physicsImpostor.setLinearVelocity(vel);
                    break; // only create one impostor!
                }
            }
        }
        this.lastResetVal = reset;
    }

    startFire() {
        this.fire.forEach(function(f) {f.start()});
    }

    stopFire() {
        this.fire.forEach(function(f) {f.stop()});
    }

    updateProxies() {
        for (let i=0; i<this.burningObjects.length; i++) {
            this.burningObjects[i].computeWorldMatrix(true);
            this.burningProxies[i].position = this.burningObjects[i].getAbsolutePosition();
        }
    }
}

class Fire {
    // http://www.html5gamedevs.com/topic/10471-fire-particles/?tab=comments#comment-61447
    // http://www.babylonjs-playground.com/#1DZUBR
    constructor (emitter, scene, scale) {
        //Smoke
        const smokeSystem = new BABYLON.ParticleSystem("particles", 1000, scene);
        smokeSystem.particleTexture = new BABYLON.Texture("lib/textures.json/flare.png", scene);
        smokeSystem.emitter = emitter; // the starting object, the emitter
        smokeSystem.minEmitBox = new BABYLON.Vector3(-scale*0.5, scale*0, -scale*0.5); // Starting all from
        smokeSystem.maxEmitBox = new BABYLON.Vector3(scale*0.5, scale*1, scale*0.5); // To...

        smokeSystem.color1 = new BABYLON.Color4(0.1, 0.1, 0.1, 1.0);
        smokeSystem.color2 = new BABYLON.Color4(0.1, 0.1, 0.1, 1.0);
        smokeSystem.colorDead = new BABYLON.Color4(0, 0, 0, 0.0);

        smokeSystem.minSize = scale*0.3;
        smokeSystem.maxSize = scale*1;

        smokeSystem.minLifeTime = 0.3;
        smokeSystem.maxLifeTime = 1.5;

        smokeSystem.emitRate = 350;

        // Blend mode : BLENDMODE_ONEONE, or BLENDMODE_STANDARD
        smokeSystem.blendMode = BABYLON.ParticleSystem.BLENDMODE_ONEONE;

        smokeSystem.gravity = new BABYLON.Vector3(0, 0, 0);

        smokeSystem.direction1 = new BABYLON.Vector3(-1.5, 8, -1.5).multiply(scale);
        smokeSystem.direction2 = new BABYLON.Vector3(1.5, 8, 1.5).multiply(scale);

        smokeSystem.minAngularSpeed = 0;
        smokeSystem.maxAngularSpeed = Math.PI;

        smokeSystem.minEmitPower = 0.5;
        smokeSystem.maxEmitPower = 1.5;
        smokeSystem.updateSpeed = 0.005;

        this.smokeSystem = smokeSystem;


        // Create a particle system
        const fireSystem = new BABYLON.ParticleSystem("particles", 2000, scene);

        //Texture of each particle
        fireSystem.particleTexture = new BABYLON.Texture("lib/textures.json/flare.png", scene);

        // Where the particles come from
        fireSystem.emitter = emitter; // the starting object, the emitter
        fireSystem.minEmitBox = new BABYLON.Vector3(-scale*0.5, scale*0, -scale*0.5); // Starting all from
        fireSystem.maxEmitBox = new BABYLON.Vector3(scale*0.5, scale*1, scale*0.5); // To...

        // Colors of all particles
        fireSystem.color1 = new BABYLON.Color4(1, 0.5, 0, 1.0);
        fireSystem.color2 = new BABYLON.Color4(1, 0.5, 0, 1.0);
        fireSystem.colorDead = new BABYLON.Color4(0, 0, 0, 0.0);

        // Size of each particle (random between...
        fireSystem.minSize = scale*0.3;
        fireSystem.maxSize = scale*1;

        // Life time of each particle (random between...
        fireSystem.minLifeTime = 0.2;
        fireSystem.maxLifeTime = 0.4;

        // Emission rate
        fireSystem.emitRate = 600;

        // Blend mode : BLENDMODE_ONEONE, or BLENDMODE_STANDARD
        fireSystem.blendMode = BABYLON.ParticleSystem.BLENDMODE_ONEONE;

        // Set the gravity of all particles
        fireSystem.gravity = new BABYLON.Vector3(0, 0, 0);

        // Direction of each particle after it has been emitted
        fireSystem.direction1 = new BABYLON.Vector3(0, scale*4, 0);
        fireSystem.direction2 = new BABYLON.Vector3(0, scale*4, 0);

        // Angular speed, in radians
        fireSystem.minAngularSpeed = 0;
        fireSystem.maxAngularSpeed = Math.PI;

        // Speed
        fireSystem.minEmitPower = 1;
        fireSystem.maxEmitPower = 3;
        fireSystem.updateSpeed = 0.007;
        this.fireSystem = fireSystem;

    }

    start() {
        this.fireSystem.start();
        this.smokeSystem.start();
    }

    stop() {
        this.fireSystem.stop();
        this.smokeSystem.stop();
    }
}
