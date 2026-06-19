"""
Offline NLS parameter fit for IML experiments.

After an IML experiment has identified the (nonparametric) impulse-response
model of the closed-loop balancing system, this module fits the *physical*
BILBO model parameters (e.g. centre-of-gravity height ``l``, body mass ``m_b``,
body inertia ``I_y``) by output-error nonlinear least squares -- mirroring
``projects/SS26_AdaptiveStateFeedback/parameter_identification_ideas.py``.

The fit replays the recorded learning-set inputs through the BILBO 2D
simulation model (with the balancing state-feedback gain applied) and minimises
the mismatch to the measured pitch trajectories over the chosen parameters::

    r(theta) = y_measured - theta_simulated(theta),     theta = (l, m_b, I_y, ...)

solved with ``scipy.optimize.least_squares`` (trust-region). All other model
parameters are held fixed at the supplied ``model``'s values, and the balancing
feedback gain ``K`` is a **required input** held fixed throughout: the data was
recorded under the robot's actual gain, so ``K`` must be that exact gain and is
never re-derived from the (changing) model parameters.

This is the host-side analysis step the IML report points to; it is deliberately
decoupled from the experiment lifecycle so it can be re-run with different
parameter sets, models, or feedback gains.
"""
from __future__ import annotations

import dataclasses
import json

import numpy as np
from scipy.optimize import least_squares

from core.utils.logging_utils import Logger
from robots.bilbo.simulation.model import (
    BilboModel,
    DEFAULT_BILBO_MODEL,
    BILBO_Dynamics_2D,
)

logger = Logger("IML Parameter Fit")


# Reasonable physical bounds and scales for the parameters typically identified.
# (lower, upper, x_scale) per parameter name.
_PARAM_BOUNDS: dict[str, tuple[float, float, float]] = {
    'l':         (1e-3, 0.5, 0.02),
    'm_b':       (0.1, 6.0, 1.0),
    'm_w':       (0.05, 2.0, 0.4),
    'I_y':       (1e-4, 0.1, 0.005),
    'I_x':       (1e-4, 0.2, 0.02),
    'I_z':       (1e-4, 0.2, 0.03),
    'I_w':       (1e-5, 1e-2, 2e-4),
    'c_alpha':   (1e-5, 1e-2, 5e-4),
    'r_w':       (0.02, 0.12, 0.06),
    'tau_theta': (0.0, 5.0, 0.4),
    'tau_x':     (0.0, 5.0, 0.4),
}


@dataclasses.dataclass
class BILBO_ParameterFitResult:
    """Result of an output-error NLS parameter fit.

    Attributes:
        params: Fitted parameter values, keyed by name.
        fitted_model: The nominal model with the fitted parameters applied.
        initial_params: The starting parameter guess, keyed by name.
        success: Whether the optimiser reported convergence.
        cost: Final 0.5 * sum-of-squares cost from least_squares.
        residual_norm: L2 norm of the (unweighted) output residual at the optimum.
        n_samples: Number of residual entries (sum of trajectory lengths).
        covariance: Approx. parameter covariance inv(JᵀJ) when computable, else None.
        std: Per-parameter standard deviation (sqrt of covariance diagonal), else None.
        message: Optimiser status message.
    """
    params: dict[str, float]
    fitted_model: BilboModel
    initial_params: dict[str, float]
    success: bool
    cost: float
    residual_norm: float
    n_samples: int
    covariance: np.ndarray | None = None
    std: dict[str, float] | None = None
    message: str = ""


# === Learning-data extraction =========================================================

def _extract_pairs(experiment_data, max_pairs: int | None = None
                   ) -> list[tuple[np.ndarray, np.ndarray]]:
    """Extract (input, measured_output) pairs from an IML data source.

    Accepts the same source types as :func:`generate_iml_report`: a results
    JSON path, a raw results dict, an ``IML_Results`` dataclass, or a live
    ``IML_Experiment`` proxy. Only trials carrying both ``u`` and ``y`` are used.
    """
    from robots.bilbo.robot.experiment.iml.iml import IML_Results, IML_Experiment

    if isinstance(experiment_data, str):
        with open(experiment_data) as f:
            trials = json.load(f).get('trials', [])
    elif isinstance(experiment_data, IML_Results):
        trials = experiment_data.trials
    elif isinstance(experiment_data, IML_Experiment):
        if experiment_data.results is not None and experiment_data.results.trials:
            trials = experiment_data.results.trials
        else:
            trials = [dataclasses.asdict(t) for t in experiment_data.trials]
    elif isinstance(experiment_data, dict):
        trials = experiment_data.get('trials', [])
    elif isinstance(experiment_data, (list, tuple)):
        trials = list(experiment_data)
    else:
        raise TypeError(f"Unsupported experiment_data type: {type(experiment_data)}")

    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for trial in trials:
        u = trial.get('u') if isinstance(trial, dict) else getattr(trial, 'u', None)
        y = trial.get('y') if isinstance(trial, dict) else getattr(trial, 'y', None)
        if u is None or y is None:
            continue
        u = np.asarray(u, dtype=float)
        y = np.asarray(y, dtype=float)
        n = min(len(u), len(y))
        if n == 0:
            continue
        pairs.append((u[:n], y[:n]))
        if max_pairs is not None and len(pairs) >= max_pairs:
            break
    return pairs


# === Fit ==============================================================================

def fit_bilbo_parameters(
        experiment_data,
        K: np.ndarray,
        *,
        model: BilboModel = DEFAULT_BILBO_MODEL,
        params_to_fit: tuple[str, ...] = ('l', 'm_b', 'I_y'),
        Ts: float = 0.01,
        theta0: dict[str, float] | None = None,
        bounds: dict[str, tuple[float, float]] | None = None,
        max_pairs: int | None = None,
) -> BILBO_ParameterFitResult:
    """Fit BILBO physical parameters from IML learning data by output-error NLS.

    Parameters
    ----------
    experiment_data : str | dict | IML_Results | IML_Experiment | list of pairs
        IML data source (see :func:`_extract_pairs`). Each trial supplies one
        ``(input, measured_pitch)`` pair.
    K : ndarray
        The robot's fixed balancing state-feedback gain, shape ``(1, 4)`` or
        ``(4,)`` for the 2D state ``[s, v, theta, theta_dot]``. **Required** and
        held fixed throughout the fit -- the data was recorded under this exact
        gain, so it must not be re-derived from the (changing) model parameters.
        Pass the same gain the robot balances with.
    model : BilboModel
        Nominal model whose non-fitted parameters are held fixed and whose
        values seed the optimiser (unless ``theta0`` is given).
    params_to_fit : tuple of str
        Names of ``BilboModel`` fields to identify (default ``l, m_b, I_y``).
    Ts : float
        Sampling period of the recorded data (s).
    theta0 : dict, optional
        Initial parameter guess (per name). Defaults to the nominal model's
        values.
    bounds : dict, optional
        Per-parameter ``(lower, upper)`` overrides; defaults from ``_PARAM_BOUNDS``.
    max_pairs : int, optional
        Cap on the number of learning pairs used (for speed).

    Returns
    -------
    BILBO_ParameterFitResult
    """
    pairs = _extract_pairs(experiment_data, max_pairs=max_pairs)
    if not pairs:
        raise ValueError("No (input, output) pairs available for the fit")

    for name in params_to_fit:
        if not hasattr(model, name):
            raise ValueError(f"Unknown model parameter to fit: {name!r}")

    bounds = bounds or {}
    initial_params = {name: float(getattr(model, name)) for name in params_to_fit}
    if theta0:
        initial_params.update({k: float(v) for k, v in theta0.items() if k in initial_params})

    theta0_vec = np.array([initial_params[name] for name in params_to_fit], dtype=float)
    lower = np.array([bounds.get(name, _PARAM_BOUNDS.get(name, (-np.inf, np.inf)))[0]
                      for name in params_to_fit], dtype=float)
    upper = np.array([bounds.get(name, _PARAM_BOUNDS.get(name, (-np.inf, np.inf)))[1]
                      for name in params_to_fit], dtype=float)
    x_scale = np.array([_PARAM_BOUNDS.get(name, (0, 0, 1.0))[2] for name in params_to_fit],
                       dtype=float)
    x_scale = np.where(x_scale > 0, x_scale, 1.0)

    # Fixed feedback gain — the robot's actual balancing gain, held constant.
    if K is None:
        raise ValueError("K (the robot's balancing state-feedback gain) is required")
    K = np.asarray(K, dtype=float).reshape(1, -1)
    if K.shape[1] != 4:
        raise ValueError(
            f"K must have 4 columns for the 2D state [s, v, theta, theta_dot]; "
            f"got shape {K.shape}")

    # Per-channel residual weight from the measured-output RMS (so trajectories
    # of different amplitude contribute comparably).
    weights = [max(float(np.std(y)), 1e-9) for _, y in pairs]

    def _simulate_theta(params_vec: np.ndarray, u: np.ndarray) -> np.ndarray:
        kwargs = {name: float(val) for name, val in zip(params_to_fit, params_vec)}
        m = dataclasses.replace(model, **kwargs)
        dyn = BILBO_Dynamics_2D(m, Ts=Ts)
        dyn.K = K
        states = dyn.simulate(input=u, reset=True, include_zero_step=False)
        theta = np.array([s.theta for s in states], dtype=float)
        # Align to the input length (simulate returns one state per input step).
        n = len(u)
        if len(theta) >= n:
            return theta[:n]
        return np.pad(theta, (0, n - len(theta)), mode='edge')

    def residual(params_vec: np.ndarray) -> np.ndarray:
        chunks = []
        for (u, y), w in zip(pairs, weights):
            theta_sim = _simulate_theta(params_vec, u)
            chunks.append((y - theta_sim) / w)
        r = np.concatenate(chunks)
        # A diverging closed-loop sim (e.g. wrong-sign / unstable K, or a
        # nonphysical parameter excursion) yields inf/nan. Map those to a large
        # finite penalty so least_squares can steer away instead of erroring out
        # with "Residuals are not finite in the initial point".
        if not np.all(np.isfinite(r)):
            r = np.nan_to_num(r, nan=1e6, posinf=1e6, neginf=1e6)
        return r

    logger.info(f"Fitting {list(params_to_fit)} from {len(pairs)} learning pairs "
                f"({sum(len(u) for u, _ in pairs)} samples)...")
    result = least_squares(residual, theta0_vec, bounds=(lower, upper), x_scale=x_scale)

    fitted = {name: float(val) for name, val in zip(params_to_fit, result.x)}
    fitted_model = dataclasses.replace(model, **fitted)

    # Unweighted residual norm at the optimum (interpretable in output units).
    raw_residual = np.concatenate([
        (y - _simulate_theta(result.x, u)) for u, y in pairs])
    residual_norm = float(np.linalg.norm(raw_residual))

    # Approximate parameter covariance from the (weighted) Jacobian.
    covariance = None
    std = None
    try:
        JtJ = result.jac.T @ result.jac
        covariance = np.linalg.inv(JtJ)
        std = {name: float(np.sqrt(max(covariance[i, i], 0.0)))
               for i, name in enumerate(params_to_fit)}
    except np.linalg.LinAlgError:
        logger.warning("Jacobian is singular — covariance not available")

    logger.info(f"Fit {'converged' if result.success else 'did NOT converge'}: "
                f"{fitted}, residual norm {residual_norm:.6f}")

    return BILBO_ParameterFitResult(
        params=fitted,
        fitted_model=fitted_model,
        initial_params=initial_params,
        success=bool(result.success),
        cost=float(result.cost),
        residual_norm=residual_norm,
        n_samples=len(raw_residual),
        covariance=covariance,
        std=std,
        message=str(result.message),
    )


if __name__ == '__main__':
    # Example: fit (l, m_b, I_y) from a results JSON under the robot's balancing
    # gain K. Replace K with the gain the robot actually balances with.
    import sys
    if len(sys.argv) > 1:
        K = np.array([[0.0, -0.8, -2.5, -0.3]])  # placeholder — use the real gain
        res = fit_bilbo_parameters(sys.argv[1], K)
        print(res)
