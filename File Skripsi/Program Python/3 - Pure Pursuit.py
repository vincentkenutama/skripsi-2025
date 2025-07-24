import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from PIL import Image, UnidentifiedImageError
from math import cos as _cos, sin as _sin, radians as _rad
import pandas as pd

# --- KONFIGURASI APLIKASI ---
UDP_IP = '127.0.0.1'
UDP_PORT = 5005
TRACK_IMAGE_PATH = r"D:\Data Kuliahan\maestro2024\PathPlanning\lapangan_gui.png"
REFERENCE_PATH_FILE = "path.csv"
TARGET_WIDTH = 12000
TARGET_HEIGHT = 6500

# --- FUNGSI LISTENER UDP ---
def udp_listener_thread(q, sock, stop_event):
    print("UDP listener thread dimulai.")
    while not stop_event.is_set():
        try:
            sock.settimeout(1.0)
            data_bytes, _ = sock.recvfrom(1024)
            data_str = data_bytes.decode('utf-8')
            parts = data_str.split(',')
            if len(parts) == 5:
                values = tuple(map(float, parts))
                q.put(values)
        except socket.timeout:
            continue
        except (ValueError, IndexError):
            print(f"Peringatan: Menerima data UDP tidak valid: {data_str}")
        except Exception as e:
            if not stop_event.is_set():
                print(f"Error kritis di listener UDP: {e}")
            break
    print("UDP listener thread dihentikan.")

# --- KELAS UTAMA APLIKASI GUI ---
class PurePursuitViewerApp:
    def __init__(self, master):
        self.master = master
        master.title("Real-time Pure Pursuit Viewer")
        master.geometry("900x950")

        self.robot_path_x, self.robot_path_y = [], []
        
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((UDP_IP, UDP_PORT))
        except OSError as e:
            messagebox.showerror("Socket Error", f"Gagal bind ke port {UDP_PORT}.\n\nError: {e}")
            self.master.destroy()
            raise

        self._create_widgets()
        self._load_and_process_track_image(TRACK_IMAGE_PATH)
        self._load_reference_path(REFERENCE_PATH_FILE)
        self._start_listener()
        
        self._animation = animation.FuncAnimation(self.fig, self._update_plot, interval=50, blit=True, init_func=self._init_plot)
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_widgets(self):
        control_frame = ttk.Frame(self.master, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(control_frame, text="Reset Path", command=self._reset_data).pack(side=tk.LEFT, padx=5, ipady=3)
        
        self.status_label = ttk.Label(control_frame, text="Menunggu data dari Unity...", font=("Helvetica", 10), wraplength=500)
        self.status_label.pack(side=tk.RIGHT, padx=10)

        plot_frame = ttk.Frame(self.master); plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.fig, self.ax = plt.subplots(); self.ax.set_aspect('equal', adjustable='box'); self.ax.set_title("Visualisasi Pure Pursuit")
        self.ax.set_xlabel("Posisi X (meter)"); self.ax.set_ylabel("Posisi Y (meter)"); self.ax.grid(True, linestyle='--', alpha=0.6)
        
        self.reference_path_line, = self.ax.plot([], [], 'k--', linewidth=1.5, label="Path Referensi", zorder=1)
        
        # <<< PERBAIKAN 1: Tambahkan animated=True untuk jejak robot >>>
        self.path_line, = self.ax.plot([], [], 'c-', linewidth=2, label="Jejak Robot", zorder=2, animated=True)
        
        self.target_marker, = self.ax.plot([], [], 'go', markersize=10, label="Titik Target", zorder=4, animated=True)
        self.lookahead_line, = self.ax.plot([], [], 'r--', linewidth=1, label="Garis Lookahead", zorder=3, animated=True)
        self.robot_pos_marker, = self.ax.plot([], [], 'ro', markersize=8, label="Robot", zorder=5, animated=True)
        self.robot_orient_line, = self.ax.plot([], [], 'r-', linewidth=2, zorder=6, animated=True)
        
        self.ax.legend(loc='upper right')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False); toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _load_and_process_track_image(self, filepath):
        try: original_img = Image.open(filepath)
        except (FileNotFoundError, UnidentifiedImageError) as e: messagebox.showerror("Image Load Error", f"Gagal memuat gambar dari:\n{filepath}\n\nError: {e}"); return
        w, h = original_img.width, original_img.height; target_size = (TARGET_WIDTH, TARGET_HEIGHT) if w > h else (TARGET_HEIGHT, TARGET_WIDTH)
        processed_img = original_img.resize(target_size, Image.Resampling.LANCZOS).transpose(Image.FLIP_LEFT_RIGHT).rotate(180)
        img_width_m, img_height_m = processed_img.width / 1000.0, processed_img.height / 1000.0
        plot_extent = [0, img_width_m, 0, img_height_m]
        self.ax.imshow(processed_img, extent=plot_extent, aspect='equal', zorder=0, origin='lower')
        self.ax.set_xlim(plot_extent[0], plot_extent[1]); self.ax.set_ylim(plot_extent[2], plot_extent[3]); self.canvas.draw_idle()
    
    def _load_reference_path(self, filepath):
        try:
            path_df = pd.read_csv(filepath); ref_x = path_df['x'].values; ref_y = path_df['y'].values
            self.reference_path_line.set_data(ref_x, ref_y); self.canvas.draw_idle()
            print(f"Path referensi dimuat dari '{filepath}'.")
        except FileNotFoundError: print(f"Peringatan: File path referensi '{filepath}' tidak ditemukan.")
        except Exception as e: messagebox.showerror("Path File Error", f"Gagal membaca file '{filepath}'.\nPastikan formatnya benar.\n\nError: {e}")

    def _start_listener(self):
        self.listener_thread = threading.Thread(target=udp_listener_thread, args=(self.data_queue, self.sock, self.stop_event))
        self.listener_thread.daemon = True; self.listener_thread.start()
        
    def _init_plot(self):
        """Fungsi inisialisasi untuk blitting. Mengembalikan semua artis yang di-blit."""
        self.robot_pos_marker.set_data([], [])
        self.robot_orient_line.set_data([], [])
        self.target_marker.set_data([], [])
        self.lookahead_line.set_data([], [])
        self.path_line.set_data([], []) # <<< PERBAIKAN 2: Inisialisasi jejak di sini juga
        
        # Kembalikan semua elemen yang memiliki animated=True
        return self.path_line, self.robot_pos_marker, self.robot_orient_line, self.target_marker, self.lookahead_line
    
    def _update_plot(self, frame):
        """Fungsi animasi yang dioptimalkan."""
        latest_data = None
        while not self.data_queue.empty():
            try:
                latest_data = self.data_queue.get_nowait()
            except queue.Empty:
                break
        
        if latest_data:
            rx, ry, ra, tx, ty = latest_data
            
            self.robot_path_x.append(rx)
            self.robot_path_y.append(ry)
            self.path_line.set_data(self.robot_path_x, self.robot_path_y)
            
            self._update_robot_marker(rx, ry, ra)
            self.target_marker.set_data([tx], [ty])
            self.lookahead_line.set_data([rx, tx], [ry, ty])

            status_text = f"Robot: ({rx:.2f}, {ry:.2f}, {ra:.1f}°) | Target: ({tx:.2f}, {ty:.2f})"
            self.status_label.config(text=status_text)
        
        # <<< PERBAIKAN 3: Kembalikan jejak sebagai bagian dari tuple blit >>>
        return self.path_line, self.robot_pos_marker, self.robot_orient_line, self.target_marker, self.lookahead_line

    def _update_robot_marker(self, x, y, angle_deg):
        self.robot_pos_marker.set_data([x], [y]); length = 0.3; angle_rad = _rad(angle_deg)
        end_x = x + length * _cos(angle_rad); end_y = y + length * _sin(angle_rad)
        self.robot_orient_line.set_data([x, end_x], [y, end_y])
    
    def _reset_data(self):
        """Mereset jejak robot yang telah dilalui."""
        if messagebox.askokcancel("Konfirmasi Reset", "Apakah Anda yakin ingin menghapus semua jejak robot?"):
            print("Mereset jejak robot...")
            self.robot_path_x.clear()
            self.robot_path_y.clear()
            # Tidak perlu memanggil set_data di sini karena _init_plot akan menanganinya
            # saat animasi me-reset.
    
    def _on_closing(self):
        if messagebox.askokcancel("Keluar", "Apakah Anda yakin ingin keluar?"):
            self.stop_event.set(); self.sock.close()
            if hasattr(self, 'listener_thread') and self.listener_thread.is_alive(): self.listener_thread.join(timeout=1.5)
            self.master.destroy()

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = PurePursuitViewerApp(root)
        root.mainloop()
    except Exception as e:
        import traceback; messagebox.showerror("Fatal Error", f"Aplikasi gagal dijalankan.\n\nError: {e}")
        print(f"Gagal menjalankan aplikasi: {e}"); traceback.print_exc()