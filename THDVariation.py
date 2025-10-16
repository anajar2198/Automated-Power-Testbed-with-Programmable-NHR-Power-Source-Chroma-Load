import socket, time, math, matplotlib.pyplot as plt, signal

# --- Configuration -----------------------------------------------------------
SIMULATOR_HOST = "192.168.0.149"
SIMULATOR_PORT = 5025
SIMULATOR_INSTRUMENT = 3
NOMINAL_VOLTAGE_V = 120.0
NOMINAL_FREQUENCY_HZ = 60.0

# --- Comprehensive Test Sequence Configuration ---
DWELL_TIME_S = 300  # 5 minutes for each stage

# A sequence of 12 harmonic scenarios to test.
HARMONIC_STAGES = [
    {'name': '1. Clean Sine Wave (Baseline)', 'harmonics': {1: (100, 0)}},
    {'name': '2. Low 3rd Harmonic (5%)',    'harmonics': {1: (100, 0), 3: (5, 0)}},
    {'name': '3. Med 3rd Harmonic (10%)',   'harmonics': {1: (100, 0), 3: (10, 0)}},
    {'name': '4. High 3rd Harmonic (20%)',  'harmonics': {1: (100, 0), 3: (20, 0)}},
    {'name': '5. Low 5th Harmonic (5%)',    'harmonics': {1: (100, 0), 5: (5, 0)}},
    {'name': '6. Med 5th Harmonic (10%)',   'harmonics': {1: (100, 0), 5: (10, 0)}},
    {'name': '7. High 5th Harmonic (15%)',  'harmonics': {1: (100, 0), 5: (15, 0)}},
    {'name': '8. Low 7th Harmonic (5%)',    'harmonics': {1: (100, 0), 7: (5, 0)}},
    {'name': '9. Combined 3rd and 5th',    'harmonics': {1: (100, 0), 3: (15, 0), 5: (10, 0)}},
    {'name': '10. Combined 3, 5, 7',       'harmonics': {1: (100, 0), 3: (12, 0), 5: (8, 0), 7: (5, 0)}},
    {'name': '11. Combined 3, 5, 7 with Phase ',       'harmonics': {1: (100, 0), 3: (12, 30), 5: (8, 45), 7: (5, 90)}},
    {'name': '12. High THD Mix with Phase', 'harmonics': {1: (100, 0), 3: (20, 15), 5: (15, 30), 7: (10, 45)}}
]

# --- Helper functions --------------------------------------------------------
def send(sock, cmd):
    sock.sendall((cmd + "\n").encode())

def handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("\n🛑 Hard stop requested (CTRL+C or q).")

signal.signal(signal.SIGINT, handle_stop)

def query(sock, cmd):
    send(sock, cmd)
    return sock.recv(4096).decode().strip().replace("\x00","")

def connect():
    s = socket.create_connection((SIMULATOR_HOST, SIMULATOR_PORT), timeout=10)
    s.sendall(f"INSTrument:NSELect {SIMULATOR_INSTRUMENT}\n".encode())
    print("✅ Connected to Grid Simulator.")
    return s

def gen_waveform(harmonics=None, fundamental_amp=100.0):
    """
    Generate one cycle (360 points) of a composite harmonic waveform.

    Parameters
    ----------
    harmonics : dict[int, tuple[float, float]]
        Dictionary of {harmonic_order: (amplitude_percent, phase_deg)}.
        Example: {1: (100, 0), 3: (20, 0), 5: (10, 0), 11: (6, 5)}
        means:
            y = 100*sin(1θ + 0°) + 20*sin(3θ + 0°) + 10*sin(5θ + 0°) + 6*sin(11θ + 5°)
    fundamental_amp : float
        Base amplitude (percent). Default 100%.

    Returns
    -------
    list[float] : 360 normalized waveform samples (−1 to +1)
    """
    if harmonics is None:
        # Default example: fundamental + 3rd + 5th
        harmonics = {1: (100, 0), 3: (20, 0), 5: (10, 0)}

    data = []
    for deg in range(360):
        th = math.radians(deg)
        y = 0.0
        for n, (amp, ph_deg) in harmonics.items():
            y += (amp / 100.0) * math.sin(n * th + math.radians(ph_deg))
        data.append(y)

    # Normalize to ±1
    max_abs = max(abs(v) for v in data)
    return [v / max_abs for v in data]

def responsive_sleep(duration_s):
    """
    A replacement for time.sleep() that is responsive to the STOP_REQUESTED flag.
    It sleeps in 1-second intervals and checks the flag.
    Returns True if sleep was interrupted, False otherwise.
    """
    for _ in range(int(duration_s)):
        if STOP_REQUESTED:
            return True  # Interrupted
        time.sleep(1)
    return False # Completed without interruption
def upload_waveform(sock, data, user_slot="USER1"):
    """
    Prepares simulator and uploads waveform data to a specified user slot.
    NOTE: This function does NOT turn the output off, assuming it's already on.
    """
    print(f"   (Loading next waveform into {user_slot} in the background...)")
    # We no longer turn output off/on here. We switch to STANDARD to be safe.
    # send(sock, "FUNC STANDARD") 
    time.sleep(0.2)
    for q in range(4):
        chunk = ",".join(f"{v:.4f}" for v in data[q*90:(q+1)*90])
        send(sock, f"DATA Q{q+1},{chunk}")
        time.sleep(0.1)
    send(sock, f"DATA:LOAD {user_slot}")

    # 2. Send the *OPC? query. This will block until the DATA:LOAD is finished.
    print(f"   Waiting for {user_slot} to finish programming...")
    confirmation = query(sock, "*OPC?")
    
    # 3. Check the confirmation from *OPC?
    if '1' in confirmation:
        print(f"   ✅ {user_slot} is pre-loaded and ready.")
    else:
        # If *OPC? failed or returned something else, check the error queue.
        error = query(sock, "SYSTem:ERRor?")
        print(f"   ⚠️ Error loading {user_slot}. OPC Confirmation: '{confirmation}'. Error: '{error}'")

# --- Upload waveform ---------------------------------------------------------
def upload_user1(sock, data):
    send(sock, "OUTPut OFF")
    send(sock, "FUNC STANDARD")
    time.sleep(0.5)
    for q in range(4):
        chunk = ",".join(f"{v:.4f}" for v in data[q*90:(q+1)*90])
        send(sock, f"DATA Q{q+1},{chunk}")
        time.sleep(0.1)
    send(sock, "DATA:LOAD USER1")
    error = query(sock, "SYSTem:ERRor?")
    if "No error" not in error:
        print(f"⚠️ Error after loading waveform: {error}")
    else:
        print("✅ Waveform programmed successfully to USER1.")

# # --- Read waveform back ------------------------------------------------------
# def read_user_waveform(sock, user="USER1"):
#     send(sock, f"DATA:LOAD {user}")
#     all_pts = []
#     for q in range(1, 5):
#         resp = query(sock, f"DATA? Q{q}")
#         vals = [float(x) for x in resp.split(",") if x.strip()]
#         all_pts.extend(vals)
#     return all_pts
def read_user_waveform(sock, user_slot="USER1"):
    """
    Reads a waveform and defensively checks that each of the 4 quadrants
    returns exactly 90 data points.
    """
    confirmation = query(sock, f"DATA:LOAD? {user_slot}")
    time.sleep(0.3) # Slightly longer delay for internal transfer

    # 2. Check if the response is '1' to confirm the operation succeeded.
    if '1' not in confirmation:
        print(f"❌ READ-BACK FAILURE: Command 'DATA:LOAD? {user_slot}' failed.")
        print(f"   Instrument responded: '{confirmation}' instead of '1'.")

    all_pts = []
    for q in range(1, 5):
        resp_raw = query(sock, f"DATA? Q{q}")
        
        vals_for_quadrant = []
        if resp_raw:
            # Isolate the first line to prevent concatenation errors
            first_line = resp_raw.splitlines()[0]
            number_strings = first_line.split(',')

            for num_str in number_strings:
                clean_str = num_str.strip()
                if not clean_str: continue
                try:
                    vals_for_quadrant.append(float(clean_str))
                except ValueError:
                    # This handles individual corrupted numbers
                    print(f"⚠️ Warning: Skipping corrupted data point '{clean_str}' in {user_slot} Q{q}.")
        
        # --- DEFENSIVE CHECK ---
        # Verify we got exactly 90 points from the quadrant.
        if len(vals_for_quadrant) == 90:
            all_pts.extend(vals_for_quadrant)
        else:
            # If not, report a critical failure and abort.
            print(f"❌ READ-BACK FAILURE: Expected 90 points from {user_slot} Q{q}, but received {len(vals_for_quadrant)}.")
            print(f"   Raw response for this quadrant was: '{resp_raw}'")
            return [] # Abort and return an empty list

    # This code is only reached if all 4 quadrants succeed
    return all_pts
STOP_REQUESTED = False
# ---------- THD via discrete Fourier series ----------
def thd_from_cycle(samples, max_h=50):
    """
    samples: one cycle, uniformly sampled (len=360)
    max_h: highest harmonic to include in THD numerator
    Returns: (thd_frac, thd_percent, V1_rms, harmonics_rms_dict)
    """
    x = samples[:]
    N = len(x)
    # remove DC
    mean = sum(x)/N
    x = [v - mean for v in x]

    # DFS coefficients for sine/cos bases at integer harmonics
    # Continuous-time sinusoid of amplitude A has rms = A/sqrt(2).
    # For discrete series with N points:
    #   a_n = (2/N) * sum x[k]*cos(n*theta_k), b_n = (2/N) * sum x[k]*sin(n*theta_k),
    #   amplitude_n = sqrt(a_n^2 + b_n^2),  Vn_rms = amplitude_n / sqrt(2)
    harmonics_rms = {}
    for n in range(1, max_h+1):
        a = 0.0; b = 0.0
        for k, v in enumerate(x):
            th = math.radians(k)  # 360 samples → 1° per sample
            a += v * math.cos(n * th)
            b += v * math.sin(n * th)
        a *= (2.0 / N)
        b *= (2.0 / N)
        amp = math.hypot(a, b)
        Vn_rms = amp / math.sqrt(2.0)
        harmonics_rms[n] = Vn_rms

    V1 = harmonics_rms.get(1, 0.0)
    num = math.sqrt(sum(v*v for n, v in harmonics_rms.items() if n >= 2))
    thd = (num / V1) if V1 > 0 else float('nan')
    return thd, thd*100.0, V1, harmonics_rms
# --- Main --------------------------------------------------------------------
# def main():
#     simulator_socket = None
#     try:
#         simulator_socket = connect()

#         # Generate and upload waveform
#         # wf = gen_waveform({1: (100, 0), 3: (20, 5), 5: (10, 20), 11: (6, 5)})
#         wf = gen_waveform({1: (100, 0), 3: (10, 0)})

#         upload_user1(simulator_socket, wf)

#         # Set the nominal voltage and frequency once at the start
#         send(simulator_socket, f"SOURce:VOLTage {NOMINAL_VOLTAGE_V}")
#         send(simulator_socket, f"SOURce:FREQuency {NOMINAL_FREQUENCY_HZ}")

#         send(simulator_socket, "OUTPut OFF")
#         time.sleep(0.5)
#         send(simulator_socket, "FUNC USER1")
#         time.sleep(0.5)
#         send(simulator_socket, "OUTPut ON")
#         print("⚡ Output ON → USER1 waveform @ 120 V / 60 Hz")
#         print("Active function:", query(simulator_socket, "FUNC?"))
#         print("Output state:", query(simulator_socket, "OUTPut?"))
#         print("System:", query(simulator_socket, "SYSTem:ERRor?"))
#         # --- until here ---

#         # Read waveform back and verify
#         wf_read = read_user_waveform(simulator_socket, "USER1")
#         thd, thd_pct, V1_rms, H = thd_from_cycle(wf, max_h=50)
#         print(f"Fundamental RMS (normalized units): {V1_rms:.6f}")
#         print(f"THD = {thd:.6f}  ({thd_pct:.2f}%)")
#         print(f"\n✅ Retrieved {len(wf_read)} points from USER1.")
#         print("First 10:", wf_read[:10])
#         print("Last 10 :", wf_read[-10:])
#         print("System :", query(simulator_socket, "SYSTem:ERRor?"))
#         responsive_sleep(60) # Stabilize

#         # --- Plot both sent and read waveform ---
#         plt.figure(figsize=(8,4))
#         plt.plot(wf, label="Sent waveform")
#         plt.plot(wf_read, "--", label="Read-back waveform")
#         plt.title("NHR USER1 Waveform (Sine + 3rd + 5th Harmonics)")
#         plt.xlabel("Sample Index (0–359)")
#         plt.ylabel("Amplitude (normalized)")
#         plt.grid(True)
#         plt.legend()
#         plt.tight_layout()
#         plt.show()
#         if not STOP_REQUESTED:
#             print("\n--- Test Completed Successfully ---")

#     except KeyboardInterrupt:
#         print("\nUser interrupted the test. Proceeding to save and shut down.")
#     except Exception as e:
#         print(f"\n❌ An error occurred during the test: {e}")
#     finally:
#         print("\nCleaning up and shutting down outputs...")
#         if simulator_socket:
#             try:
#                 simulator_socket.sendall(b'VOLTage 0\n'); time.sleep(1)
#                 simulator_socket.sendall(b'OUTPut OFF\n')
#                 simulator_socket.close()
#                 print("✅ Grid Simulator output OFF and connection closed.")
#             except Exception:
#                 print("⚠️ Warning: Could not cleanly close simulator connection.")

def main():
    simulator_socket = None
    try:
        simulator_socket = connect()
        send(simulator_socket, f"SOURce:VOLTage {NOMINAL_VOLTAGE_V}")
        send(simulator_socket, f"SOURce:FREQuency {NOMINAL_FREQUENCY_HZ}")

        # --- Test Setup ---
        # 1. Pre-load the very first stage's waveform before starting.
        print("--- Initializing Test: Pre-loading first stage ---")
        first_stage_data = gen_waveform(HARMONIC_STAGES[0]['harmonics'])
        # We use the original 'upload_user1' function just once for a clean start
        upload_user1(simulator_socket, first_stage_data) 

        # 2. Define our alternating slots
        current_slot = "USER1"
        next_slot = "USER2"

        # 3. Turn the output ON. It will stay on for the entire test.
        send(simulator_socket, f"FUNC {current_slot}")
        send(simulator_socket, "OUTPut ON")
        print("\n✅ Output is ON. Starting comprehensive harmonic test.")
        time.sleep(2)

        # --- Main Loop ---
        for i, stage in enumerate(HARMONIC_STAGES):
            if STOP_REQUESTED: break
            
            print(f"\n--- Activating Stage {i+1}/{len(HARMONIC_STAGES)}: {stage['name']} ---")
            
            
            # 1. Attempt to switch the waveform
            print(f"   Attempting to set function to {current_slot}...")
            # send(simulator_socket, "OUTPut OFF")
            time.sleep(0.5) # Use a slightly longer, safer delay
            send(simulator_socket, f"FUNC {current_slot}") 
            # send(simulator_socket, "OUTPut ON")
            time.sleep(1.0) # Let the output fully stabilize before querying

            # 2. VERIFY the result
            # ❗ REPLACE 'FUNC?' with the correct query from your manual!
            actual_function = query(simulator_socket, "FUNC?") 
            print(f"   - Commanded function: {current_slot}")
            print(f"   - Simulator reports active function: {actual_function}")

            # 3. Check if the change was successful
            if current_slot not in actual_function:
                print("   ❌ CRITICAL FAILURE: The simulator did NOT switch to the new waveform.")
                print("      The command may still be incorrect or the instrument is in a locked state.")
                break # Stop the test because it's not working
            else:
                print("   ✅ Waveform switch confirmed.")
                
            # Generate the waveform data once
            waveform_data = gen_waveform(stage['harmonics'])
            # Get the full tuple of results from the calculation
            thd_results = thd_from_cycle(waveform_data)
            # Extract just the percentage value (the second element, index 1)
            expected_thd_pct = thd_results[1]
            print(f"   Theoretical THD: {expected_thd_pct:.2f}%")
            if responsive_sleep(5):
                break
            # # # 5. In the background, prepare the NEXT stage (if one exists)
            if (i + 1) < len(HARMONIC_STAGES):
                next_stage_data = gen_waveform(HARMONIC_STAGES[i+1]['harmonics'])
                upload_waveform(simulator_socket, next_stage_data, next_slot)
                # --- FORENSIC ANALYSIS BLOCK ---
            #     print("   --- Forensic Read-Back ---")
            #     # 1. Read what's actually in the slot we just uploaded to
            #     read_back_next = read_user_waveform(simulator_socket, next_slot)
            #     thd_next_actual = thd_from_cycle(read_back_next)[1]
                
            #     # 2. Read what's in the currently active slot (should be unchanged)
            #     read_back_current = read_user_waveform(simulator_socket, current_slot)
            #     thd_current_actual = thd_from_cycle(read_back_current)[1]

            #     # 3. Compare with what we expected
            #     thd_next_expected = thd_from_cycle(next_stage_data)[1]
                
            #     print(f"   - Expected THD for {next_slot}: {thd_next_expected:.2f}%")
            #     print(f"   - Actual THD read from {next_slot}: {thd_next_actual:.2f}%")
            #     print(f"   - Actual THD read from {current_slot}: {thd_current_actual:.2f}%")
            #     print("   --------------------------")
                # --- END FORENSIC BLOCK ---
            # 6. Hold for the specified dwell time
            if responsive_sleep(DWELL_TIME_S):
                break

            # 7. Swap the slots for the next iteration
            current_slot, next_slot = next_slot, current_slot

        if not STOP_REQUESTED:
            print("\n--- All test stages completed successfully! ---")

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
    finally:
        # Standard shutdown procedure
        if simulator_socket:
            print("\nCleaning up and shutting down...")
            send(simulator_socket, "FUNC STANDARD")
            send(simulator_socket, "OUTPut OFF")
            simulator_socket.close()
            print("✅ Simulator set to STANDARD, output OFF, connection closed.")

if __name__ == "__main__":
    main()