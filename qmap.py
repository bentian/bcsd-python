"""
Quantile mapping implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class QMap:
    """Empirical quantile mapping.

    This implementation keeps the original repo's design philosophy:
    fit percentile maps on observation/model pairs and map model values
    to the corresponding observation quantiles.

    Parameters
    ----------
    step:
        Percentile step size. For example, 0.1 means percentile grid
        [0.0, 0.1, 0.2, ..., 99.9]. Smaller values provide finer mapping
        but increase memory and compute cost.
    """

    step: float = 0.1
    axis: Optional[int] = field(default=None, init=False)
    x_map: Optional[np.ndarray] = field(default=None, init=False)
    y_map: Optional[np.ndarray] = field(default=None, init=False)

    def fit(self, x: np.ndarray, y: np.ndarray, axis: Optional[int] = None) -> "QMap":
        """Fit percentile maps.

        Parameters
        ----------
        x:
            Observed/reference values.
        y:
            Modeled values.
        axis:
            None or 0. `axis=0` is intended for arrays shaped like
            (time, feature), where each feature/column gets its own mapping.
        """
        if axis not in (None, 0):
            raise ValueError("axis must be None or 0")
        if self.step <= 0 or self.step > 100:
            raise ValueError("step must be in the interval (0, 100]")

        self.axis = axis
        percentiles = np.arange(0.0, 100.0, self.step, dtype=float)
        self.x_map = np.nanpercentile(x, percentiles, axis=axis)
        self.y_map = np.nanpercentile(y, percentiles, axis=axis)
        return self

    def predict(self, y: np.ndarray) -> np.ndarray:
        """Map modeled values to observed quantiles.

        Notes
        -----
        This preserves the original repo's nearest-percentile behavior
        instead of interpolating continuously between quantiles.
        """
        if self.x_map is None or self.y_map is None:
            raise RuntimeError("QMap must be fit before calling predict().")

        y = np.asarray(y)

        if self.axis is None:
            flat_y = y.reshape(-1)
            idx = np.array([np.nanargmin(np.abs(val - self.y_map)) for val in flat_y])
            out = self.x_map[idx]
            return out.reshape(y.shape)

        if y.ndim != 2:
            raise ValueError(
                "When axis=0, input to predict() must be 2D: (time, feature)."
            )

        if y.shape[1] != self.y_map.shape[1]:
            raise ValueError("Feature dimension does not match fitted quantile maps.")

        idx = np.array([np.nanargmin(np.abs(row - self.y_map), axis=0) for row in y])
        col_idx = np.arange(y.shape[1])
        out = np.array([self.x_map[row_idx, col_idx] for row_idx in idx])
        return out


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    x_sample = rng.normal(loc=10.0, scale=1.0, size=(10, 20))
    y_sample = rng.normal(loc=100.0, scale=5.0, size=(10, 20))

    qmap = QMap(step=0.5).fit(x_sample, y_sample, axis=0)
    mapped = qmap.predict(y_sample)
    print("mapped shape:", mapped.shape)
