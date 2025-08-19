import pandas as pd
import matplotlib.pyplot as plt

# -----------------------------
# Load data dari Excel
# -----------------------------
# Ganti "data.xlsx" dengan nama file Excel kamu
df = pd.read_excel("pid 2.xlsx")

time = df["Waktu (s)"].values
actual = df["Sudut Aktual"].values
setpoint = df["Setpoint"].values[0]  # diasumsikan setpoint konstan

# -----------------------------
# Analisis Step Response
# -----------------------------
y0 = actual[0]              # nilai awal
y_final = actual[-1]        # nilai akhir (steady state)
delta_y = setpoint - y0     # besar step

# Rise Time (10% → 90%)
y_10 = y0 + 0.1 * delta_y
y_90 = y0 + 0.9 * delta_y

t_10 = next(t for t, y in zip(time, actual) if y >= y_10)
t_90 = next(t for t, y in zip(time, actual) if y >= y_90)
rise_time = t_90 - t_10

# Maximum Overshoot
max_val = max(actual)
overshoot = ((max_val - setpoint) / delta_y) * 100 if delta_y != 0 else 0

# Settling Time (±2% band)
tolerance = 0.02 * abs(delta_y)
settling_time = None
for i in range(len(actual)-1, -1, -1):
    if abs(actual[i] - setpoint) > tolerance:
        settling_time = time[i+1] if i+1 < len(time) else time[-1]
        break

# Steady-State Error (SSE)
sse = setpoint - y_final

# -----------------------------
# Hasil Analisis
# -----------------------------
print("=== Step Response Analysis ===")
print(f"Rise Time (Tr): {rise_time:.4f} s")
print(f"Maximum Overshoot (Mp): {overshoot:.2f} %")
print(f"Settling Time (Ts): {settling_time:.4f} s")
print(f"Steady-State Error (SSE): {sse:.4f}")

# -----------------------------
# Plot Response
# -----------------------------
plt.figure(figsize=(10,5))
plt.plot(time, actual, label="Sudut Aktual")
plt.axhline(setpoint, color='r', linestyle='--', label="Setpoint")
plt.axhline(setpoint + tolerance, color='g', linestyle='--', alpha=0.5, label="±2% Band")
plt.axhline(setpoint - tolerance, color='g', linestyle='--', alpha=0.5)

plt.xlabel("Waktu (s)")
plt.ylabel("Sudut (deg)")
plt.title("Step Response Analysis")
plt.legend()
plt.grid(True)
plt.show()
