/**
 * BilboLab JS Library
 *
 * Modular JavaScript port of the BILBO simulation and control stack.
 * Designed for reuse across multiple webapps.
 *
 * Modules:
 *   - linalg:    Lightweight matrix/vector math (no dependencies)
 *   - model:     Physical robot parameters and default models
 *   - dynamics:  Nonlinear and linearized 3D dynamics (Euler integration)
 *   - control:   Eigenstructure assignment, pole placement, state feedback
 *   - velocity:  Velocity PID controller (v + psi_dot)
 *   - position:  Position control (turn-to-heading, drive-to-point, follow-path)
 *   - agent:     Complete simulation agent combining all layers
 */

export { Matrix, vec, eye, zeros, inv, eig, expm, complexMul, complexAdd } from './linalg.js';
export { BilboModel, DEFAULT_BILBO_MODEL, BILBO_MICHAEL_MODEL, BILBO_SMALL } from './model.js';
export {
    BilboDynamics3D,
    BilboDynamics3DLinearReduced,
    linearizeReduced,
    linearizeFull,
    c2d,
} from './dynamics.js';
export {
    eigenstructureAssignment,
    polePlacement2D,
    dlqr,
    DEFAULT_POLES,
    DEFAULT_EIGENVECTORS,
} from './control.js';
export { VelocityController, VelocityControllerConfig } from './velocity.js';
export { PositionControl, PositionControlConfig } from './position.js';
export {
    BilboAgent,
    MODE_OFF,
    MODE_DIRECT,
    MODE_BALANCING,
    MODE_VELOCITY,
    MODE_POSITION,
} from './agent.js';
export { bilboEigenstructureAssignment } from './control.js';
export { normalizeAngle, clamp, deg2rad, rad2deg } from './utils.js';
