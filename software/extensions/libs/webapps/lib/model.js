/**
 * Physical model parameters for BILBO robots.
 *
 * Matches the Python BilboModel dataclass from bilbo_model.py.
 */

export class BilboModel {
    /**
     * @param {object} params
     * @param {number} params.m_b       Body mass [kg]
     * @param {number} params.m_w       Wheel mass [kg]
     * @param {number} params.l         Center of gravity height [m]
     * @param {number} params.d_w       Distance between wheels [m]
     * @param {number} params.I_w       Wheel moment of inertia [kg·m²]
     * @param {number} params.I_y       Body pitch inertia [kg·m²]
     * @param {number} params.I_x       Body roll inertia [kg·m²]
     * @param {number} params.I_z       Body yaw inertia [kg·m²]
     * @param {number} params.c_alpha   Drag coefficient (speed-dependent)
     * @param {number} params.r_w       Wheel radius [m]
     * @param {number} params.tau_theta Pitch drag coefficient
     * @param {number} params.tau_x     Speed drag coefficient
     * @param {number} params.max_pitch Max pitch for floor contact [rad]
     */
    constructor(params) {
        this.m_b = params.m_b;
        this.m_w = params.m_w;
        this.l = params.l;
        this.d_w = params.d_w;
        this.I_w = params.I_w;
        this.I_y = params.I_y;
        this.I_x = params.I_x;
        this.I_z = params.I_z;
        this.c_alpha = params.c_alpha;
        this.r_w = params.r_w;
        this.tau_theta = params.tau_theta;
        this.tau_x = params.tau_x;
        this.max_pitch = params.max_pitch;
    }
}

export const DEFAULT_BILBO_MODEL = new BilboModel({
    m_b: 1.2,
    m_w: 0.4,
    l: 0.026,
    d_w: 0.22,
    I_w: 2e-4,
    I_y: 0.005,
    I_x: 0.02,
    I_z: 0.03,
    c_alpha: 4.6302e-4,
    r_w: 0.06,
    tau_theta: 0.4,
    tau_x: 0.25,
    max_pitch: 105 * Math.PI / 180,
});

export const BILBO_MICHAEL_MODEL = new BilboModel({
    m_b: 2.5,
    m_w: 0.636,
    l: 0.026,
    d_w: 0.28,
    I_w: 5.1762e-4,
    I_y: 0.01648,
    I_x: 0.02,
    I_z: 0.03,
    c_alpha: 4.6302e-4,
    r_w: 0.055,
    tau_theta: 0.0,
    tau_x: 0.0,
    max_pitch: 105 * Math.PI / 180,
});

export const BILBO_SMALL = new BilboModel({
    m_b: 1,
    m_w: 0.292,
    l: 0.01,
    d_w: 0.168,
    I_w: 2.773e-4,
    I_y: 0.001,
    I_x: 0.01,
    I_z: 0.03,
    c_alpha: 4.6302e-4,
    r_w: 0.062,
    tau_theta: 0.5,
    tau_x: 0.5,
    max_pitch: 105 * Math.PI / 180,
});
