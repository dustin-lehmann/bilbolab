/*
 * ekf.cpp
 *
 *  Created on: Dec 19, 2025
 *      Author: tizianohumpert
 */

#include "ekf.h"
#include <math.h>

/* Sampling time */
static const float Ts = 0.01f;

/* Process noise Q */
static const float Q[3][3] = {
    {0.01f, 0.0f,  0.0f},
    {0.0f,  0.01f, 0.0f},
    {0.0f,  0.0f,  0.001f}
};

/* Measurement noise R */
static const float R[2][2] = {
    {0.05f, 0.0f},
    {0.0f,  0.05f}
};

/* Persistent EKF state */
static ekf_state_t x = {0.0f, 0.0f, 0.0f};
static float P[3][3] = {
    {1.0f, 0.0f, 0.0f},
    {0.0f, 1.0f, 0.0f},
    {0.0f, 0.0f, 0.1f}
};

static bool initialized = false;

void ekf_robot_update(float v,
                      float psi_dot,
                      const float z[2],
                      bool meas_valid,
                      ekf_state_t *x_hat)
{
    if (!initialized) {
        initialized = true;
    }

    /* =========================
       1) PREDICTION
       ========================= */

    float psi = x.psi;
    float c = cosf(psi);
    float s = sinf(psi);

    /* State prediction */
    ekf_state_t x_pred;
    x_pred.x   = x.x   + Ts * v * c;
    x_pred.y   = x.y   + Ts * v * s;
    x_pred.psi = x.psi + Ts * psi_dot;

    /* Jacobian A */
    float A[3][3] = {
        {1.0f, 0.0f, -Ts * v * s},
        {0.0f, 1.0f,  Ts * v * c},
        {0.0f, 0.0f,  1.0f}
    };

    /* P_pred = A * P * A' + Q */
    float AP[3][3] = {0};
    float P_pred[3][3] = {0};

    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++)
            for (int k = 0; k < 3; k++)
                AP[i][j] += A[i][k] * P[k][j];

    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) {
            for (int k = 0; k < 3; k++)
                P_pred[i][j] += AP[i][k] * A[j][k];
            P_pred[i][j] += Q[i][j];
        }

    /* =========================
       2) CORRECTION
       ========================= */

    if (meas_valid) {
        /* Innovation y = z - H*x_pred */
        float y[2] = {
            z[0] - x_pred.x,
            z[1] - x_pred.y
        };

        /* S = H*P*H' + R */
        float S[2][2] = {
            {P_pred[0][0] + R[0][0], P_pred[0][1]},
            {P_pred[1][0], P_pred[1][1] + R[1][1]}
        };

        /* Inverse of S */
        float detS = S[0][0]*S[1][1] - S[0][1]*S[1][0];
        float invS[2][2] = {
            { S[1][1]/detS, -S[0][1]/detS },
            { -S[1][0]/detS, S[0][0]/detS }
        };

        /* Kalman gain K = P_pred * H' * inv(S) */
        float K[3][2];
        for (int i = 0; i < 3; i++) {
            K[i][0] = P_pred[i][0] * invS[0][0] + P_pred[i][1] * invS[1][0];
            K[i][1] = P_pred[i][0] * invS[0][1] + P_pred[i][1] * invS[1][1];
        }

        /* State update */
        x.x   = x_pred.x   + K[0][0]*y[0] + K[0][1]*y[1];
        x.y   = x_pred.y   + K[1][0]*y[0] + K[1][1]*y[1];
        x.psi = x_pred.psi + K[2][0]*y[0] + K[2][1]*y[1];

        /* Joseph-form covariance update */
        float I_KH[3][3] = {
            {1.0f - K[0][0], -K[0][1], 0.0f},
            {-K[1][0], 1.0f - K[1][1], 0.0f},
            {-K[2][0], -K[2][1], 1.0f}
        };

        float temp[3][3] = {0};
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                for (int k = 0; k < 3; k++)
                    temp[i][j] += I_KH[i][k] * P_pred[k][j];

        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++) {
                P[i][j] = 0.0f;
                for (int k = 0; k < 3; k++)
                    P[i][j] += temp[i][k] * I_KH[j][k];
            }

    } else {
        x = x_pred;
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                P[i][j] = P_pred[i][j];
    }

    *x_hat = x;
}


