/**
 * BILBO dynamics: nonlinear 3D, linearized 3D (reduced and full), and c2d conversion.
 *
 * State vector (7): [x, y, v, theta, theta_dot, psi, psi_dot]
 * Reduced state (6): [s, v, theta, theta_dot, psi, psi_dot]
 * Input (2): [M_L, M_R]
 */

import { Matrix, eye, zeros, inv, expm } from './linalg.js';

const g = 9.81;
const DEFAULT_TS = 0.01;


// =====================================================================================================================
// Helper: compute common dynamics coefficients from model parameters
// =====================================================================================================================

function _coefficients(model) {
    const { m_b, m_w, l, d_w, I_w, I_y, I_x, I_z, c_alpha, r_w } = model;

    const C_21 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * m_b * l;
    const V_1  = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * (I_y + m_b * l ** 2) - m_b ** 2 * l ** 2;
    const D_22 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * 2 * c_alpha + m_b * l * 2 * c_alpha / r_w;
    const D_21 = (m_b + 2 * m_w + 2 * I_w / r_w ** 2) * 2 * c_alpha / r_w + m_b * l * 2 * c_alpha / r_w ** 2;
    const C_11 = m_b ** 2 * l ** 2;
    const D_12 = (I_y + m_b * l ** 2) * 2 * c_alpha / r_w - m_b * l * 2 * c_alpha;
    const D_11 = (I_y + m_b * l ** 2) * 2 * c_alpha / r_w ** 2 - m_b * l * 2 * c_alpha / r_w;
    const D_33 = d_w ** 2 / (2 * r_w ** 2) * c_alpha;
    const V_2  = I_z + 2 * I_w + (m_w + I_w / r_w ** 2) * d_w ** 2 / 2;
    const B_1  = (I_y + m_b * l ** 2) / r_w + m_b * l;
    const B_2  = m_b * l / r_w + m_b + 2 * m_w + 2 * I_w / r_w ** 2;
    const B_3  = d_w / (2 * r_w);

    return { C_21, V_1, D_22, D_21, C_11, D_12, D_11, D_33, V_2, B_1, B_2, B_3 };
}


// =====================================================================================================================
// Linearized continuous-time models
// =====================================================================================================================

/**
 * Linearized reduced (6-state) continuous-time model.
 * State: [s, v, theta, theta_dot, psi, psi_dot]
 * Returns { A: Matrix(6,6), B: Matrix(6,2), C: Matrix(1,6), D: Matrix(1,2) }
 */
export function linearizeReduced(model) {
    const { C_21, V_1, D_22, D_21, C_11, D_12, D_11, D_33, V_2, B_1, B_2, B_3 } = _coefficients(model);

    const A = Matrix.from2D([
        [0, 1, 0, 0, 0, 0],
        [0, -D_11 / V_1, -C_11 * g / V_1, D_12 / V_1, 0, 0],
        [0, 0, 0, 1, 0, 0],
        [0, D_21 / V_1, C_21 * g / V_1, -D_22 / V_1, 0, 0],
        [0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, -D_33 / V_2],
    ]);

    const B = Matrix.from2D([
        [0, 0],
        [B_1 / V_1, B_1 / V_1],
        [0, 0],
        [-B_2 / V_1, -B_2 / V_1],
        [0, 0],
        [-B_3 / V_2, B_3 / V_2],
    ]);

    const C = Matrix.from2D([[0, 0, 1, 0, 0, 0]]);
    const D = Matrix.from2D([[0, 0]]);

    return { A, B, C, D };
}


/**
 * Linearized full (7-state) continuous-time model.
 * State: [x, y, v, theta, theta_dot, psi, psi_dot]
 * Linearized around (v0, psi0).
 */
export function linearizeFull(model, v0 = 0, psi0 = 0) {
    const { C_21, V_1, D_22, D_21, C_11, D_12, D_11, D_33, V_2, B_1, B_2, B_3 } = _coefficients(model);

    const cosPsi = Math.cos(psi0);
    const sinPsi = Math.sin(psi0);

    const A = zeros(7, 7);
    // Kinematics
    A.set(0, 2, cosPsi);            // dx/dt depends on v
    A.set(0, 5, -v0 * sinPsi);      // dx/dt depends on psi
    A.set(1, 2, sinPsi);            // dy/dt depends on v
    A.set(1, 5, v0 * cosPsi);       // dy/dt depends on psi
    // v dynamics
    A.set(2, 2, -D_11 / V_1);
    A.set(2, 3, -C_11 * g / V_1);
    A.set(2, 4, D_12 / V_1);
    // theta kinematics
    A.set(3, 4, 1.0);
    // theta_dot dynamics
    A.set(4, 2, D_21 / V_1);
    A.set(4, 3, C_21 * g / V_1);
    A.set(4, 4, -D_22 / V_1);
    // psi kinematics
    A.set(5, 6, 1.0);
    // psi_dot dynamics
    A.set(6, 6, -D_33 / V_2);

    const B = zeros(7, 2);
    B.set(2, 0, B_1 / V_1); B.set(2, 1, B_1 / V_1);
    B.set(4, 0, -B_2 / V_1); B.set(4, 1, -B_2 / V_1);
    B.set(6, 0, -B_3 / V_2); B.set(6, 1, B_3 / V_2);

    const C = Matrix.from2D([[0, 0, 0, 1, 0, 0, 0]]);
    const D = Matrix.from2D([[0, 0]]);

    return { A, B, C, D };
}


/**
 * Continuous-to-discrete conversion using zero-order hold.
 * Uses matrix exponential: Ad = expm(A*Ts), Bd = A^{-1}(Ad - I)*B
 *
 * For singular A, uses the block matrix exponential method:
 *   expm([[A, B], [0, 0]] * Ts) = [[Ad, Bd], [0, I]]
 */
export function c2d(Ac, Bc, Ts) {
    const n = Ac.rows;
    const m = Bc.cols;

    // Build block matrix: [[A*Ts, B*Ts], [0, 0]]
    const block = zeros(n + m, n + m);
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) block.set(i, j, Ac.get(i, j) * Ts);
        for (let j = 0; j < m; j++) block.set(i, n + j, Bc.get(i, j) * Ts);
    }

    const E = expm(block);

    const Ad = new Matrix(n, n);
    const Bd = new Matrix(n, m);
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) Ad.set(i, j, E.get(i, j));
        for (let j = 0; j < m; j++) Bd.set(i, n + j, E.get(i, n + j));
    }

    // Fix: extract Bd from the right columns of E
    for (let i = 0; i < n; i++)
        for (let j = 0; j < m; j++)
            Bd.set(i, j, E.get(i, n + j));

    return { Ad, Bd };
}


// =====================================================================================================================
// Linearized reduced dynamics (discrete-time, with eigenstructure assignment)
// =====================================================================================================================

export class BilboDynamics3DLinearReduced {
    /**
     * @param {BilboModel} model
     * @param {number} [Ts=0.01]
     */
    constructor(model, Ts = DEFAULT_TS) {
        this.model = model;
        this.Ts = Ts;

        const { A, B, C, D } = linearizeReduced(model);
        this._Ac = A;
        this._Bc = B;

        const disc = c2d(A, B, Ts);
        this.Ad = disc.Ad;
        this.Bd = disc.Bd;

        this.K = null;

        // State: [s, v, theta, theta_dot, psi, psi_dot]
        this.state = [0, 0, 0, 0, 0, 0];
    }

    /** Set state feedback gain K (2×6). */
    setK(K) {
        this.K = K;
    }

    /** Step the discrete-time dynamics. input = [M_L, M_R]. */
    step(input) {
        let u = input;
        if (this.K) {
            const Kx = this.K.mulVec(this.state);
            u = [input[0] - Kx[0], input[1] - Kx[1]];
        }
        const Ax = this.Ad.mulVec(this.state);
        const Bu = this.Bd.mulVec(u);
        this.state = Ax.map((v, i) => v + Bu[i]);
        return this.state;
    }

    reset() {
        this.state = [0, 0, 0, 0, 0, 0];
    }
}


// =====================================================================================================================
// Nonlinear 3D dynamics (Euler integration)
// =====================================================================================================================

export class BilboDynamics3D {
    /**
     * @param {BilboModel} model
     * @param {number} [Ts=0.01]
     * @param {number[]} [x0] - Initial state [x, y, v, theta, theta_dot, psi, psi_dot]
     */
    constructor(model, Ts = DEFAULT_TS, x0 = null) {
        this.model = model;
        this.Ts = Ts;
        this.K = null;

        // State: [x, y, v, theta, theta_dot, psi, psi_dot]
        this.state = x0 ? [...x0] : [0, 0, 0, 0, 0, 0, 0];

        // Ground contact state
        this._groundContact = false;
        this._prevPose = { x: this.state[0], y: this.state[1], psi: this.state[5] };
    }

    /** Set state feedback gain K (2×7). */
    setK(K) {
        this.K = K;
    }

    /** Named state accessors */
    get x()         { return this.state[0]; }
    get y()         { return this.state[1]; }
    get v()         { return this.state[2]; }
    get theta()     { return this.state[3]; }
    get thetaDot()  { return this.state[4]; }
    get psi()       { return this.state[5]; }
    get psiDot()    { return this.state[6]; }

    /**
     * Step the nonlinear dynamics. input = [M_L, M_R].
     * Returns the state after integration.
     */
    step(input) {
        const m = this.model;
        const [x, y, v, theta, theta_dot, psi, psi_dot] = this.state;

        // Apply state feedback if set
        let u0 = input[0], u1 = input[1];
        if (this.K) {
            const Kx = this.K.mulVec(this.state);
            u0 -= Kx[0];
            u1 -= Kx[1];
        }

        const cosTheta = Math.cos(theta);
        const sinTheta = Math.sin(theta);

        // Nonlinear coefficients (theta-dependent)
        const C_12 = (m.I_y + m.m_b * m.l ** 2) * m.m_b * m.l;
        const C_22 = m.m_b ** 2 * m.l ** 2 * cosTheta;
        const C_21 = (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * m.m_b * m.l;
        const V_1  = (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * (m.I_y + m.m_b * m.l ** 2) - m.m_b ** 2 * m.l ** 2 * cosTheta ** 2;
        const D_22 = (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * 2 * m.c_alpha + m.m_b * m.l * cosTheta * 2 * m.c_alpha / m.r_w;
        const D_21 = (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * 2 * m.c_alpha / m.r_w + m.m_b * m.l * cosTheta * 2 * m.c_alpha / m.r_w ** 2;
        const C_11 = m.m_b ** 2 * m.l ** 2 * cosTheta;
        const D_12 = (m.I_y + m.m_b * m.l ** 2) * 2 * m.c_alpha / m.r_w - m.m_b * m.l * cosTheta * 2 * m.c_alpha;
        const D_11 = (m.I_y + m.m_b * m.l ** 2) * 2 * m.c_alpha / m.r_w ** 2 - 2 * m.m_b * m.l * cosTheta * m.c_alpha / m.r_w;
        const B_2  = m.m_b * m.l / m.r_w * cosTheta + m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2;
        const B_1  = (m.I_y + m.m_b * m.l ** 2) / m.r_w + m.m_b * m.l * cosTheta;
        const C_31 = 2 * (m.I_z - m.I_x - m.m_b * m.l ** 2) * cosTheta;
        const C_32 = m.m_b * m.l;
        const D_33 = m.d_w ** 2 / (2 * m.r_w ** 2) * m.c_alpha;
        const V_2  = m.I_z + 2 * m.I_w + (m.m_w + m.I_w / m.r_w ** 2) * m.d_w ** 2 / 2 - (m.I_z - m.I_x - m.m_b * m.l ** 2) * sinTheta ** 2;
        const B_3  = m.d_w / (2 * m.r_w);
        const C_13 = (m.I_y + m.m_b * m.l ** 2) * m.m_b * m.l + m.m_b * m.l * (m.I_z - m.I_x - m.m_b * m.l ** 2) * cosTheta ** 2;
        const C_23 = (m.m_b ** 2 * m.l ** 2 + (m.m_b + 2 * m.m_w + 2 * m.I_w / m.r_w ** 2) * (m.I_z - m.I_x - m.m_b * m.l ** 2)) * cosTheta;

        const uSum = u0 + u1;
        const uDiff = u0 - u1;

        // State derivatives
        const dx = v * Math.cos(psi);
        const dy = v * Math.sin(psi);
        const dv = (sinTheta / V_1) * (-C_11 * g + C_12 * theta_dot ** 2 + C_13 * psi_dot ** 2)
                 - (D_11 / V_1) * v + (D_12 / V_1) * theta_dot + (B_1 / V_1) * uSum - m.tau_x * v;
        const dtheta = theta_dot;
        const dtheta_dot = (sinTheta / V_1) * (C_21 * g - C_22 * theta_dot ** 2 - C_23 * psi_dot ** 2)
                         + (D_21 / V_1) * v - (D_22 / V_1) * theta_dot - (B_2 / V_1) * uSum - m.tau_theta * theta_dot;
        const dpsi = psi_dot;
        const dpsi_dot = (sinTheta / V_2) * (C_31 * theta_dot * psi_dot - C_32 * psi_dot * v)
                       - (D_33 / V_2) * psi_dot - (B_3 / V_2) * uDiff;

        // Euler integration
        this.state = [
            x + dx * this.Ts,
            y + dy * this.Ts,
            v + dv * this.Ts,
            theta + dtheta * this.Ts,
            theta_dot + dtheta_dot * this.Ts,
            psi + dpsi * this.Ts,
            psi_dot + dpsi_dot * this.Ts,
        ];

        // Apply ground contact constraints
        this._applyGroundConstraints();

        return this.state;
    }

    /** Simulate over a sequence of inputs. Returns array of states. */
    simulate(inputs, x0 = null) {
        if (x0) this.state = [...x0];
        const states = [this.state.slice()];
        for (const inp of inputs) {
            this.step(inp);
            states.push(this.state.slice());
        }
        return states;
    }

    reset(x0 = null) {
        this.state = x0 ? [...x0] : [0, 0, 0, 0, 0, 0, 0];
        this._groundContact = false;
        this._prevPose = { x: this.state[0], y: this.state[1], psi: this.state[5] };
    }

    // === Ground contact constraints (matches Python _calculateStateConstraints) ===

    _applyGroundConstraints() {
        const dt = this.Ts;
        const maxPitch = this.model.max_pitch;
        const tolEnter = 1e-4;
        const tolExit = 2e-4;
        const eN = 0.0;      // normal restitution
        const kT = 12.0;     // v decay rate
        const kR = 10.0;     // psi_dot decay rate
        const vStick = 5e-3;
        const wStick = 5e-3;

        let [x, y, v, theta, theta_dot, psi, psi_dot] = this.state;

        const side = theta >= 0 ? 1.0 : -1.0;
        const depth = Math.abs(theta) - maxPitch;
        const approaching = (theta_dot * side) > 0;

        if (depth > 0 || (Math.abs(Math.abs(theta) - maxPitch) <= tolEnter && approaching)) {
            this._groundContact = true;
        } else if (Math.abs(Math.abs(theta) - maxPitch) > tolExit && !approaching) {
            this._groundContact = false;
        }

        let sticking = false;

        if (this._groundContact) {
            theta = side * maxPitch;
            if (approaching) theta_dot = -eN * theta_dot;
            if (Math.abs(theta_dot) < wStick) theta_dot = 0;

            v *= Math.exp(-kT * dt);
            psi_dot *= Math.exp(-kR * dt);

            if (Math.abs(v) < vStick) v = 0;
            if (Math.abs(psi_dot) < wStick) psi_dot = 0;

            sticking = (v === 0 && psi_dot === 0);

            if (sticking) {
                x = this._prevPose.x;
                y = this._prevPose.y;
                psi = this._prevPose.psi;
            }
        } else if (depth > 0) {
            theta = side * maxPitch;
            if (approaching) theta_dot = -eN * theta_dot;
        }

        this.state = [x, y, v, theta, theta_dot, psi, psi_dot];
        this._prevPose = { x, y, psi };
    }
}
