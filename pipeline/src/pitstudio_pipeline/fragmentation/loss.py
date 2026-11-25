"""U-Net weight map and loss (spec 012, FR-012-20): Ronneberger et al. 2015, Eq. 2, plus a soft foreground Dice."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F
from scipy import ndimage

from .labels import encode_three_class

W0 = 10.0  # Ronneberger, Fischer & Brox 2015, section 3: w0 = 10 and sigma of about 5 pixels
SIGMA_PX = 5.0
_BORDER_FLOOR = 1e-14  # the border term beyond the crop radius is below this fraction of w0 (see _crop_radius)
_DICE_SMOOTH = 1.0


def class_weight_map(label: np.ndarray) -> np.ndarray:
    """w_c: inverse frequency of the three FR-012-18 classes of the tile, normalised so the pixel mean is 1.

    A class absent from the tile gets weight 0 (it has no pixel to weight).
    """
    target = encode_three_class(label)
    freq = np.bincount(target.ravel(), minlength=3) / target.size
    present = freq > 0
    per_class = np.zeros(3, dtype=np.float64)
    per_class[present] = 1.0 / freq[present] / present.sum()
    return per_class[target]


def _crop_radius(w0: float, sigma: float) -> float:
    """Distance beyond which the border term is below w0 * _BORDER_FLOOR: d2 > R implies d1 + d2 > R."""
    return float(sigma * np.sqrt(-2.0 * np.log(_BORDER_FLOOR))) + 1.0


def weight_map(label: np.ndarray, *, w0: float = W0, sigma: float = SIGMA_PX) -> np.ndarray:
    """w = w_c + w0 exp(-(d1 + d2)^2 / (2 sigma^2)).

    d1 and d2 are the Euclidean distances to the nearest and second-nearest instance (0 inside an instance). The border
    term is 0 with fewer than two instances.
    """
    label = np.asarray(label)
    h, w = label.shape
    wc = class_weight_map(label)
    ids, inverse = np.unique(label, return_inverse=True)
    dense = inverse.reshape(label.shape) + (0 if ids[0] == 0 else 1)  # background -> 0, instances -> 1..n
    if int(dense.max()) < 2:
        return wc
    radius = int(np.ceil(_crop_radius(w0, sigma)))
    d1 = np.full((h, w), np.inf)
    d2 = np.full((h, w), np.inf)
    for i, sl in enumerate(ndimage.find_objects(dense), start=1):
        if sl is None:
            continue
        y0, y1 = max(sl[0].start - radius, 0), min(sl[0].stop + radius, h)
        x0, x1 = max(sl[1].start - radius, 0), min(sl[1].stop + radius, w)
        d = ndimage.distance_transform_edt(dense[y0:y1, x0:x1] != i)  # float64, 0 inside instance i
        a, b = d1[y0:y1, x0:x1], d2[y0:y1, x0:x1]
        d2[y0:y1, x0:x1] = np.minimum(b, np.maximum(a, d))
        d1[y0:y1, x0:x1] = np.minimum(a, d)
    with np.errstate(invalid="ignore", over="ignore"):
        border = w0 * np.exp(-((d1 + d2) ** 2) / (2.0 * sigma**2))  # d2 = inf gives 0
    return wc + np.nan_to_num(border, nan=0.0, posinf=0.0)


def unet_loss(logits: torch.Tensor, target: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
    """Pixel-weighted cross-entropy (mean over pixels) + (1 - soft Dice) on the foreground probability 1 - p0.

    The Dice is computed per tile with a smoothing constant of 1 and averaged over the batch.
    """
    logits = logits.float()
    ce = (F.cross_entropy(logits, target, reduction="none") * weight.float()).mean()
    foreground_prob = 1.0 - logits.softmax(dim=1)[:, 0]
    foreground = (target > 0).float()
    inter = (foreground_prob * foreground).flatten(1).sum(1)
    denom = foreground_prob.flatten(1).sum(1) + foreground.flatten(1).sum(1)
    dice = (2.0 * inter + _DICE_SMOOTH) / (denom + _DICE_SMOOTH)
    return ce + (1.0 - dice).mean()
