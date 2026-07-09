"""Stream review window with PCA analysis and pixel time-series plotting.

Layout is sized for a Raspberry Pi 7" touchscreen (~800×480).
"""

import csv
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import messagebox, ttk

try:
    from pca_thermography import compute_thermal_pca
    HAS_PCA_MODULE = True
except ImportError:
    HAS_PCA_MODULE = False

# Preview size (keeps window usable on 800×480 displays)
_PREVIEW_W = 400
_PREVIEW_H = 320


class StreamReviewWindow(tk.Toplevel):
    def __init__(self, master, data_3d, save_path):
        super().__init__(master)
        self.title("Stream Review & PCA")
        # Fit Pi 7" (800×480) with a little margin for window chrome
        self.geometry("780x460")
        self.minsize(700, 420)
        self.data = data_3d  # (H, W, T)
        self.save_path = save_path
        self.current_frame = 0
        self.pca_results = None
        self.component_options = []
        self.pixel_plot_fig = None
        self.pixel_plot_ax = None

        n = int(self.data.shape[2])
        self.subtract_first_var = tk.BooleanVar(value=False)
        self.pca_first_var = tk.IntVar(value=0)
        self.pca_last_var = tk.IntVar(value=max(0, n - 1))

        self.create_widgets()
        self.show_frame(0)

    @property
    def n_frames(self):
        return int(self.data.shape[2])

    def create_widgets(self):
        # ---- Row 1: frame slider ----
        control_frame = ttk.Frame(self)
        control_frame.pack(pady=2, fill="x", padx=6)

        ttk.Label(control_frame, text="Frame:").pack(side=tk.LEFT, padx=2)
        self.frame_var = tk.IntVar(value=0)
        self.slider = ttk.Scale(
            control_frame,
            from_=0,
            to=max(0, self.n_frames - 1),
            orient=tk.HORIZONTAL,
            length=420,
            variable=self.frame_var,
            command=self.on_slider_change,
        )
        self.slider.pack(side=tk.LEFT, padx=4, fill="x", expand=True)

        self.frame_label = ttk.Label(
            control_frame, text=f"0 / {max(0, self.n_frames - 1)}", width=10
        )
        self.frame_label.pack(side=tk.LEFT, padx=4)

        # ---- Preview image (compact) ----
        self.image_label = ttk.Label(self)
        self.image_label.pack(pady=2)
        self.image_label.bind("<Button-1>", self.on_image_click)

        # ---- Row 2: processing options (first-frame sub + PCA range) ----
        proc_frame = ttk.Frame(self)
        proc_frame.pack(pady=2, fill="x", padx=6)

        ttk.Checkbutton(
            proc_frame,
            text="Subtract 1st frame",
            variable=self.subtract_first_var,
            command=self._on_subtract_toggle,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Label(proc_frame, text="PCA frames:").pack(side=tk.LEFT, padx=(10, 2))
        self.pca_first_entry = ttk.Entry(
            proc_frame, textvariable=self.pca_first_var, width=5
        )
        self.pca_first_entry.pack(side=tk.LEFT)
        ttk.Label(proc_frame, text="–").pack(side=tk.LEFT, padx=2)
        self.pca_last_entry = ttk.Entry(
            proc_frame, textvariable=self.pca_last_var, width=5
        )
        self.pca_last_entry.pack(side=tk.LEFT)
        ttk.Label(proc_frame, text="(inclusive)", font=("Helvetica", 8)).pack(
            side=tk.LEFT, padx=4
        )

        for entry, clamp in (
            (self.pca_first_entry, self._clamp_pca_first),
            (self.pca_last_entry, self._clamp_pca_last),
        ):
            entry.bind("<FocusOut>", clamp)
            entry.bind("<Return>", clamp)

        ttk.Button(proc_frame, text="Run PCA", command=self.run_pca).pack(
            side=tk.LEFT, padx=8
        )

        # ---- Row 3: plot / PCA view / save ----
        bottom_controls = ttk.Frame(self)
        bottom_controls.pack(pady=2, fill="x", padx=6)

        self.pixel_plot_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bottom_controls,
            text="Pixel plot",
            variable=self.pixel_plot_enabled,
        ).pack(side=tk.LEFT, padx=4)

        self.component_var = tk.StringVar()
        self.component_combo = ttk.Combobox(
            bottom_controls,
            textvariable=self.component_var,
            state="readonly",
            width=6,
        )
        self.component_combo.pack(side=tk.LEFT, padx=2)

        ttk.Button(
            bottom_controls, text="Show PC", command=self.show_selected_component
        ).pack(side=tk.LEFT, padx=2)

        self.save_format_var = tk.StringVar(value="NumPy (.npy)")
        ttk.Combobox(
            bottom_controls,
            textvariable=self.save_format_var,
            values=["NumPy (.npy)", "TIFF sequence", "Both"],
            state="readonly",
            width=12,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(bottom_controls, text="Save", command=self.save_data).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(bottom_controls, text="Close", command=self.destroy).pack(
            side=tk.LEFT, padx=2
        )

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var).pack(pady=2)

    # ------------------------------------------------------------------ helpers
    def _parse_int_field(self, var, default=0):
        try:
            return int(var.get())
        except (tk.TclError, ValueError, TypeError):
            return default

    def _clamp_pca_first(self, _event=None):
        last = max(0, self.n_frames - 1)
        v = self._parse_int_field(self.pca_first_var, 0)
        v = max(0, min(last, v))
        self.pca_first_var.set(v)
        # Keep first <= last
        if self._parse_int_field(self.pca_last_var, last) < v:
            self.pca_last_var.set(v)
        return "break" if _event and getattr(_event, "keysym", "") == "Return" else None

    def _clamp_pca_last(self, _event=None):
        last = max(0, self.n_frames - 1)
        v = self._parse_int_field(self.pca_last_var, last)
        v = max(0, min(last, v))
        self.pca_last_var.set(v)
        if self._parse_int_field(self.pca_first_var, 0) > v:
            self.pca_first_var.set(v)
        return "break" if _event and getattr(_event, "keysym", "") == "Return" else None

    def _pca_range(self):
        """Return inclusive (first, last) frame indices after clamping."""
        self._clamp_pca_first()
        self._clamp_pca_last()
        first = self._parse_int_field(self.pca_first_var, 0)
        last = self._parse_int_field(self.pca_last_var, self.n_frames - 1)
        if first > last:
            first, last = last, first
            self.pca_first_var.set(first)
            self.pca_last_var.set(last)
        return first, last

    def _frame_2d(self, frame):
        arr = np.asarray(frame, dtype=np.float64)
        while arr.ndim > 2:
            arr = np.mean(arr, axis=-1)
        return arr

    def get_processed_frame(self, frame_idx):
        """One frame for display / analysis, optional first-frame subtraction."""
        frame = self._frame_2d(self.data[:, :, frame_idx])
        if self.subtract_first_var.get() and self.n_frames > 0:
            ref = self._frame_2d(self.data[:, :, 0])
            frame = frame - ref
        return frame

    def get_processed_cube(self, first=None, last=None):
        """
        Build (H, W, T') float cube with optional first-frame subtraction
        and optional inclusive frame range [first, last].
        """
        data = np.asarray(self.data, dtype=np.float64)
        if data.ndim == 4:
            if data.shape[-1] == 3:
                data = np.mean(data, axis=-1)
            else:
                data = data[..., 0]

        if self.subtract_first_var.get() and data.shape[2] > 0:
            ref = data[:, :, 0:1]
            data = data - ref

        if first is not None or last is not None:
            f0 = 0 if first is None else int(first)
            f1 = data.shape[2] - 1 if last is None else int(last)
            f0 = max(0, min(data.shape[2] - 1, f0))
            f1 = max(0, min(data.shape[2] - 1, f1))
            if f0 > f1:
                f0, f1 = f1, f0
            data = data[:, :, f0 : f1 + 1]

        return data

    def _on_subtract_toggle(self):
        self.show_frame(self.current_frame)

    def on_slider_change(self, value):
        self.show_frame(int(float(value)))

    def show_frame(self, frame_idx):
        frame_idx = int(frame_idx)
        frame_idx = max(0, min(self.n_frames - 1, frame_idx))
        self.current_frame = frame_idx
        frame = self.get_processed_frame(frame_idx)
        lo, hi = float(frame.min()), float(frame.max())
        display = ((frame - lo) / (hi - lo + 1e-8) * 255).astype(np.uint8)
        img = Image.fromarray(display).resize((_PREVIEW_W, _PREVIEW_H), Image.BILINEAR)
        imgtk = ImageTk.PhotoImage(img)
        self.image_label.imgtk = imgtk
        self.image_label.configure(image=imgtk)
        self.frame_label.config(text=f"{frame_idx} / {max(0, self.n_frames - 1)}")
        self.frame_var.set(frame_idx)

    def on_image_click(self, event):
        if not self.pixel_plot_enabled.get():
            return

        orig_h, orig_w = self.data.shape[0], self.data.shape[1]
        x = int(event.x * orig_w / _PREVIEW_W)
        y = int(event.y * orig_h / _PREVIEW_H)
        x = max(0, min(x, orig_w - 1))
        y = max(0, min(y, orig_h - 1))
        self.plot_pixel_time_series(x, y)

    def plot_pixel_time_series(self, x, y):
        # Use processed full series (respects subtract-first-frame)
        cube = self.get_processed_cube()
        time_series = np.asarray(cube[y, x, ...], dtype=np.float64)
        while time_series.ndim > 1:
            time_series = np.mean(time_series, axis=-1)
        time_series = np.ravel(time_series)

        if self.pixel_plot_fig is None or not plt.fignum_exists(self.pixel_plot_fig.number):
            self.pixel_plot_fig, self.pixel_plot_ax = plt.subplots(figsize=(7, 3.5))
            plt.ion()
            self.pixel_plot_ax.set_xlabel("Frame")
            self.pixel_plot_ax.set_ylabel("Value")
            self.pixel_plot_ax.set_title("Pixel Time Series")
            self.pixel_plot_ax.grid(True)

        label = f"Pixel ({x}, {y})"
        if self.subtract_first_var.get():
            label += " −f0"
        self.pixel_plot_ax.plot(
            np.arange(time_series.size),
            time_series,
            label=label,
        )
        self.pixel_plot_ax.legend(loc="upper right", fontsize=8)
        self.pixel_plot_fig.canvas.draw()
        plt.show(block=False)

    def run_pca(self):
        if not HAS_PCA_MODULE:
            messagebox.showerror("Error", "pca_thermography.py not found.")
            return

        first, last = self._pca_range()
        n_sel = last - first + 1
        if n_sel < 2:
            messagebox.showwarning(
                "PCA range",
                "Need at least 2 frames in the PCA range (first–last).",
            )
            return

        self.status_var.set(f"PCA frames {first}–{last}...")
        self.update_idletasks()

        try:
            data = self.get_processed_cube(first=first, last=last)

            self.pca_results = compute_thermal_pca(
                data,
                preprocessing="per_pixel_center",
                n_components=min(8, n_sel),
                return_reconstruction=True,
                verbose=True,
            )
            self.pca_results["_frame_range"] = (first, last)
            self.pca_results["_subtract_first"] = bool(self.subtract_first_var.get())

            n_comp = self.pca_results["n_components"]
            self.component_options = [f"PC{i + 1}" for i in range(n_comp)]
            self.component_combo["values"] = self.component_options

            if n_comp >= 2:
                self.component_var.set("PC2")
            else:
                self.component_var.set("PC1")

            sub = " (1st-frame sub)" if self.subtract_first_var.get() else ""
            self.status_var.set(f"PCA done: frames {first}–{last}{sub}")
            messagebox.showinfo(
                "Success",
                f"Computed {n_comp} components on frames {first}–{last} "
                f"({n_sel} frames){sub}.",
            )

        except Exception as e:
            self.status_var.set("PCA failed.")
            messagebox.showerror("PCA Error", str(e))

    def show_selected_component(self):
        if self.pca_results is None:
            messagebox.showwarning("Warning", "Run PCA first.")
            return
        try:
            selected = self.component_var.get()
            if not selected:
                return
            idx = int(selected.replace("PC", "")) - 1
            eigen = self.pca_results["eigenimages"][idx]
            fr = self.pca_results.get("_frame_range")
            title = f"{selected} (Eigenimage)"
            if fr:
                title += f" [{fr[0]}–{fr[1]}]"
            self._show_image_window(eigen, title)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    @staticmethod
    def _frame_for_tiff(frame):
        """Prepare one frame for 16-bit TIFF write (2D grayscale preferred)."""
        arr = np.asarray(frame)
        while arr.ndim > 2:
            arr = np.mean(arr, axis=-1)
        if np.issubdtype(arr.dtype, np.floating):
            # Preserve signed contrast from first-frame subtraction via shift
            arr = arr - arr.min()
            if arr.max() > 0:
                arr = arr / arr.max() * 65535.0
            arr = np.clip(arr, 0, 65535).astype(np.uint16)
        elif arr.dtype != np.uint16:
            arr = np.clip(arr, 0, 65535).astype(np.uint16)
        return arr

    def _save_stream_tiffs(self, base_dir, data=None):
        """Write each time index as frames/frame_XXXX.tiff (uint16)."""
        frames_dir = base_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        data = np.asarray(self.data if data is None else data)
        if data.ndim < 3:
            raise ValueError(f"Stream data must be 3D+ (H,W,T); got shape {data.shape}")

        n_frames = data.shape[2]
        for t in range(n_frames):
            frame = self._frame_for_tiff(
                data[:, :, t, ...] if data.ndim > 3 else data[:, :, t]
            )
            path = frames_dir / f"frame_{t:04d}.tiff"
            ok = cv2.imwrite(str(path), frame, [cv2.IMWRITE_TIFF_COMPRESSION, 1])
            if not ok:
                raise RuntimeError(f"Failed to write TIFF: {path}")
        return n_frames, frames_dir

    def save_data(self):
        if self.data is None:
            return

        base_dir = Path(self.save_path) / f"stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        base_dir.mkdir(parents=True, exist_ok=True)

        fmt = self.save_format_var.get()
        save_npy = fmt in ("NumPy (.npy)", "Both")
        save_tiff = fmt in ("TIFF sequence", "Both")

        try:
            notes = []
            # Save currently displayed processing (first-frame sub) as optional
            # companion; raw cube always from original self.data
            if save_npy:
                np.save(base_dir / "raw_data.npy", self.data)
                notes.append("raw_data.npy")
                if self.subtract_first_var.get():
                    processed = self.get_processed_cube()
                    np.save(base_dir / "raw_data_minus_first.npy", processed)
                    notes.append("raw_data_minus_first.npy")

            if save_tiff:
                n_frames, frames_dir = self._save_stream_tiffs(base_dir)
                notes.append(f"{n_frames} TIFFs in {frames_dir.name}/")

            if self.pca_results is not None:
                np.save(base_dir / "eigenimages.npy", self.pca_results["eigenimages"])

                for i in range(self.pca_results["eigenimages"].shape[0]):
                    eigen = self.pca_results["eigenimages"][i]
                    norm = (
                        (eigen - eigen.min())
                        / (eigen.max() - eigen.min() + 1e-8)
                        * 255
                    ).astype(np.uint8)
                    cv2.imwrite(str(base_dir / f"PC{i + 1}.tiff"), norm)

                np.save(
                    base_dir / "temporal_components.npy",
                    self.pca_results["temporal_components"],
                )

                with open(base_dir / "explained_variance.csv", "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Component", "Explained Variance Ratio"])
                    for i, var in enumerate(self.pca_results["explained_variance_ratio"]):
                        writer.writerow([f"PC{i + 1}", var])

                fr = self.pca_results.get("_frame_range")
                if fr:
                    with open(base_dir / "pca_range.txt", "w") as f:
                        f.write(f"first_frame={fr[0]}\nlast_frame={fr[1]}\n")
                        f.write(
                            f"subtract_first={self.pca_results.get('_subtract_first', False)}\n"
                        )
                    notes.append(f"PCA range {fr[0]}–{fr[1]}")

                notes.append("PCA outputs (eigenimages, temporal, variance CSV)")

            messagebox.showinfo(
                "Saved",
                f"Data saved to:\n{base_dir}\n\n" + "\n".join(f"• {n}" for n in notes),
            )

        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _show_image_window(self, image_array, title):
        win = tk.Toplevel(self)
        win.title(title)
        img_norm = (
            (image_array - image_array.min())
            / (image_array.max() - image_array.min() + 1e-8)
            * 255
        ).astype(np.uint8)
        # Smaller popup for 7" screen
        img = Image.fromarray(img_norm).resize((400, 320), Image.BILINEAR)
        imgtk = ImageTk.PhotoImage(img)
        label = ttk.Label(win, image=imgtk)
        label.image = imgtk
        label.pack()
