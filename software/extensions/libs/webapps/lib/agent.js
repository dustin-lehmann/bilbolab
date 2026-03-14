/**
 * Complete BILBO simulation agent.
 *
 * Combines dynamics, balancing (eigenstructure assignment), velocity PID,
 * and position control into a single self-contained agent — matching the
 * Python BILBO_CompleteAgent from bilbo_complete_agent.py.
 *
 * Control hierarchy:
 *   Position Control -> (vCmd, psiDotCmd)
 *     -> Velocity PID -> [uL, uR]
 *       -> Balancing (K @ state) -> Motor Torques
 *         -> Nonlinear Dynamics
 */

import { BilboDynamics3D } from './dynamics.js';
import { bilboEigenstructureAssignment, DEFAULT_POLES, DEFAULT_EIGENVECTORS } from './control.js';
import { VelocityController, VelocityControllerConfig } from './velocity.js';
import { PositionControl, PositionControlConfig } from './position.js';
import { DEFAULT_BILBO_MODEL } from './model.js';

// Control modes matching firmware BILBO_Control_Mode enum
export const MODE_OFF = 0;
export const MODE_DIRECT = 1;
export const MODE_BALANCING = 2;
export const MODE_VELOCITY = 3;
export const MODE_POSITION = 4;


export class BilboAgent {
    /**
     * @param {object} [options]
     * @param {BilboModel} [options.model]
     * @param {number} [options.Ts=0.01]
     * @param {number[]} [options.x0] - Initial state [x, y, v, theta, theta_dot, psi, psi_dot]
     * @param {Array} [options.poles] - Eigenstructure poles (6 complex numbers)
     * @param {number[][]} [options.eigenvectors] - 6×6 eigenvector constraints
     * @param {VelocityControllerConfig} [options.velocityConfig]
     * @param {PositionControlConfig} [options.positionConfig]
     */
    constructor(options = {}) {
        const model = options.model || DEFAULT_BILBO_MODEL;
        const Ts = options.Ts || 0.01;
        const x0 = options.x0 || null;

        this.model = model;
        this.Ts = Ts;
        this.mode = MODE_OFF;

        // Dynamics
        this.dynamics = new BilboDynamics3D(model, Ts, x0);

        // Eigenstructure assignment for balancing
        const poles = options.poles || DEFAULT_POLES;
        const eigenvectors = options.eigenvectors || DEFAULT_EIGENVECTORS;
        this.K = bilboEigenstructureAssignment(model, poles, eigenvectors);

        // Velocity controller
        this.velocityController = new VelocityController(Ts, options.velocityConfig || null);
        this.velocityCommand = { v: 0, psiDot: 0 };
        this.velocityOutput = [0, 0];

        // Position controller
        const posCfg = options.positionConfig || new PositionControlConfig({ Ts });
        this.positionControl = new PositionControl(posCfg);
        this._positionControlWasIdle = true;
        this._pendingHeading = null;

        // External input (for BALANCING/DIRECT mode)
        this.input = [0, 0]; // [M_L, M_R]

        // Trajectory playback
        this._trajectory = null;  // Array of [uLeft, uRight]
        this._trajectoryIndex = 0;

        // Callbacks
        this.onTrajectoryFinished = null;
        this.onPositionFinished = null;

        // Wire position control callbacks
        this.positionControl.onPathFinished = () => this._onPositionFinished();
        this.positionControl.onMoveCompleted = () => this._onPositionFinished();
        this.positionControl.onTurnCompleted = () => this._onPositionFinished();
    }

    // === State accessors ===

    get state() { return this.dynamics.state; }
    set state(v) { this.dynamics.state = [...v]; }
    get x()         { return this.dynamics.x; }
    get y()         { return this.dynamics.y; }
    get v()         { return this.dynamics.v; }
    get theta()     { return this.dynamics.theta; }
    get thetaDot()  { return this.dynamics.thetaDot; }
    get psi()       { return this.dynamics.psi; }
    get psiDot()    { return this.dynamics.psiDot; }

    // === Mode management ===

    setMode(mode) {
        if (mode === MODE_VELOCITY) this.velocityController.reset();
        if (mode === MODE_POSITION) this.positionControl.reset();
        this.mode = mode;
    }

    // === Velocity commands ===

    setVelocity(v, psiDot) {
        this.velocityCommand.v = v;
        this.velocityCommand.psiDot = psiDot;
    }

    // === Position commands ===

    moveToPoint(x, y, { timeout = 0, maxSpeed = 0, targetHeading = null } = {}) {
        this.positionControl.reset();
        this.velocityController.reset();
        this._pendingHeading = null;

        this.positionControl.moveToPoint(x, y, timeout, maxSpeed);

        if (targetHeading !== null) this._pendingHeading = targetHeading;
        this._positionControlWasIdle = false;
        this.mode = MODE_POSITION;
    }

    turnToHeading(psi, timeout = 0) {
        this.positionControl.reset();
        this.velocityController.reset();
        this.positionControl.turnToHeading(psi, timeout);
        this._positionControlWasIdle = false;
        this.mode = MODE_POSITION;
    }

    /**
     * Follow a path of dense waypoints.
     * @param {number[][]} waypoints - Array of [x, y]
     * @param {object} [options]
     */
    followPath(waypoints, { maxSpeed = 0, allowReverse = false, timeout = 0, stopIndices = null } = {}) {
        this.positionControl.reset();
        this.velocityController.reset();

        this.positionControl.setPath(waypoints, stopIndices);
        this.positionControl.startPath({ maxSpeed, allowReverse, timeout });
        this._positionControlWasIdle = false;
        this.mode = MODE_POSITION;
    }

    // === Trajectory playback ===

    /**
     * Play back a torque trajectory in BALANCING mode.
     * @param {number[][]} trajectory - Array of [uLeft, uRight]
     */
    runTrajectory(trajectory) {
        this._trajectory = trajectory;
        this._trajectoryIndex = 0;
        this.mode = MODE_BALANCING;
    }

    abortTrajectory() {
        this._trajectory = null;
        this._trajectoryIndex = 0;
        this.input = [0, 0];
    }

    get isTrajectoryRunning() { return this._trajectory !== null; }

    // === Main step ===

    /**
     * Advance the simulation by one timestep.
     * Runs the full control hierarchy and dynamics integration.
     * @returns {number[]} The new state
     */
    step() {
        const controlInput = this._controller();
        this.dynamics.step(controlInput);
        return this.dynamics.state;
    }

    /**
     * Run multiple steps.
     * @param {number} n - Number of steps
     * @returns {number[][]} Array of states (including initial)
     */
    simulate(n) {
        const states = [this.dynamics.state.slice()];
        for (let i = 0; i < n; i++) {
            this.step();
            states.push(this.dynamics.state.slice());
        }
        return states;
    }

    // === Reset ===

    reset(x0 = null) {
        this.dynamics.reset(x0);
        this.velocityController.reset();
        this.velocityCommand = { v: 0, psiDot: 0 };
        this.velocityOutput = [0, 0];
        this.positionControl.reset();
        this._pendingHeading = null;
        this._trajectory = null;
        this._trajectoryIndex = 0;
        this.input = [0, 0];
        this.mode = MODE_OFF;
    }

    // === Controller (internal) ===

    _controller() {
        if (this.mode === MODE_OFF) {
            return [0, 0];
        }

        if (this.mode === MODE_DIRECT) {
            return [...this.input];
        }

        if (this.mode === MODE_BALANCING) {
            // Advance trajectory playback
            if (this._trajectory) {
                if (this._trajectoryIndex < this._trajectory.length) {
                    this.input = [...this._trajectory[this._trajectoryIndex]];
                    this._trajectoryIndex++;
                } else {
                    this.input = [0, 0];
                    this._trajectory = null;
                    this._trajectoryIndex = 0;
                    if (this.onTrajectoryFinished) this.onTrajectoryFinished();
                }
            }

            // u = input - K * state
            const Kx = this.K.mulVec(this.dynamics.state);
            return [this.input[0] - Kx[0], this.input[1] - Kx[1]];
        }

        if (this.mode === MODE_VELOCITY) {
            this.velocityOutput = this.velocityController.update(
                this.velocityCommand.v, this.velocityCommand.psiDot,
                this.dynamics.v, this.dynamics.psiDot
            );
            const Kx = this.K.mulVec(this.dynamics.state);
            return [this.velocityOutput[0] - Kx[0], this.velocityOutput[1] - Kx[1]];
        }

        if (this.mode === MODE_POSITION) {
            const state = this.dynamics;

            // Chain turn after move/path
            if (this.positionControl.isIdle && this._pendingHeading !== null) {
                const heading = this._pendingHeading;
                this._pendingHeading = null;
                this.positionControl.turnToHeading(heading);
                this._positionControlWasIdle = false;
            }

            if (this.positionControl.isIdle) {
                if (!this._positionControlWasIdle) {
                    this.velocityCommand = { v: 0, psiDot: 0 };
                    this.velocityController.reset();
                    this._positionControlWasIdle = true;
                }
                // Hold position via pure balancing
                const Kx = this.K.mulVec(this.dynamics.state);
                return [this.input[0] - Kx[0], this.input[1] - Kx[1]];
            }

            this._positionControlWasIdle = false;
            const posOut = this.positionControl.update(state.x, state.y, state.psi, state.v);
            this.velocityCommand.v = posOut.vCmd;
            this.velocityCommand.psiDot = posOut.psiDotCmd;

            this.velocityOutput = this.velocityController.update(
                this.velocityCommand.v, this.velocityCommand.psiDot,
                this.dynamics.v, this.dynamics.psiDot
            );
            const Kx = this.K.mulVec(this.dynamics.state);
            return [this.velocityOutput[0] - Kx[0], this.velocityOutput[1] - Kx[1]];
        }

        return [0, 0];
    }

    _onPositionFinished() {
        if (this.onPositionFinished) this.onPositionFinished();
    }
}
