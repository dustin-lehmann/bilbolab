/*
 * ekf.h
 *
 *  Created on: Dec 19, 2025
 *      Author: tizianohumpert
 */

#ifndef CONTROL_EKF_H_
#define CONTROL_EKF_H_

#ifndef EKF_ROBOT_H
#define EKF_ROBOT_H

#include <stdbool.h>

typedef struct {
    float x;
    float y;
    float psi;
} ekf_state_t;

void ekf_robot_update(float v,
                      float psi_dot,
                      const float z[2],
                      bool meas_valid,
                      ekf_state_t *x_hat);

#endif




#endif /* CONTROL_EKF_H_ */
