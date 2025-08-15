from __future__ import annotations
from PIL import Image
import imagehash
import numpy as np
import cv2

def phash_from_image(img: Image.Image) -> str:
    return str(imagehash.phash(img))

def has_border_visual(img: Image.Image, edge_band_px: int = 14, edge_density_threshold: float = 0.08) -> bool:
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160)

    h, w = edges.shape
    band = edge_band_px
    top = edges[0:band, :]
    bottom = edges[h-band:h, :]
    left = edges[:, 0:band]
    right = edges[:, w-band:w]

    total_edge = np.count_nonzero(edges)
    total_pixels = edges.size
    edge_density = total_edge / max(1, total_pixels)

    border_edges = np.count_nonzero(top) + np.count_nonzero(bottom) + np.count_nonzero(left) + np.count_nonzero(right)
    border_pixels = top.size + bottom.size + left.size + right.size
    border_density = border_edges / max(1, border_pixels)

    return border_density >= edge_density_threshold and edge_density >= (edge_density_threshold / 2)

def has_orange_outline(img: Image.Image, band_px: int = 12) -> bool:
    """Поиск оранжевой рамки по периметру (как на примере)."""
    arr = np.array(img.convert("RGB"))
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

    lower = np.array([10, 120, 120], dtype=np.uint8)  # H≈10..28
    upper = np.array([28, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    h, w = mask.shape
    b = max(4, min(band_px, h//6, w//6))

    border = np.zeros_like(mask)
    border[:b, :] = mask[:b, :]
    border[-b:, :] = mask[-b:, :]
    border[:, :b] = np.maximum(border[:, :b], mask[:, :b])
    border[:, -b:] = np.maximum(border[:, -b:], mask[:, -b:])

    density = np.count_nonzero(border) / max(1, border.size)
    return density >= 0.012  # ~1.2%+

def has_outline(img: Image.Image, edge_band_px: int = 14, edge_density_threshold: float = 0.08) -> bool:
    return has_orange_outline(img) or has_border_visual(img, edge_band_px, edge_density_threshold)
