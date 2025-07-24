import socket
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox  # Ditambahkan messagebox untuk notifikasi error
from collections import deque
import pandas as pd
import matplotlib.animation as animation # <--- PERBAIKAN DI SINI
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# --- Konfigurasi dipindahkan ke dalam kelas atau sebagai konstanta ---
PYTHON_IP = '127.0.0.1'
PYTHON_PORT_LISTEN = 5005
UNITY_IP = '127.0.0.1'
UNITY_PORT_SEND = 5006
MAX_DATA_POINTS_PLOT = 200

# --- Listener Function (Lebih baik sebagai metode statis atau di luar kelas) ---
# Tidak ada perubahan besar di sini, sudah cukup baik.
def udp_listener_thread(sock, q, stop_event):
    """Fungsi ini berjalan di thread terpisah untuk mendengarkan data UDP."""
    print("UDP listener thread dimulai.")
    while not stop_event.is_set():
        try:
            sock.settimeout(1.0)
            data_bytes, _ = sock.recvfrom(1024)
            data_str = data_bytes.decode('utf-8')
            q.put((time.time(), float(data_str)))
        except socket.timeout:
            continue
        except (ValueError, UnicodeDecodeError):
            print("Peringatan: Menerima data UDP tidak valid.")
            continue
        except Exception as e:
            if not stop_event.is_set():
                print(f"Error kritis di UDP listener: {e}")
            break
    print("UDP listener thread dihentikan.")

class PIDControllerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("PID Controller & UDP Plotter")
        self.master.geometry("850x700")

        # --- Inisialisasi Atribut Kelas (Enkapsulasi) ---
        self.sock = self._setup_socket()
        self.data_queue = queue.Queue()
        self.stop_event = threading.Event()

        # Data untuk plot dan rekaman
        self.plot_data = deque(maxlen=MAX_DATA_POINTS_PLOT)
        self.session_recorder = []
        self.session_pid_params = {}
        
        # State aplikasi
        self.is_running = False
        self.start_time = 0
        self.current_setpoint = 180.0

        # Panggil metode untuk membangun UI dan memulai listener
        self._create_widgets()
        self._start_listener_thread()
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_socket(self):
        """Membungkus setup socket dalam satu metode."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((PYTHON_IP, PYTHON_PORT_LISTEN))
            return sock
        except OSError as e:
            messagebox.showerror("Socket Error", f"Gagal bind ke port {PYTHON_PORT_LISTEN}.\nPastikan tidak ada aplikasi lain yang menggunakan port ini.\n\nError: {e}")
            self.master.destroy()
            raise

    def _create_widgets(self):
        """Membangun semua elemen GUI dalam satu metode terpusat."""
        # --- Frame Kontrol (Kiri) ---
        control_frame = ttk.Frame(self.master, padding="10")
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        ttk.Label(control_frame, text="Kontrol PID", font=("Helvetica", 16, "bold")).pack(pady=(0, 10))

        # Variabel Tkinter
        self.kp_var = tk.StringVar(value="1.0")
        self.ki_var = tk.StringVar(value="0.1")
        self.kd_var = tk.StringVar(value="0.05")
        self.setpoint_var = tk.StringVar(value=str(self.current_setpoint))

        # Membuat input fields menggunakan metode helper
        self._create_entry(control_frame, "Kp:", self.kp_var)
        self._create_entry(control_frame, "Ki:", self.ki_var)
        self._create_entry(control_frame, "Kd:", self.kd_var)
        self._create_entry(control_frame, "Setpoint:", self.setpoint_var)

        ttk.Button(control_frame, text="Apply PID Settings", command=self.apply_pid_settings).pack(pady=10, ipady=5, fill=tk.X)
        
        self.start_stop_button = ttk.Button(control_frame, text="Start PID", command=self.toggle_pid_control)
        self.start_stop_button.pack(pady=10, ipady=8, fill=tk.X)
        
        self.save_button = ttk.Button(control_frame, text="Save Session to Excel", command=self.save_to_excel, state=tk.DISABLED)
        self.save_button.pack(pady=10, ipady=5, fill=tk.X)

        self.status_label = ttk.Label(control_frame, text="Status: Ready", foreground="blue", wraplength=200) # wraplength untuk pesan error panjang
        self.status_label.pack(side=tk.BOTTOM, pady=10)

        # --- Frame Plot (Kanan) ---
        plot_frame = ttk.Frame(self.master)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0,10), pady=10)
        
        self.fig, self.ax = plt.subplots(facecolor='#f0f0f0') # Samakan warna background
        self.ax.set_facecolor('#ffffff')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Simpan referensi animasi untuk mencegah garbage collection
        self._animation = animation.FuncAnimation(self.fig, self._update_plot, interval=50, blit=False)

    def _create_entry(self, parent, label_text, text_variable):
        """Metode helper untuk membuat label dan entry."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)
        ttk.Label(frame, text=label_text, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Entry(frame, textvariable=text_variable, width=15).pack(side=tk.LEFT, expand=True, fill=tk.X)
    
    def _start_listener_thread(self):
        self.listener_thread = threading.Thread(target=udp_listener_thread, args=(self.sock, self.data_queue, self.stop_event))
        self.listener_thread.daemon = True
        self.listener_thread.start()

    # --- Logika Aplikasi ---
    def toggle_pid_control(self):
        if self.is_running:
            # Proses STOP
            self._send_command_to_unity("stop_pid")
            self.status_label.config(text=f"STOPPED. {len(self.session_recorder)} data points recorded.", foreground="red")
            self.start_stop_button.config(text="Start PID")
            self.save_button.config(state=tk.NORMAL)
            self.is_running = False
        else:
            # Proses START
            if not self.apply_pid_settings(is_starting=True):
                # Jangan mulai jika parameter awal tidak valid
                return

            self._reset_session_data()
            self._send_command_to_unity("start_pid")
            self.status_label.config(text="Status: PID Running", foreground="green")
            self.start_stop_button.config(text="Stop PID")
            self.save_button.config(state=tk.DISABLED)
            self.start_time = time.time()
            self.is_running = True

    def apply_pid_settings(self, is_starting=False):
        """Mengirim pengaturan PID ke Unity. Mengembalikan True jika sukses."""
        try:
            params = {
                'Kp': float(self.kp_var.get()),
                'Ki': float(self.ki_var.get()),
                'Kd': float(self.kd_var.get()),
                'Setpoint': float(self.setpoint_var.get())
            }
        except ValueError:
            self.status_label.config(text="Error: Input harus berupa angka valid.", foreground="red")
            messagebox.showerror("Input Error", "Pastikan semua nilai Kp, Ki, Kd, dan Setpoint adalah angka.")
            return False

        if is_starting:
            self.session_pid_params = params
        
        self.current_setpoint = params['Setpoint']
        message = f"pid,{params['Kp']},{params['Ki']},{params['Kd']},{params['Setpoint']}"
        self._send_command_to_unity(message)
        
        if not self.is_running:
            self.status_label.config(text="PID settings applied. Ready to start.", foreground="blue")
        return True

    def _send_command_to_unity(self, command):
        try:
            self.sock.sendto(command.encode('utf-8'), (UNITY_IP, UNITY_PORT_SEND))
        except Exception as e:
            print(f"Gagal mengirim perintah '{command}': {e}")
            self.status_label.config(text=f"Error sending command: {e}", foreground="red")

    def _reset_session_data(self):
        self.plot_data.clear()
        self.session_recorder.clear()
        self._update_plot(None)
        print("Grafik dan data rekaman telah direset.")

    def _update_plot(self, frame):
        # 1. Proses antrian data
        if self.is_running:
            while not self.data_queue.empty():
                try:
                    timestamp, value = self.data_queue.get_nowait()
                    self.plot_data.append(value)
                    elapsed_time = timestamp - self.start_time
                    self.session_recorder.append({
                        "Waktu (s)": elapsed_time, "Sudut Aktual": value, "Setpoint": self.current_setpoint
                    })
                except queue.Empty:
                    break
        
        # 2. Gambar ulang plot
        self.ax.clear()
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.ax.set_title("Sudut Real-time dari Unity")
        self.ax.set_xlabel("Sampel (Gunakan toolbar di bawah untuk scroll/pan/zoom)")
        self.ax.set_ylabel("Sudut (derajat)")
        self.ax.set_ylim(-10, 370)

        if self.plot_data:
            self.ax.plot(range(len(self.plot_data)), list(self.plot_data), 'r-', label='Sudut Aktual')
        if self.is_running:
            self.ax.axhline(y=self.current_setpoint, color='b', linestyle='--', label='Setpoint')
        
        # Selalu tampilkan legenda jika ada label yang didefinisikan
        if self.ax.get_legend_handles_labels()[0]:
            self.ax.legend(loc='upper left')
        
        # Perlu dipanggil untuk menggambar ulang canvas
        self.canvas.draw_idle()

    def save_to_excel(self):
        if not self.session_recorder:
            messagebox.showwarning("No Data", "Tidak ada data sesi untuk disimpan.")
            return

        filepath = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Workbook", "*.xlsx")], title="Simpan Sesi PID")
        if not filepath:
            self.status_label.config(text="Penyimpanan dibatalkan.", foreground="orange")
            return

        self.status_label.config(text="Menyimpan ke Excel...", foreground="blue")
        self.master.update_idletasks()

        try:
            df_data = pd.DataFrame(self.session_recorder)
            df_data['Waktu (s)'] = df_data['Waktu (s)'].round(4)
            df_data['Sudut Aktual'] = df_data['Sudut Aktual'].round(4)
            df_params = pd.DataFrame([self.session_pid_params])

            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df_data.to_excel(writer, sheet_name='PID_Data', index=False)
                df_params.to_excel(writer, sheet_name='PID_Parameters', index=False)
            
            self.status_label.config(text="Data berhasil disimpan!", foreground="green")
            messagebox.showinfo("Sukses", f"Data berhasil disimpan ke:\n{filepath}")
        except Exception as e:
            self.status_label.config(text=f"Error saat menyimpan: {e}", foreground="red")
            messagebox.showerror("Save Error", f"Gagal menyimpan file Excel.\n\nError: {e}")

    def _on_closing(self):
        """Menangani penutupan jendela aplikasi dengan bersih."""
        if messagebox.askokcancel("Keluar", "Apakah Anda yakin ingin keluar?"):
            print("Menutup aplikasi...")
            self.stop_event.set()
            if self.sock:
                self.sock.close()
            # Beri waktu sedikit untuk thread selesai
            if hasattr(self, 'listener_thread'):
                self.listener_thread.join(timeout=1.5)
            self.master.destroy()

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = PIDControllerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Gagal menjalankan aplikasi: {e}")