"""One-shot input transfer learning.

Library implementation of the one-shot method developed in the dissertation
section *One-Shot Input Transfer Learning* (``sec:oneshot``).  The method
identifies the input transfer map :math:`\\hat{\\mathcal{T}}^{(\\alpha\\to\\beta)}`
from a single (or a few) replay(s) of source input trajectories on the target,
and deploys it as a lifted lower-triangular Toeplitz operator.

Two estimators are provided, both consuming the same learning-set data
:math:`\\{(\\mathbf{y}_l^{(\\alpha)}, \\mathbf{y}_l^{(\\beta)})\\}`:

* :func:`fit_biproper_lti` -- the rational biproper-LTI estimator
  (``sec:oneshot_model_structure``).  Commits to a fixed order ``M`` and fits
  the ``2M+1`` coefficients by nonlinear least squares on the prediction-error
  cost ``eq:oneshot_cost`` / ``eq:oneshot_cost_weighted``.
* :func:`fit_full_lttm` -- the full lifted-system estimator
  (``sec:oneshot_full_lttm``).  Drops the rational parametrisation and solves
  the closed-form linear least-squares problem ``eq:oneshot_full_estimate`` /
  ``eq:oneshot_full_spectral_estimate`` for the ``N`` Markov parameters
  directly.

Supporting diagnostics:

* :func:`deconvolve_output_transfer` -- nonparametric impulse-response estimate
  (``eq:oneshot_deconv``);
* :func:`estimate_order` -- Hankel-rank order estimate (``eq:oneshot_M_estimator``);
* :func:`transferability_index` -- scalar go/no-go predictor (``eq:oneshot_rho``);
* :func:`task_weight_matrix` -- task-shaped cost weight (``eq:oneshot_weight_task``).

Both estimators return the lifted transfer *vector* :math:`\\mathbf{p}` (the
first ``N`` Markov parameters).  Build the operator with
:func:`vector_to_lifted_matrix` or deploy directly with :func:`apply_transfer`.

The method assumes structurally similar agents (``ass:structural_similarity``,
equal relative degree) and approximate input--output transfer equivalence
(``ass:commutation``); see the section for when these hold.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import lfilter

from core.utils.control_lib.lib_control.learning.lifted import vector_to_lifted_matrix

ArrayLike = np.ndarray


# ======================================================================================================================
def _as_trajectory_list(y) -> list[np.ndarray]:
    """Wrap a single 1-D trajectory in a list; pass a list/2-D array through.

    Accepts either one learning trajectory or a learning set of ``L`` of them,
    so every estimator below transparently supports ``L = 1`` and ``L > 1``.
    """
    arr = np.asarray(y, dtype=float)
    if arr.ndim == 1:
        return [arr]
    return [np.asarray(row, dtype=float) for row in arr]


# ======================================================================================================================
def biproper_impulse_response(theta: np.ndarray, M: int, N: int) -> np.ndarray:
    r"""First ``N`` Markov parameters of the biproper LTI model ``eq:oneshot_model_structure``.

    The model is the discrete-time, SISO, biproper transfer function

    .. math::
       F(z) = c\,\frac{1 + \sum_{k=1}^{M} a_k z^{-k}}{1 + \sum_{k=1}^{M} b_k z^{-k}},

    parametrised by :math:`\boldsymbol{\theta} = [c, a_1, \dots, a_M, b_1,
    \dots, b_M]^\top \in \mathbb{R}^{2M+1}`.  The returned vector
    :math:`\mathbf{p}(\boldsymbol{\theta})` is the impulse response of
    :math:`F` truncated to ``N`` samples (``eq:oneshot_impulse_response``).

    Parameters
    ----------
    theta : ndarray, shape (2M+1,)
        Parameter vector ``[c, a_1..a_M, b_1..b_M]``.
    M : int
        Model order.  ``M = 0`` is the static-gain model ``p = [c, 0, ...]``.
    N : int
        Number of Markov parameters to return (deployment horizon).
    """
    theta = np.asarray(theta, dtype=float)
    if theta.shape != (2 * M + 1,):
        raise ValueError(f"theta must have length {2 * M + 1} for M={M}, got {theta.shape}")
    c = theta[0]
    a = theta[1:1 + M]
    b = theta[1 + M:1 + 2 * M]
    num = c * np.concatenate([[1.0], a])
    den = np.concatenate([[1.0], b])
    impulse = np.zeros(N)
    impulse[0] = 1.0
    return lfilter(num, den, impulse)


# ======================================================================================================================
def apply_transfer(p: np.ndarray, u_source: np.ndarray) -> np.ndarray:
    r"""Deploy a transfer vector: :math:`\mathbf{u}^{(\beta)} = \mathcal{M}(\mathbf{p})\,\mathbf{u}^{(\alpha)}`.

    Applies the lifted lower-triangular Toeplitz operator built from ``p`` to a
    deployment input.  Equivalent to ``vector_to_lifted_matrix(p) @ u_source``
    but evaluated as a causal convolution.

    Parameters
    ----------
    p : ndarray, shape (N,)
        Transfer vector (Markov parameters), from :func:`fit_biproper_lti` or
        :func:`fit_full_lttm`.
    u_source : ndarray, shape (N,)
        Source deployment input :math:`\mathbf{u}_d^{(\alpha)}`.

    Returns
    -------
    ndarray
        Transferred target input :math:`\mathbf{u}_d^{(\beta)}`.
    """
    p = np.asarray(p, dtype=float)
    u_source = np.asarray(u_source, dtype=float)
    return lfilter(p, [1.0], u_source)


# ======================================================================================================================
def _whitener(W: np.ndarray | None, N: int) -> np.ndarray | None:
    """Cholesky factor ``U`` with ``W = U^T U``; ``None`` for an unweighted cost.

    A residual ``r`` weighted by ``W`` satisfies ``r^T W r = ||U r||_2^2``, so
    weighted least squares reduces to ordinary least squares on ``U @ r``.
    """
    if W is None:
        return None
    W = np.asarray(W, dtype=float)
    if W.shape != (N, N):
        raise ValueError(f"W must be {N}x{N}, got {W.shape}")
    # W = L L^T (lower Cholesky); use U = L^T so that W = U^T U.
    return np.linalg.cholesky(W).T


# ======================================================================================================================
def fit_biproper_lti(
        y_source: ArrayLike,
        y_target: ArrayLike,
        M: int,
        W: np.ndarray | None = None,
        ridge: float = 0.0,
        theta0: np.ndarray | None = None,
        max_iter: int = 1000,
) -> np.ndarray:
    r"""Rational biproper-LTI one-shot estimator (``sec:oneshot_model_structure``).

    Solves the prediction-error cost ``eq:oneshot_cost`` (or its weighted
    variant ``eq:oneshot_cost_weighted``)

    .. math::
       \boldsymbol{\theta}^\star = \arg\min_{\boldsymbol{\theta}}
       \sum_{l} \bigl\| \mathbf{y}_l^{(\alpha)}
       - \mathcal{M}(\mathbf{p}(\boldsymbol{\theta}))\,\mathbf{y}_l^{(\beta)}
       \bigr\|_W^2 + \lambda \lVert\boldsymbol{\theta}\rVert_2^2

    over the biproper class of order ``M`` by Levenberg--Marquardt /
    trust-region nonlinear least squares.  The transfer vector returned has
    length ``N`` equal to the (common) learning-trajectory length.

    Parameters
    ----------
    y_source, y_target : ndarray or list of ndarray
        Learning-set outputs.  A single 1-D array is the canonical ``L = 1``
        case; a list (or 2-D array, one trajectory per row) supplies an
        ``L > 1`` learning set.  All trajectories must share length ``N``.
    M : int
        Model order.  Use :func:`estimate_order` to pick it from data.
    W : ndarray, shape (N, N), optional
        Symmetric positive-definite task-shaped weight (``eq:oneshot_weight_task``,
        :func:`task_weight_matrix`).  ``None`` is the unweighted cost.
    ridge : float, optional
        Parameter-norm regulariser :math:`\lambda` (the ``ridge`` term in the
        note following ``eq:oneshot_cost``).  Controls variance when ``L`` is
        small relative to ``2M+1``.
    theta0 : ndarray, shape (2M+1,), optional
        Initial guess.  Defaults to the static-gain seed ``[c0, 0, ..., 0]``
        with ``c0`` the least-squares scalar gain between the outputs.
    max_iter : int, optional
        Maximum solver iterations.

    Returns
    -------
    ndarray, shape (N,)
        Transfer vector :math:`\mathbf{p}(\boldsymbol{\theta}^\star)`.
    """
    ys = _as_trajectory_list(y_source)
    yt = _as_trajectory_list(y_target)
    if len(ys) != len(yt):
        raise ValueError(f"y_source and y_target must have the same L, got {len(ys)} vs {len(yt)}")
    N = len(ys[0])
    if any(len(v) != N for v in ys + yt):
        raise ValueError("all learning trajectories must share the same length N")

    U = _whitener(W, N)

    if theta0 is None:
        # Static-gain seed: c0 = argmin_c sum ||y_s - c y_t||^2.
        num = sum(float(s @ t) for s, t in zip(ys, yt))
        den = sum(float(t @ t) for t in yt)
        c0 = num / den if den > 0 else 1.0
        theta0 = np.concatenate([[c0], np.zeros(2 * M)])

    def residual(theta: np.ndarray) -> np.ndarray:
        p = biproper_impulse_response(theta, M, N)
        Mp = vector_to_lifted_matrix(p)
        blocks = []
        for s, t in zip(ys, yt):
            r = s - Mp @ t
            blocks.append(r if U is None else U @ r)
        if ridge > 0.0:
            blocks.append(np.sqrt(ridge) * theta)
        return np.concatenate(blocks)

    sol = least_squares(residual, theta0, method="trf", max_nfev=max_iter)
    return biproper_impulse_response(sol.x, M, N)


# ======================================================================================================================
def fit_full_lttm(
        y_source: ArrayLike,
        y_target: ArrayLike,
        W: np.ndarray | None = None,
        R: np.ndarray | float | None = None,
) -> np.ndarray:
    r"""Full lifted-system one-shot estimator (``sec:oneshot_full_lttm``).

    Drops the rational parametrisation and identifies all ``N`` Markov
    parameters of the lifted transfer map by closed-form linear least squares.
    Using the LTTM commutability identity, the cost ``eq:oneshot_full_cost``
    is linear in :math:`\mathbf{p}`, with closed-form solution
    ``eq:oneshot_full_spectral_estimate``

    .. math::
       \hat{\mathbf{p}} = \Bigl(\textstyle\sum_l \mathcal{M}(\mathbf{y}_l^{(\beta)})^\top W
       \mathcal{M}(\mathbf{y}_l^{(\beta)}) + R\Bigr)^{-1}
       \sum_l \mathcal{M}(\mathbf{y}_l^{(\beta)})^\top W\,\mathbf{y}_l^{(\alpha)}.

    Convex, no local minima, no order to choose -- at the price of higher
    variance than the rational fit (``N`` parameters instead of ``2M+1``).

    Parameters
    ----------
    y_source, y_target : ndarray or list of ndarray
        Learning-set outputs; ``L = 1`` (single array) or ``L > 1`` (list /
        2-D array).  All trajectories must share length ``N``.
    W : ndarray, shape (N, N), optional
        Per-trajectory symmetric PSD residual weight (the spectral shaping
        :math:`\mathbf{W}_0` of ``eq:oneshot_full_cost_spectral``, e.g. a
        causal low-pass LTTM ``Q^T Q``).  ``None`` is the plain estimator
        ``eq:oneshot_full_estimate``.
    R : ndarray (N, N) or float, optional
        Tikhonov parameter regulariser ``eq:oneshot_full_tikhonov``.  A scalar
        ``lambda`` is expanded to ``lambda * I``.  ``None`` means no
        regularisation.

    Returns
    -------
    ndarray, shape (N,)
        Transfer vector :math:`\hat{\mathbf{p}}_{\mathrm{full}}`.
    """
    ys = _as_trajectory_list(y_source)
    yt = _as_trajectory_list(y_target)
    if len(ys) != len(yt):
        raise ValueError(f"y_source and y_target must have the same L, got {len(ys)} vs {len(yt)}")
    N = len(ys[0])
    if any(len(v) != N for v in ys + yt):
        raise ValueError("all learning trajectories must share the same length N")

    if W is None:
        W = np.eye(N)
    else:
        W = np.asarray(W, dtype=float)
    if R is None:
        R = np.zeros((N, N))
    elif np.isscalar(R):
        R = float(R) * np.eye(N)
    else:
        R = np.asarray(R, dtype=float)

    A = R.copy()
    b = np.zeros(N)
    for s, t in zip(ys, yt):
        Mt = vector_to_lifted_matrix(t)
        MtW = Mt.T @ W
        A += MtW @ Mt
        b += MtW @ s
    return np.linalg.solve(A, b)


# ======================================================================================================================
def deconvolve_output_transfer(
        y_source: np.ndarray,
        y_target: np.ndarray,
        ridge: float = 0.0,
) -> np.ndarray:
    r"""Nonparametric impulse response of the output transfer map (``eq:oneshot_deconv``).

    Solves the lower-triangular Toeplitz system
    :math:`\mathcal{M}(\mathbf{y}^{(\beta)})\,\mathbf{g} = \mathbf{y}^{(\alpha)}`
    for the impulse response :math:`\mathbf{g}` of the output transfer map.
    With ``ridge = 0`` this is exact forward substitution; ``ridge > 0``
    switches to a regularised least-squares solve, recommended when the
    leading samples of ``y_target`` are small (the ill-conditioned regime
    noted after ``eq:oneshot_deconv``).

    Parameters
    ----------
    y_source, y_target : ndarray, shape (N,)
        A single learning-set output pair.
    ridge : float, optional
        Tikhonov regulariser for the deconvolution solve.

    Returns
    -------
    ndarray, shape (N,)
        Deconvolved impulse-response estimate :math:`\hat{\mathbf{g}}`.
    """
    y_source = np.asarray(y_source, dtype=float)
    y_target = np.asarray(y_target, dtype=float)
    Mt = vector_to_lifted_matrix(y_target)
    if ridge > 0.0:
        N = len(y_source)
        A = Mt.T @ Mt + ridge * np.eye(N)
        return np.linalg.solve(A, Mt.T @ y_source)
    return np.linalg.solve(Mt, y_source)


# ======================================================================================================================
def hankel_singular_values(g: np.ndarray) -> np.ndarray:
    r"""Singular values of the strictly-proper Hankel matrix (``eq:oneshot_hankel``).

    The output transfer map is biproper, so its first impulse-response sample
    :math:`\hat g_1` is the direct-feedthrough term.  Stripping it off and
    building the Hankel matrix from the strictly-proper tail
    :math:`(\hat g_2, \hat g_3, \dots)` yields an object whose rank equals the
    McMillan degree of the transfer map.

    Parameters
    ----------
    g : ndarray, shape (N,)
        Deconvolved impulse response from :func:`deconvolve_output_transfer`.

    Returns
    -------
    ndarray
        Singular values in non-increasing order.
    """
    g = np.asarray(g, dtype=float)
    tail = g[1:]                       # strip the direct-feedthrough term g_1
    n = len(tail)
    rows = n // 2
    if rows < 1:
        raise ValueError("impulse response too short to form a Hankel matrix")
    H = np.array([tail[i:i + rows] for i in range(rows)])
    return np.linalg.svd(H, compute_uv=False)


# ======================================================================================================================
def estimate_order(
        y_source: np.ndarray,
        y_target: np.ndarray,
        tau: float = 1e-2,
        ridge: float = 0.0,
) -> tuple[int, np.ndarray]:
    r"""Data-driven model-order estimate (``eq:oneshot_M_estimator``).

    Deconvolves the output transfer impulse response, forms the strictly-proper
    Hankel matrix, and counts the singular values above a relative tolerance:

    .. math::
       \hat M = \bigl|\{\, k : \sigma_k / \sigma_1 > \tau \,\}\bigr|.

    A sharp drop after :math:`\sigma_{\hat M}` confirms structural similarity
    and routes the data to :func:`fit_biproper_lti`; a slowly decaying spectrum
    signals that no low-order rational model applies and motivates
    :func:`fit_full_lttm` or the iterative method.

    Parameters
    ----------
    y_source, y_target : ndarray, shape (N,)
        A single learning-set output pair.
    tau : float, optional
        Relative singular-value threshold, calibrated to the noise floor.
    ridge : float, optional
        Regulariser passed to :func:`deconvolve_output_transfer`.

    Returns
    -------
    M_hat : int
        Estimated model order.
    sigma : ndarray
        Normalised Hankel singular values :math:`\sigma_k / \sigma_1`, for
        plotting the spectrum.
    """
    g = deconvolve_output_transfer(y_source, y_target, ridge=ridge)
    sigma = hankel_singular_values(g)
    if sigma[0] <= 0.0:
        return 0, sigma
    sigma_norm = sigma / sigma[0]
    M_hat = int(np.sum(sigma_norm > tau))
    return M_hat, sigma_norm


# ======================================================================================================================
def transferability_index(
        y_source: ArrayLike,
        y_target: ArrayLike,
        M: int,
        **fit_kwargs,
) -> float:
    r"""Transferability index :math:`\rho_M` (``eq:oneshot_rho``).

    The fraction of the source output's energy explained by the best order-``M``
    biproper transfer map fitted from the target output:

    .. math::
       \rho_M = 1 - \frac{\min_{\boldsymbol{\theta}}
       \sum_l \lVert \mathbf{y}_l^{(\alpha)}
       - \mathcal{M}(\mathbf{p}(\boldsymbol{\theta}))\,\mathbf{y}_l^{(\beta)} \rVert_2^2}
       {\sum_l \lVert \mathbf{y}_l^{(\alpha)} \rVert_2^2} \in (-\infty, 1].

    It equals ``1`` iff a perfect order-``M`` transfer exists on the learning
    data and is monotone non-decreasing in ``M``; sweeping ``M`` and inspecting
    the *shape* of :math:`M \mapsto \rho_M` (sharp knee vs. gradual slope) is
    the go/no-go diagnostic for the one-shot method.  The pair is
    :math:`\varepsilon`-transferable at order ``M`` when :math:`\rho_M \ge 1 - \varepsilon`.

    Parameters
    ----------
    y_source, y_target : ndarray or list of ndarray
        Learning-set outputs; ``L = 1`` or ``L > 1``.
    M : int
        Candidate model order.
    **fit_kwargs
        Forwarded to :func:`fit_biproper_lti` (e.g. ``ridge``, ``W``).

    Returns
    -------
    float
        Transferability index :math:`\rho_M`.
    """
    ys = _as_trajectory_list(y_source)
    yt = _as_trajectory_list(y_target)
    p = fit_biproper_lti(ys, yt, M, **fit_kwargs)
    Mp = vector_to_lifted_matrix(p)
    num = sum(float(np.sum((s - Mp @ t) ** 2)) for s, t in zip(ys, yt))
    den = sum(float(np.sum(s ** 2)) for s in ys)
    if den <= 0.0:
        return float("nan")
    return 1.0 - num / den


# ======================================================================================================================
def task_weight_matrix(
        inputs: ArrayLike,
        lam: float = 1e-6,
) -> np.ndarray:
    r"""Task-shaped identification-cost weight (``eq:oneshot_weight_task``).

    Builds the empirical second-moment operator of a set of lifted inputs,

    .. math::
       W = \frac{1}{|\mathfrak{L}|} \sum_\ell
       \mathbf{u}_\ell\,\mathbf{u}_\ell^\top + \lambda I,

    so that :func:`fit_biproper_lti` is biased towards the input subspace
    actually used at deployment time.  Pass the learning-set inputs for a
    general-purpose weight, or the known deployment inputs of a downstream task
    for a task-specialised transfer map.

    Parameters
    ----------
    inputs : ndarray or list of ndarray
        One input trajectory, or a set of them (list / 2-D array, one per row).
    lam : float, optional
        Ridge term :math:`\lambda` ensuring positive definiteness.

    Returns
    -------
    ndarray, shape (N, N)
        Symmetric positive-definite weight ``W``.
    """
    us = _as_trajectory_list(inputs)
    N = len(us[0])
    W = np.zeros((N, N))
    for u in us:
        W += np.outer(u, u)
    W /= len(us)
    return W + lam * np.eye(N)


# ======================================================================================================================
def deployment_error_bound(
        T_source: np.ndarray,
        T_target: np.ndarray,
        p_hat: np.ndarray,
        p_true: np.ndarray,
        u_deploy: np.ndarray,
        commutativity_gap: float = 0.0,
) -> dict:
    r"""A-posteriori deployment-error bound (``thm:oneshot_error_bound``, ``eq:oneshot_error_bound``).

    Evaluates the two-term upper bound

    .. math::
       \lVert \mathbf{e}_d \rVert_2 \le
       \underbrace{\lVert F^{(\beta)} \rVert_2\,
       \lVert \hat{\mathcal{T}} - \mathcal{F}^{(\beta\to\alpha)} \rVert_2\,
       \lVert \mathbf{u}_d^{(\alpha)} \rVert_2}_{\text{identification residual}}
       + \underbrace{\lVert \Delta_{\mathrm{com}} \rVert_2}_{\text{commutativity gap}}.

    Diagnostic helper.  The commutativity gap is not observable from training
    data (see the note in ``sec:oneshot_error_bound``); supply it from a
    deployment trial, or leave it at ``0`` for LTI agents where it vanishes
    (``rem:oneshot_comgap_zero_lti``).

    Parameters
    ----------
    T_source, T_target : ndarray, shape (N, N)
        Lifted agent operators :math:`F^{(\alpha)}`, :math:`F^{(\beta)}`.
    p_hat : ndarray, shape (N,)
        Estimated transfer vector.
    p_true : ndarray, shape (N,)
        True (or reference) output-transfer vector.
    u_deploy : ndarray, shape (N,)
        Deployment input :math:`\mathbf{u}_d^{(\alpha)}`.
    commutativity_gap : float, optional
        :math:`\lVert \Delta_{\mathrm{com}} \rVert_2`; ``0`` for LTI agents.

    Returns
    -------
    dict
        Keys ``identification_residual``, ``commutativity_gap``, ``bound``
        (their sum) and ``deployment_error`` (the actually realised
        :math:`\lVert \mathbf{e}_d \rVert_2`).
    """
    T_source = np.asarray(T_source, dtype=float)
    T_target = np.asarray(T_target, dtype=float)
    u_deploy = np.asarray(u_deploy, dtype=float)
    A = vector_to_lifted_matrix(np.asarray(p_hat, dtype=float)) \
        - vector_to_lifted_matrix(np.asarray(p_true, dtype=float))
    id_residual = (np.linalg.norm(T_target, 2)
                   * np.linalg.norm(A, 2)
                   * np.linalg.norm(u_deploy))
    e_d = T_target @ apply_transfer(p_hat, u_deploy) - T_source @ u_deploy
    return {
        "identification_residual": float(id_residual),
        "commutativity_gap": float(commutativity_gap),
        "bound": float(id_residual + commutativity_gap),
        "deployment_error": float(np.linalg.norm(e_d)),
    }
