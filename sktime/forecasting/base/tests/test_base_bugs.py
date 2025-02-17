"""Regression tests for bugfixes related to base class related functionality."""
# copyright: sktime developers, BSD-3-Clause License (see LICENSE file)

import pytest

from sktime.forecasting.compose import ForecastByLevel, TransformedTargetForecaster
from sktime.forecasting.exp_smoothing import ExponentialSmoothing
from sktime.forecasting.model_selection import (
    ExpandingWindowSplitter,
    ForecastingGridSearchCV,
)
from sktime.forecasting.reconcile import ReconcilerForecaster
from sktime.forecasting.trend import PolynomialTrendForecaster
from sktime.transformations.hierarchical.aggregate import Aggregator
from sktime.utils._testing.hierarchical import _make_hierarchical
from sktime.utils.validation._dependencies import _check_estimator_deps


@pytest.mark.skipif(
    not _check_estimator_deps(ExponentialSmoothing, severity="none"),
    reason="skip test if required soft dependency not available",
)
def test_heterogeneous_get_fitted_params():
    """Regression test for bugfix #4574, related to get_fitted_params."""
    y = _make_hierarchical(hierarchy_levels=(2, 2), min_timepoints=7, max_timepoints=7)
    agg = Aggregator()
    y_agg = agg.fit_transform(y)

    param_grid = [
        {
            "forecaster": [ExponentialSmoothing()],
            "forecaster__trend": ["add", "mul"],
        },
        {
            "forecaster": [PolynomialTrendForecaster()],
            "forecaster__degree": [1, 2],
        },
    ]

    pipe = TransformedTargetForecaster(steps=[("forecaster", ExponentialSmoothing())])

    N_cv_fold = 2
    step_cv = 1
    fh = [1, 2]

    N_t = len(y_agg.index.get_level_values(2).unique())
    initial_window_cv_len = N_t - (N_cv_fold - 1) * step_cv - fh[-1]

    cv = ExpandingWindowSplitter(
        initial_window=initial_window_cv_len,
        step_length=step_cv,
        fh=fh,
    )

    gscv = ForecastingGridSearchCV(forecaster=pipe, param_grid=param_grid, cv=cv)
    gscv_bylevel = ForecastByLevel(gscv, "local")
    reconciler = ReconcilerForecaster(gscv_bylevel, method="ols")

    reconciler.fit(y_agg)
    reconciler.get_fitted_params()  # triggers an error pre-fix
