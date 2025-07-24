import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# --- Konfigurasi UDP ---
UDP_IP = '127.0.0.1'
UDP_PORT = 5005

# --- Fungsi Listener UDP (Tidak ada perubahan) ---
def udp_listener_thread(q, sock, stop_event):
    """Mendengarkan data UDP dan memasukkannya ke dalam antrian."""
    print("UDP listener thread dimulai.")
    while not stop_event.is_set():
        try:
            sock.settimeout(1.0)
            data_bytes, _ = sock.recvfrom(1024)
            data_str = data_bytes.decode('utf-8')
            parts = data_str.split(',')
            if len(parts) == 3:
                x, y, angle = map(float, parts)
                q.put((x, y, angle))
        except socket.timeout:
            continue
        except (ValueError, IndexError):
            print(f"Menerima data tidak valid: {data_str}")
        except Exception as e:
            if not stop_event.is_set():
                print(f"Error di listener UDP: {e}")
            break
    print("UDP listener thread dihentikan.")

class OdometryPlotterApp:
    def __init__(self, master):
        self.master = master
        master.title("Real-time Odometry Plotter")
        master.geometry("900x900") # Sedikit lebih lebar untuk input baru

        # --- Inisialisasi data dan state ---
        self.x_path = []
        self.y_path = []
        self.current_x, self.current_y, self.current_angle = 0.0, 0.0, 0.0
        
        # --- Setup Networking ---
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((UDP_IP, UDP_PORT))
        
        # <<< TAMBAHAN >>>: Variabel untuk batas plot statis
        self.x_min_var = tk.StringVar(value="-10.0")
        self.x_max_var = tk.StringVar(value="10.0")
        self.y_min_var = tk.StringVar(value="-10.0")
        self.y_max_var = tk.StringVar(value="10.0")

        self._create_widgets()
        self._start_listener()
        
        # Terapkan batas awal saat aplikasi dimulai
        self._apply_plot_limits()

        self._animation = animation.FuncAnimation(self.fig, self._update_plot, interval=100, blit=False)
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_widgets(self):
        """Membuat semua elemen GUI."""
        # --- Frame Kontrol (Kiri) ---
        control_frame = ttk.Frame(self.master, padding="10")
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(control_frame, text="Kontrol", font=("Helvetica", 16, "bold")).pack(pady=(0, 10), anchor='w')
        ttk.Button(control_frame, text="Reset Odometry Data", command=self._reset_data).pack(fill=tk.X, pady=5, ipady=5)

        # <<< TAMBAHAN >>>: Frame dan input untuk batas plot
        limits_frame = ttk.LabelFrame(control_frame, text="Batas Plot (meter)", padding="10")
        limits_frame.pack(fill=tk.X, pady=20)
        
        self._create_limit_entry(limits_frame, "X Min:", self.x_min_var)
        self._create_limit_entry(limits_frame, "X Max:", self.x_max_var)
        self._create_limit_entry(limits_frame, "Y Min:", self.y_min_var)
        self._create_limit_entry(limits_frame, "Y Max:", self.y_max_var)
        
        ttk.Button(limits_frame, text="Apply Limits", command=self._apply_plot_limits).pack(fill=tk.X, pady=(10,0))
        
        self.status_label = ttk.Label(control_frame, text="Menunggu data...", font=("Helvetica", 12), wraplength=200)
        self.status_label.pack(side=tk.BOTTOM, pady=10)

        # --- Frame Plot (Kanan) ---
        plot_frame = ttk.Frame(self.master)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 10), pady=10)

        self.fig, self.ax = plt.subplots()
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.set_title("Jejak Odometri Robot")
        self.ax.set_xlabel("Posisi X (meter)")
        self.ax.set_ylabel("Posisi Y (meter)")
        self.ax.grid(True, linestyle='--', alpha=0.6)

        self.path_line, = self.ax.plot([], [], 'b-', label="Jejak Robot")
        self.robot_marker, = self.ax.plot([], [], 'ro', markersize=8, label="Posisi Robot")
        self.ax.legend()
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def _create_limit_entry(self, parent, label_text, text_variable):
        """Helper untuk membuat entry batas."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label_text, width=7).pack(side=tk.LEFT)
        ttk.Entry(frame, textvariable=text_variable, width=10).pack(side=tk.LEFT)

    def _start_listener(self):
        """Memulai thread listener UDP."""
        self.listener_thread = threading.Thread(
            target=udp_listener_thread,
            args=(self.data_queue, self.sock, self.stop_event)
        )
        self.listener_thread.daemon = True
        self.listener_thread.start()

    def _update_plot(self, frame):
        """Fungsi yang dipanggil secara berkala untuk memperbarui plot."""
        data_updated = False
        while not self.data_queue.empty():
            try:
                x, y, angle = self.data_queue.get_nowait()
                self.x_path.append(x)
                self.y_path.append(y)
                self.current_x, self.current_y, self.current_angle = x, y, angle
                data_updated = True
            except queue.Empty:
                break
        
        if data_updated:
            status_text = f"X: {self.current_x:.2f} | Y: {self.current_y:.2f} | Sudut: {self.current_angle:.1f}°"
            self.status_label.config(text=status_text)
            
            # Update data di plot
            self.path_line.set_data(self.x_path, self.y_path)
            self.robot_marker.set_data([self.current_x], [self.current_y])
            
            # <<< PERBAIKAN >>>: Hapus rescaling otomatis
            # self.ax.relim()
            # self.ax.autoscale_view()
            
            # Gambar ulang canvas
            self.canvas.draw_idle()

    def _apply_plot_limits(self):
        """Menerapkan batas plot dari input GUI."""
        try:
            x_min = float(self.x_min_var.get())
            x_max = float(self.x_max_var.get())
            y_min = float(self.y_min_var.get())
            y_max = float(self.y_max_var.get())
            
            if x_min >= x_max or y_min >= y_max:
                messagebox.showerror("Input Error", "Nilai Min harus lebih kecil dari nilai Max.")
                return

            self.ax.set_xlim(x_min, x_max)
            self.ax.set_ylim(y_min, y_max)
            
            # Gambar ulang canvas untuk menerapkan batas baru
            self.canvas.draw_idle()
            print(f"Batas plot diatur ke: X({x_min}, {x_max}), Y({y_min}, {y_max})")

        except ValueError:
            messagebox.showerror("Input Error", "Batas plot harus berupa angka yang valid.")
    
    def _reset_data(self):
        """Menghapus semua data odometri dan membersihkan plot."""
        print("Mereset data odometri...")
        self.x_path.clear()
        self.y_path.clear()
        
        self.path_line.set_data([], [])
        self.robot_marker.set_data([], [])
        
        # <<< PERBAIKAN >>>: Tidak perlu rescale, cukup gambar ulang
        self.canvas.draw_idle()
        
        self.status_label.config(text="Data direset. Menunggu data baru...")

    def _on_closing(self):
        """Menangani penutupan aplikasi dengan bersih."""
        print("Menutup aplikasi...")
        self.stop_event.set()
        self.sock.close()
        if hasattr(self, 'listener_thread') and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=1.5)
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = OdometryPlotterApp(root)
    root.mainloop()