"""Time Series Forest (TSF) Classifier."""

__author__ = [
    "TonyBagnall",
    "kkoziara",
    "luiszugasti",
    "kanand77",
    "mloning",
    "Oleksii Kachaiev",
    "CTFallon",
    "mgazian000",
]
__all__ = [
    "BaseTimeSeriesForest",
    "_transform",
    "_get_intervals",
    "_fit_estimator",
]

import math

import numpy as np
from joblib import Parallel, delayed
from sklearn.utils.multiclass import class_distribution
from sklearn.utils.validation import check_random_state

from sktime.base._base import _clone_estimator
from sktime.utils.slope_and_trend import _slope
from sktime.utils.validation import check_n_jobs


class BaseTimeSeriesForest:
    """Base time series forest classifier."""

    def __init__(
        self,
        min_interval=3,
        n_estimators=200,
        n_jobs=1,
        random_state=None,
    ):
        super().__init__(
            self._base_estimator,
            n_estimators=n_estimators,
        )

        self.random_state = random_state
        self.n_estimators = n_estimators
        self.min_interval = min_interval
        self.n_jobs = n_jobs
        # The following set in method fit
        self.n_classes = 0
        self.series_length = 0
        self.n_intervals = 0
        self.estimators_ = []
        self.intervals_ = []
        self.classes_ = []

        # We need to add is-fitted state when inheriting from scikit-learn
        self._is_fitted = False

        # temporal importance curves, set inside fit
        self.mean_curve_ = None
        self.stdev_curve_ = None
        self.slope_curve_ = None
        self.n_intervals_wts_curve_ = None

    @property
    def _estimator(self):
        """Access first parameter in self, self inheriting from sklearn BaseForest.

        The attribute was renamed from base_estimator to estimator in sklearn 1.2.0.
        """
        import sklearn
        from packaging.specifiers import SpecifierSet

        sklearn_version = sklearn.__version__

        if sklearn_version in SpecifierSet(">=1.2.0"):
            return self.estimator
        else:
            return self.base_estimator

    def _fit(self, X, y):
        """Build a forest of trees from the training set (X, y).

        Parameters
        ----------
        Xt: np.ndarray or pd.DataFrame
            Panel training data.
        y : np.ndarray
            The class labels.

        Returns
        -------
        self : object
            An fitted instance of the classifier
        """
        X = X.squeeze(1)
        n_instances, self.series_length = X.shape

        n_jobs = check_n_jobs(self.n_jobs)

        rng = check_random_state(self.random_state)

        self.n_classes = np.unique(y).shape[0]

        self.classes_ = class_distribution(np.asarray(y).reshape(-1, 1))[0][0]
        self.n_intervals = int(math.sqrt(self.series_length))
        if self.n_intervals == 0:
            self.n_intervals = 1
        if self.series_length < self.min_interval:
            self.min_interval = self.series_length

        self.intervals_ = [
            _get_intervals(self.n_intervals, self.min_interval, self.series_length, rng)
            for _ in range(self.n_estimators)
        ]

        self.estimators_ = Parallel(n_jobs=n_jobs)(
            delayed(_fit_estimator)(
                _clone_estimator(self._estimator, rng), X, y, self.intervals_[i]
            )
            for i in range(self.n_estimators)
        )

        self._is_fitted = True
        return self

    def _get_fitted_params(self):
        return {
            "classes": self.classes_,
            "intervals": self.intervals_,
            "estimators": self.estimators_,
        }

    def temporal_curves_(self):
        """Create temporal importance curves.

        Creates four curves: three feature temporal importance curves
        (mean, stdev, slope) and one curve containing the number of times a
        timestamp appears in a tree's intervals.

        Follows procedure outlined in section 4.4 of [1]

        References
        ----------
        .. [1] H.Deng, G.Runger, E.Tuv and M.Vladimir, "A time series forest for
        classification and feature extraction",Information Sciences, 239, 2013

        """
        self.mean_curve_ = np.zeros(self.series_length)
        self.stdev_curve_ = np.zeros(self.series_length)
        self.slope_curve_ = np.zeros(self.series_length)
        self.n_intervals_wts_curve_ = np.zeros(self.series_length)

        for estimator, intervals in zip(self.estimators_, self.intervals_):
            for i_int, interval in enumerate(intervals):
                interval_mask = np.zeros(self.series_length)
                np.put(interval_mask, range(interval[0], interval[1]), 1)

                self.n_intervals_wts_curve_ += np.where(interval_mask, 1, 0)
                self.mean_curve_ += np.where(
                    interval_mask, estimator.feature_importances_[3 * i_int], 0
                )
                self.stdev_curve_ += np.where(
                    interval_mask, estimator.feature_importances_[3 * i_int + 1], 0
                )
                self.slope_curve_ += np.where(
                    interval_mask, estimator.feature_importances_[3 * i_int + 2], 0
                )


def _transform(X, intervals):
    """Transform X for given intervals.

    Compute the mean, standard deviation and slope for given intervals of input data X.

    Parameters
    ----------
    Xt: np.ndarray or pd.DataFrame
        Panel data to transform.
    intervals : np.ndarray
        Intervals containing start and end values.

    Returns
    -------
    Xt: np.ndarray or pd.DataFrame
     Transformed X, containing the mean, std and slope for each interval
    """
    n_instances, _ = X.shape
    n_intervals, _ = intervals.shape
    transformed_x = np.empty(shape=(3 * n_intervals, n_instances), dtype=np.float32)
    for j in range(n_intervals):
        X_slice = X[:, intervals[j][0] : intervals[j][1]]
        means = np.mean(X_slice, axis=1)
        std_dev = np.std(X_slice, axis=1)
        slope = _slope(X_slice, axis=1)
        transformed_x[3 * j] = means
        transformed_x[3 * j + 1] = std_dev
        transformed_x[3 * j + 2] = slope

    return transformed_x.T


def _get_intervals(n_intervals, min_interval, series_length, rng):
    """Generate random intervals for given parameters."""
    intervals = np.zeros((n_intervals, 2), dtype=int)
    for j in range(n_intervals):
        intervals[j][0] = rng.randint(series_length - min_interval)
        length = rng.randint(series_length - intervals[j][0] - 1)
        if length < min_interval:
            length = min_interval
        intervals[j][1] = intervals[j][0] + length
    return intervals


def _fit_estimator(estimator, X, y, intervals):
    """Fit an estimator on input data (X, y)."""
    transformed_x = _transform(X, intervals)
    return estimator.fit(transformed_x, y)
