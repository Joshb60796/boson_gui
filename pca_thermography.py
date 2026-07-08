#!/usr/bin/env python3
"""
pca_thermography.py

Self-contained, importable Python module for Principal Component Thermography (PCT)
on time-series thermal image data from FLIR (or similar) cameras.

This module implements PCA-based processing of 3D thermal sequences (H x W x T)
for defect enhancement, noise reduction, data compression, and feature extraction
in active thermography / NDE applications.

Core function: compute_thermal_pca()
Also includes a synthetic data generator for immediate testing/demo.

Dependencies: Only numpy (core). Matplotlib is optional for the demo plots
when running the module directly.

Usage in your other program:
    import sys
    sys.path.append('/path/to/this/folder')   # or copy the file into your project
    from pca_thermography import compute_thermal_pca

    # data_3d shape must be (H, W, T) float array of temperatures or raw counts
    results = compute_thermal_pca(data_3d, 
                                  preprocessing='per_pixel_center',
                                  n_components=8,
                                  return_reconstruction=True)

    eigenimages = results['eigenimages']          # shape (n_comp, H, W)
    temporal = results['temporal_components']     # shape (n_comp, T)
    recon = results['reconstructed_data']         # if requested

Author: Generated for EyemNohBde thermography workflow (2026)
"""

from __future__ import annotations

import numpy as np
from typing import Any, Dict, Optional, Tuple

# Optional matplotlib for demo visualization when running standalone
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def generate_synthetic_pulsed_thermography(
    H: int = 96,
    W: int = 96,
    T: int = 60,
    defect_center: Tuple[int, int] = (48, 48),
    defect_radius: int = 12,
    noise_level: float = 0.25,
    seed: int = 42,
) -> np.ndarray:
    """
    Generate synthetic pulsed thermography data for testing the PCA module.

    Simulates:
      - Background cooling (exponential decay)
      - Mild non-uniform heating (center hotspot)
      - A circular subsurface defect with slower cooling (retained heat)
      - Gaussian noise

    The defect should appear clearly in PC2 / EOF2 (Primary Contrast Mode).

    Returns
    -------
    data : np.ndarray
        Shape (H, W, T) float64 temperatures (arbitrary units).
    """
    np.random.seed(seed)
    t = np.arange(T, dtype=np.float64)

    # Base cooling curve (simple exponential)
    base_cooling = 25.0 + 18.0 * np.exp(-0.065 * t)

    # Spatial non-uniform heating (Gaussian hotspot in center)
    yy, xx = np.ogrid[:H, :W]
    dist2 = (yy - H / 2) ** 2 + (xx - W / 2) ** 2
    heating_map = 3.5 * np.exp(-dist2 / (0.35 * max(H, W) ** 2))

    # Defect mask (circular)
    defect_mask = np.zeros((H, W), dtype=np.float64)
    cy, cx = defect_center
    for i in range(H):
        for j in range(W):
            if (i - cy) ** 2 + (j - cx) ** 2 <= defect_radius ** 2:
                defect_mask[i, j] = 1.0

    # Defect retains extra heat and cools more slowly
    defect_heat = 7.0 * defect_mask[:, :, np.newaxis] * np.exp(-0.018 * t)

    # Assemble frames
    data = np.empty((H, W, T), dtype=np.float64)
    for tt in range(T):
        frame = (
            base_cooling[tt]
            + heating_map * (base_cooling[tt] / 30.0)   # scale heating with overall temp
            + defect_heat[:, :, tt]
            + noise_level * np.random.randn(H, W)
        )
        data[:, :, tt] = frame

    return data


def compute_thermal_pca(
    data: np.ndarray,
    preprocessing: str = "per_pixel_center",
    n_components: Optional[int] = None,
    return_reconstruction: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Compute Principal Component Thermography (PCT) on a thermal image time series.

    This is the main entry point. It performs PCA (via SVD) on the vectorized
    image sequence to extract spatial eigenimages (modes of temperature variation)
    and their temporal evolution. Higher-order components often highlight defects
    with improved contrast and reduced noise.

    Parameters
    ----------
    data : np.ndarray
        Thermal sequence of shape (H, W, T) — height, width, time frames.
        Must be 3-dimensional. Values should be float (temperature or counts).
    preprocessing : {'per_pixel_center', 'column_standardize', 'none'}
        - 'per_pixel_center' (recommended default): Subtract mean over time for
          each pixel. Emphasizes deviations from the average thermal response.
        - 'column_standardize': Zero-mean, unit-variance per frame (original
          Rajic PCT style). Normalizes overall intensity variations between frames.
        - 'none': No centering/standardization (rarely useful).
    n_components : int or None
        Number of principal components to retain. If None, keeps all
        (min(P, T) where P = H*W). Usually 5–15 is sufficient.
    return_reconstruction : bool
        If True, also returns a low-rank reconstruction of the data using the
        kept components (useful for denoising/compression).
    verbose : bool
        If True, prints a short summary after computation.

    Returns
    -------
    results : dict
        Dictionary containing:
        - 'eigenimages' : np.ndarray, shape (n_comp, H, W)
            Spatial principal components (eigenimages / EOFs). Index 0 = PC1
            (dominant global response). Index 1 = PC2 often = Primary Contrast
            Mode showing defects.
        - 'temporal_components' : np.ndarray, shape (n_comp, T)
            Temporal evolution of each spatial mode.
        - 'singular_values' : np.ndarray, shape (n_comp,)
        - 'explained_variance_ratio' : np.ndarray, shape (n_comp,)
            Fraction of total variance explained by each kept component.
        - 'n_components' : int — actual number kept
        - 'preprocessing' : str — preprocessing method used
        - 'original_shape' : tuple (H, W, T)
        - 'total_explained_variance' : float — sum of kept ratios
        - 'reconstructed_data' : np.ndarray (H, W, T) — only if
          return_reconstruction=True

    Notes
    -----
    - For real FLIR data, load your sequence into a (H, W, T) float array first
      (e.g. using imageio, tifffile, or your existing pipeline).
    - PC2 (eigenimages[1]) is frequently the most informative for defect
      detection in active thermography.
    - This implementation follows the common SVD formulation used in PCT
      literature (Rajic and subsequent works).
    """
    if data.ndim != 3:
        raise ValueError(
            f"Input data must be 3-dimensional (H, W, T). Got shape {data.shape}"
        )

    H, W, T = data.shape
    if H == 0 or W == 0 or T == 0:
        raise ValueError("All dimensions must be positive.")

    P = H * W
    A = data.reshape(P, T).astype(np.float64, copy=False)

    # --- Preprocessing ---
    if preprocessing == "per_pixel_center":
        A_pre = A - np.mean(A, axis=1, keepdims=True)
    elif preprocessing == "column_standardize":
        col_mean = np.mean(A, axis=0, keepdims=True)
        col_std = np.std(A, axis=0, keepdims=True) + 1e-12
        A_pre = (A - col_mean) / col_std
    elif preprocessing == "none":
        A_pre = A.copy()
    else:
        raise ValueError(
            f"Unknown preprocessing='{preprocessing}'. "
            "Choose from: 'per_pixel_center', 'column_standardize', 'none'"
        )

    # --- SVD (core of PCA) ---
    U, S, Vt = np.linalg.svd(A_pre, full_matrices=False)
    # U: (P, K), S: (K,), Vt: (K, T)   where K = min(P, T)

    K_max = U.shape[1]
    n_comp = K_max if n_components is None else min(int(n_components), K_max)

    if n_comp < 1:
        n_comp = 1

    # Truncate to requested number of components
    U_trunc = U[:, :n_comp]
    S_trunc = S[:n_comp]
    Vt_trunc = Vt[:n_comp, :]

    # Explained variance (relative to total variance in the data)
    total_var = np.sum(S ** 2)
    explained_var_ratio = (S_trunc ** 2) / total_var if total_var > 0 else np.zeros(n_comp)

    # Reshape spatial components into eigenimages: (n_comp, H, W)
    eigenimages = U_trunc.T.reshape(n_comp, H, W)

    results: Dict[str, Any] = {
        "eigenimages": eigenimages,
        "temporal_components": Vt_trunc,
        "singular_values": S_trunc,
        "explained_variance_ratio": explained_var_ratio,
        "n_components": n_comp,
        "preprocessing": preprocessing,
        "original_shape": (H, W, T),
        "total_explained_variance": float(np.sum(explained_var_ratio)),
    }

    if return_reconstruction:
        # Low-rank reconstruction: A_recon = U_trunc @ diag(S_trunc) @ Vt_trunc
        A_recon = (U_trunc * S_trunc) @ Vt_trunc
        results["reconstructed_data"] = A_recon.reshape(H, W, T)

    if verbose:
        print(
            f"[ThermalPCA] Computed {n_comp} components from {H}×{W}×{T} data "
            f"({P} pixels × {T} frames).\n"
            f"  Preprocessing : {preprocessing}\n"
            f"  Total variance explained by kept components: "
            f"{results['total_explained_variance']:.4f}"
        )
        if n_comp >= 2:
            print(
                f"  PC2 (often Primary Contrast Mode) explains "
                f"{explained_var_ratio[1]:.4f} of variance."
            )

    return results


# ----------------------------------------------------------------------
# Optional helper: get a specific eigenimage or the Primary Contrast image
# ----------------------------------------------------------------------
def get_primary_contrast_image(results: Dict[str, Any]) -> np.ndarray:
    """
    Convenience function. Returns the eigenimage most likely to show defects
    (usually PC2 / index 1). Falls back to PC1 if only one component exists.
    """
    eigen = results["eigenimages"]
    if eigen.shape[0] >= 2:
        return eigen[1]
    return eigen[0]


# ----------------------------------------------------------------------
# Demo / self-test when run directly
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print("pca_thermography.py  —  Self-test / Demo")
    print("=" * 70)

    # 1. Generate synthetic data (defect should be visible in PC2)
    print("\nGenerating synthetic pulsed thermography data...")
    data = generate_synthetic_pulsed_thermography(
        H=96, W=96, T=50, defect_radius=10, noise_level=0.2
    )
    print(f"  Synthetic data shape: {data.shape}")

    # 2. Run PCA with per-pixel centering (recommended)
    print("\nRunning compute_thermal_pca (per_pixel_center, n_components=6)...")
    results = compute_thermal_pca(
        data,
        preprocessing="per_pixel_center",
        n_components=6,
        return_reconstruction=True,
        verbose=True,
    )

    print("\nResults keys:", list(results.keys()))
    print("Eigenimages shape :", results["eigenimages"].shape)
    print("Temporal shape    :", results["temporal_components"].shape)
    print("Explained variance (first 6):", 
          np.round(results["explained_variance_ratio"], 4))

    # 3. Quick check: defect contrast should be strong in PC2
    pc2 = results["eigenimages"][1]
    print(f"\nPC2 (Primary Contrast) stats — min: {pc2.min():.3f}, "
          f"max: {pc2.max():.3f}, std: {pc2.std():.3f}")

    # 4. Optional visualization if matplotlib is available
    if HAS_MATPLOTLIB:
        print("\nDisplaying first 6 eigenimages (close plot window to continue)...")
        n_show = min(6, results["n_components"])
        fig, axes = plt.subplots(2, 3, figsize=(11, 7))
        axes = axes.flatten()
        for i in range(n_show):
            ax = axes[i]
            im = ax.imshow(results["eigenimages"][i], cmap="RdBu_r", interpolation="nearest")
            var = results["explained_variance_ratio"][i]
            ax.set_title(f"PC{i+1}\n{var:.3f} var", fontsize=10)
            ax.axis("off")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        for j in range(n_show, 6):
            axes[j].axis("off")
        plt.suptitle("Principal Component Thermography — Eigenimages (Synthetic Data)", fontsize=12)
        plt.tight_layout()
        plt.show()

        # Also show a raw frame vs reconstructed for comparison
        print("Showing example raw frame vs low-rank reconstruction...")
        fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        mid_frame = data.shape[2] // 2
        ax1.imshow(data[:, :, mid_frame], cmap="inferno")
        ax1.set_title(f"Raw frame {mid_frame}")
        ax1.axis("off")
        ax2.imshow(results["reconstructed_data"][:, :, mid_frame], cmap="inferno")
        ax2.set_title(f"Reconstructed (6 PCs)")
        ax2.axis("off")
        plt.tight_layout()
        plt.show()
    else:
        print("\n(Matplotlib not available — skipping visualization. "
              "Install it for plots when running standalone.)")

    print("\n" + "=" * 70)
    print("Demo complete. You can now import this module in your own code.")
    print("=" * 70)