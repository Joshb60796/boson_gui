"""Stream review window with PCA analysis and pixel time-series plotting."""

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


class StreamReviewWindow(tk.Toplevel):
    def __init__(self, master, data_3d, save_path):
        super().__init__(master)
        self.title("Stream Review & PCA Analysis")
        self.geometry("1000x680")
        self.data = data_3d  # (H, W, T)
        self.save_path = save_path
        self.current_frame = 0
        self.pca_results = None
        self.component_options = []
        self.pixel_plot_fig = None
        self.pixel_plot_ax = None

        self.create_widgets()
        self.show_frame(0)

    def create_widgets(self):
        control_frame = ttk.Frame(self)
        control_frame.pack(pady=8, fill="x")

        ttk.Label(control_frame, text="Frame:").pack(side=tk.LEFT, padx=5)
        self.frame_var = tk.IntVar(value=0)
        self.slider = ttk.Scale(
            control_frame,
            from_=0,
            to=self.data.shape[2] - 1,
            orient=tk.HORIZONTAL,
            length=550,
            variable=self.frame_var,
            command=self.on_slider_change,
        )
        self.slider.pack(side=tk.LEFT, padx=5)

        self.frame_label = ttk.Label(control_frame, text=f"0 / {self.data.shape[2] - 1}")
        self.frame_label.pack(side=tk.LEFT, padx=8)

        self.image_label = ttk.Label(self)
        self.image_label.pack(pady=8)
        self.image_label.bind("<Button-1>", self.on_image_click)

        bottom_controls = ttk.Frame(self)
        bottom_controls.pack(pady=8)

        self.pixel_plot_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bottom_controls,
            text="Enable Pixel Time Series Plotting",
            variable=self.pixel_plot_enabled,
        ).pack(side=tk.LEFT, padx=10)

        self.component_var = tk.StringVar()
        self.component_combo = ttk.Combobox(
            bottom_controls,
            textvariable=self.component_var,
            state="readonly",
            width=12,
        )
        self.component_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(bottom_controls, text="Show Component", command=self.show_selected_component).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(bottom_controls, text="Run PCA Analysis", command=self.run_pca).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Label(bottom_controls, text="Save as:").pack(side=tk.LEFT, padx=(10, 2))
        self.save_format_var = tk.StringVar(value="NumPy (.npy)")
        self.save_format_combo = ttk.Combobox(
            bottom_controls,
            textvariable=self.save_format_var,
            values=["NumPy (.npy)", "TIFF sequence", "Both"],
            state="readonly",
            width=14,
        )
        self.save_format_combo.pack(side=tk.LEFT, padx=2)

        ttk.Button(bottom_controls, text="Save Data", command=self.save_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_controls, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var).pack(pady=5)

    def on_slider_change(self, value):
        self.show_frame(int(float(value)))

    def show_frame(self, frame_idx):
        self.current_frame = frame_idx
        frame = self.data[:, :, frame_idx]
        display = ((frame - frame.min()) / (frame.max() - frame.min() + 1e-8) * 255).astype(np.uint8)
        img = Image.fromarray(display).resize((640, 512), Image.BILINEAR)
        imgtk = ImageTk.PhotoImage(img)
        self.image_label.imgtk = imgtk
        self.image_label.configure(image=imgtk)
        self.frame_label.config(text=f"{frame_idx} / {self.data.shape[2] - 1}")
        self.frame_var.set(frame_idx)

    def on_image_click(self, event):
        if not self.pixel_plot_enabled.get():
            return

        display_w, display_h = 640, 512
        orig_h, orig_w = self.data.shape[0], self.data.shape[1]

        x = int(event.x * orig_w / display_w)
        y = int(event.y * orig_h / display_h)

        x = max(0, min(x, orig_w - 1))
        y = max(0, min(y, orig_h - 1))

        self.plot_pixel_time_series(x, y)

    def plot_pixel_time_series(self, x, y):
        # data is (H, W, T) or occasionally (H, W, T, C) if frames were multi-channel.
        # Matplotlib ax.plot() on a 2D array draws one line per column — that made
        # the legend list the same pixel three times (e.g. BGR/Y16 packing).
        time_series = np.asarray(self.data[y, x, ...], dtype=np.float64)
        while time_series.ndim > 1:
            time_series = np.mean(time_series, axis=-1)
        time_series = np.ravel(time_series)

        if self.pixel_plot_fig is None or not plt.fignum_exists(self.pixel_plot_fig.number):
            self.pixel_plot_fig, self.pixel_plot_ax = plt.subplots(figsize=(8, 4))
            plt.ion()
            self.pixel_plot_ax.set_xlabel("Frame")
            self.pixel_plot_ax.set_ylabel("Value (counts)")
            self.pixel_plot_ax.set_title("Pixel Time Series")
            self.pixel_plot_ax.grid(True)

        # One 1-D series → one line → one legend entry for this click
        self.pixel_plot_ax.plot(
            np.arange(time_series.size),
            time_series,
            label=f"Pixel ({x}, {y})",
        )
        self.pixel_plot_ax.legend(loc="upper right", fontsize=8)
        self.pixel_plot_fig.canvas.draw()
        plt.show(block=False)

    def run_pca(self):
        if not HAS_PCA_MODULE:
            messagebox.showerror("Error", "pca_thermography.py not found.")
            return

        self.status_var.set("Running PCA...")
        self.update_idletasks()

        try:
            data = self.data.astype(np.float64)
            if data.ndim == 4:
                if data.shape[-1] == 3:
                    data = np.mean(data, axis=-1)
                else:
                    data = data[..., 0]

            self.pca_results = compute_thermal_pca(
                data,
                preprocessing="per_pixel_center",
                n_components=8,
                return_reconstruction=True,
                verbose=True,
            )

            n_comp = self.pca_results["n_components"]
            self.component_options = [f"PC{i + 1}" for i in range(n_comp)]
            self.component_combo["values"] = self.component_options

            if n_comp >= 2:
                self.component_var.set("PC2")
            else:
                self.component_var.set("PC1")

            self.status_var.set("PCA completed!")
            messagebox.showinfo("Success", f"Computed {n_comp} components.")

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
            self._show_image_window(eigen, f"{selected} (Eigenimage)")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    @staticmethod
    def _frame_for_tiff(frame):
        """Prepare one frame for 16-bit TIFF write (2D grayscale preferred)."""
        arr = np.asarray(frame)
        while arr.ndim > 2:
            arr = np.mean(arr, axis=-1)
        if arr.dtype != np.uint16:
            arr = np.clip(arr, 0, 65535).astype(np.uint16)
        return arr

    def _save_stream_tiffs(self, base_dir):
        """Write each time index as frames/frame_XXXX.tiff (uint16)."""
        frames_dir = base_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Expect (H, W, T) or (H, W, T, C)
        data = np.asarray(self.data)
        if data.ndim < 3:
            raise ValueError(f"Stream data must be 3D+ (H,W,T); got shape {data.shape}")

        n_frames = data.shape[2]
        for t in range(n_frames):
            frame = self._frame_for_tiff(data[:, :, t, ...] if data.ndim > 3 else data[:, :, t])
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

            if save_npy:
                np.save(base_dir / "raw_data.npy", self.data)
                notes.append("raw_data.npy")

            if save_tiff:
                n_frames, frames_dir = self._save_stream_tiffs(base_dir)
                notes.append(f"{n_frames} TIFFs in {frames_dir.name}/")

            if self.pca_results is not None:
                np.save(base_dir / "eigenimages.npy", self.pca_results["eigenimages"])

                for i in range(self.pca_results["eigenimages"].shape[0]):
                    eigen = self.pca_results["eigenimages"][i]
                    norm = ((eigen - eigen.min()) / (eigen.max() - eigen.min() + 1e-8) * 255).astype(
                        np.uint8
                    )
                    cv2.imwrite(str(base_dir / f"PC{i + 1}.tiff"), norm)

                np.save(base_dir / "temporal_components.npy", self.pca_results["temporal_components"])

                with open(base_dir / "explained_variance.csv", "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Component", "Explained Variance Ratio"])
                    for i, var in enumerate(self.pca_results["explained_variance_ratio"]):
                        writer.writerow([f"PC{i + 1}", var])

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
        img = Image.fromarray(img_norm).resize((600, 500), Image.BILINEAR)
        imgtk = ImageTk.PhotoImage(img)
        label = ttk.Label(win, image=imgtk)
        label.image = imgtk
        label.pack()
