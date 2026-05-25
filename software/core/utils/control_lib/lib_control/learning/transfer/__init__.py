"""Transfer-learning utilities (input transfer error metrics, one-shot transfer, ...)."""
from .transfer import (
    deployment_error,
    deployment_error_norm,
    output_normalized_error,
    identity_normalized_error,
    transfer_polarity,
)
from .oneshot import (
    biproper_impulse_response,
    apply_transfer,
    fit_biproper_lti,
    fit_full_lttm,
    deconvolve_output_transfer,
    hankel_singular_values,
    estimate_order,
    transferability_index,
    task_weight_matrix,
    deployment_error_bound,
)

__all__ = [
    # transfer error metrics
    "deployment_error",
    "deployment_error_norm",
    "output_normalized_error",
    "identity_normalized_error",
    "transfer_polarity",
    # one-shot input transfer learning
    "biproper_impulse_response",
    "apply_transfer",
    "fit_biproper_lti",
    "fit_full_lttm",
    "deconvolve_output_transfer",
    "hankel_singular_values",
    "estimate_order",
    "transferability_index",
    "task_weight_matrix",
    "deployment_error_bound",
]
