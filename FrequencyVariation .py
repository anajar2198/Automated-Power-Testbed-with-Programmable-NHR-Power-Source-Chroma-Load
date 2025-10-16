import pyvisa
import time
import socket
import signal
import sys

# ======================================================================
# ⚙️ CONFIGURATION PARAMETERS
# ======================================================================
# --- Instrument Addresses ---
SIMULATOR_HOST = "192.168.0.149"
SIMULATOR_PORT = 5025
SIMULATOR_INSTRUMENT = 3
LOAD_ADDRESS = "GPIB0::8::INSTR"

# --- General Test Settings ---
NOMINAL_VOLTAGE_V = 120.0
NOMINAL_FREQUENCY_HZ = 60.0
TEST_CURRENT_A = 10.0

# --- Test 1: Steady-State Tolerance (Approx. 50 mins) ---
STEADY_STATE_FREQUENCIES_HZ = [59.5, 59.6, 59.7, 59.8, 59.9, 60, 60.1, 60.2, 60.3, 60.4]
STEADY_STATE_DWELL_S = 300  # 5 minutes

# --- Test 2: Comprehensive Dynamic Step Analysis (Approx. 30 mins) ---
# Sequence of (start_freq, end_freq, hold_duration_after_step_s)
DYNAMIC_STEP_SEQUENCE = [
    (60.0, 59.8, 180),  # Small step down
    (59.8, 60.2, 180),  # Small step across nominal
    (60.2, 60.0, 120),  # Return to nominal
    (60.0, 59.5, 240),  # Large step down
    (59.5, 60.5, 240),  # Large step across nominal (1 Hz jump)
    (60.5, 60.0, 180),  # Return to nominal
    (60.0, 59.2, 300),  # Very large step down
    (59.2, 60.0, 180),  # Recover from very large step
    (60.0, 60.8, 300),  # Very large step up
    (60.8, 60.0, 180)   # Recover from very large step
]
DYNAMIC_LOG_DURATION_S = 10    # How long to log transient data after a step
DYNAMIC_LOG_INTERVAL_S = 0.5  # How often to query for data

# --- Test 3: Multi-Rate RoCoF Verification (Approx. 30 mins) ---
# A list of different RoCoF rates to test against
ROCOF_RATES_TO_TEST_HZ_S = [0.1, 0.2, 0.3, 0.4, 0.5,
                            0.6,0.7, 0.8, 0.9, 1.0,
                            1.2, 1.4, 1.6, 1.8, 2.0] # Slow, Medium, Fast
ROCOF_FREQ_HIGH = 63
ROCOF_FREQ_LOW = 57
ROCOF_HOLD_S = 30 # Hold at frequency extremes for 5 minutes

# --- Test 4: Extended Grid Fault Scenario (Approx. 30 mins) ---
# A long, realistic sequence of (Voltage, Frequency, Dwell_Time_s)
COMBINED_FAULT_SEQUENCE = [
    (120.0, 60.0, 120), # Start at nominal
    (112.0, 59.7, 300), # Long, mild brownout and under-frequency
    (108.0, 59.5, 300), # Deeper brownout
    (115.0, 59.8, 180), # Gradual recovery 1
    (120.0, 60.0, 180), # Return to nominal
    (120.0, 60.3, 120), # Over-frequency event
    (125.0, 60.5, 240), # Voltage swell with over-frequency
    (130.0, 60.8, 180), # Major swell event
    (122.0, 60.2, 120), # Gradual recovery 2
    (120.0, 60.0, 120)  # End at nominal
]


# ======================================================================
# 🌐 HELPER & CONNECTION FUNCTIONS
# ======================================================================
STOP_REQUESTED = False

def handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("\n🛑 Hard stop requested (CTRL+C or q).")

signal.signal(signal.SIGINT, handle_stop)
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

def connect_grid_simulator(host, port):
    print(f"Connecting to Grid Simulator at {host}:{port}...")
    s = socket.create_connection((host, port), timeout=10)
    s.sendall((f'INSTrument:NSELect {SIMULATOR_INSTRUMENT}\n').encode())
    s.sendall(b'SOURce:CURRent 20\n')
    s.sendall(b'SOURce:POWer 2500\n')
    print("✅ Grid Simulator connected.")
    return s

def connect_electronic_load(address):
    """Connects to and configures the Chroma Electronic Load for AC CF Mode."""
    print(f"Connecting to Electronic Load at {address}...")
    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(address)
    inst.write_termination = '\n'
    inst.read_termination = '\n'
    inst.timeout = 5000
    
    inst.clear()
    inst.write("*RST"); time.sleep(2); inst.write("*CLS")
    
    print("Configuring Load for AC Crest Factor (CF) Mode...")
    inst.write("MODE ACF") 
    inst.write("CFACTor 1.414")
    inst.write("PFACtor 1.0")   
    
    error_string = inst.query("SYSTem:ERRor?").strip()
    if error_string not in ["0", "OK"] and not error_string.startswith("0,"):
        raise Exception(f"Load reported an error during setup: {error_string}")
        
    identity = inst.query("*IDN?").strip()
    print(f"✅ Electronic Load connected and configured: {identity}")
    return inst

def parse_float(value_str):
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return float('nan')

# ======================================================================
# 🧪 TEST IMPLEMENTATIONS
# ======================================================================

def run_steady_state_test(simulator, load):
    """Runs Test 1: Holds at each frequency for a long duration."""
    print("\n--- Starting Test 1: Steady-State Tolerance ---")
    header = f"{'V Set (V)':<12} | {'I Set (A)':<12} | {'F Set (Hz)':<12} | {'V Meas (V)':<12} | {'I Meas (A)':<12} | {'P Meas (W)':<12}"
    print(header); print("-" * len(header))


    for freq_set in STEADY_STATE_FREQUENCIES_HZ:
        if STOP_REQUESTED: raise KeyboardInterrupt
        # print(f"Setting frequency to {freq_set:.2f} Hz for {STEADY_STATE_DWELL_S}s...")
        simulator.sendall(f'SOURce:FREQuency {freq_set}\n'.encode())
        time.sleep(1)

        v_meas = parse_float(load.query("MEASure:VOLTage?").strip())
        i_meas = parse_float(load.query("MEASure:CURRent?").strip())
        p_meas = parse_float(load.query("MEASure:POWer?").strip())
        print(f"{NOMINAL_VOLTAGE_V:<12.2f} | {TEST_CURRENT_A:<12.2f} | {freq_set:<12.2f} | {v_meas:<12.2f} | {i_meas:<12.2f} | {p_meas:<12.2f}")
        if responsive_sleep(STEADY_STATE_DWELL_S):
            break


def run_dynamic_step_test(simulator, load):
    print(f"\n--- Starting Test 2: Comprehensive Dynamic Step Analysis (approx. 30 mins) ---")
    for i, (start_freq, end_freq, hold_s) in enumerate(DYNAMIC_STEP_SEQUENCE):
        if STOP_REQUESTED: break
        print(f"\n--- Step {i+1}/{len(DYNAMIC_STEP_SEQUENCE)}: {start_freq:.2f} Hz -> {end_freq:.2f} Hz ---")
        
        print(f"Setting pre-step frequency to {start_freq:.2f} Hz...")
        simulator.sendall(f'SOURce:FREQuency {start_freq}\n'.encode())
        responsive_sleep(5) # Stabilize

        print(f"Executing step to {end_freq:.2f} Hz. Logging transient...")
        simulator.sendall(f'SOURce:FREQuency {end_freq}\n'.encode())
        
        start_time = time.time()
        while time.time() - start_time < DYNAMIC_LOG_DURATION_S:
            if STOP_REQUESTED: break
            v_meas = parse_float(load.query("MEASure:VOLTage?").strip())
            i_meas = parse_float(load.query("MEASure:CURRent?").strip())
            p_meas = parse_float(load.query("MEASure:POWer?").strip())
            elapsed = time.time() - start_time
            print(f"  T+{elapsed:.1f}s -> V:{v_meas:.2f}, I:{i_meas:.2f}, P:{p_meas:.1f}")
            time.sleep(DYNAMIC_LOG_INTERVAL_S)

        if STOP_REQUESTED: break
        print(f"Transient logging complete. Holding for {hold_s}s...")
        if responsive_sleep(hold_s): break

def run_rocof_ramp_test(simulator, load):
    print(f"\n--- Starting Test 3: Multi-Rate RoCoF Verification (approx. 30 mins) ---")
    simulator.sendall(f'SOURce:FREQuency {ROCOF_FREQ_HIGH}\n'.encode()) # return to nominal V

    for rate in ROCOF_RATES_TO_TEST_HZ_S:
        if STOP_REQUESTED: break
        print(f"\n--- Testing RoCoF Rate: {rate:.2f} Hz/s ---")
        simulator.sendall(f'SOURce:FREQuency:SLEW {rate}\n'.encode())
        simulator.sendall(b'SOURce:FREQuency:SLEW:STATe ON\n')
        
        ramp_duration_s = abs(ROCOF_FREQ_HIGH - ROCOF_FREQ_LOW) / rate

        # Ramp Down
        print(f"Ramping Down from {ROCOF_FREQ_HIGH} to {ROCOF_FREQ_LOW} Hz...")
        simulator.sendall(f'SOURce:FREQuency {ROCOF_FREQ_HIGH}\n'.encode()); responsive_sleep(5)
        simulator.sendall(f'SOURce:FREQuency {ROCOF_FREQ_LOW}\n'.encode())
        if responsive_sleep(ramp_duration_s): break
        print(f"Ramp complete. Holding at {ROCOF_FREQ_LOW} Hz for {ROCOF_HOLD_S}s...")
        if responsive_sleep(ROCOF_HOLD_S): break
       
        # Ramp Up
        print(f"Ramping Up from {ROCOF_FREQ_LOW} to {ROCOF_FREQ_HIGH} Hz...")
        simulator.sendall(f'SOURce:FREQuency {ROCOF_FREQ_HIGH}\n'.encode())
        if responsive_sleep(ramp_duration_s): break
        print(f"Ramp complete. Holding at {ROCOF_FREQ_HIGH} Hz for {ROCOF_HOLD_S}s...")
        if responsive_sleep(ROCOF_HOLD_S): break

    simulator.sendall(b'SOURce:FREQuency:SLEW:STATe OFF\n')


def run_combined_disturbance_test(simulator, load):
    print(f"\n--- Starting Test 4: Extended Grid Fault Scenario (approx. 30 mins) ---")
    header = f"{'Step':<5} | {'V Set (V)':<12} | {'F Set (Hz)':<12} | {'Dwell (s)':<10} | {'V Meas (V)':<12} | {'I Meas (A)':<12} | {'P Meas (W)':<12}"
    print(header); print("-" * len(header))

    for i, (v_set, freq_set, dwell_s) in enumerate(COMBINED_FAULT_SEQUENCE):
        if STOP_REQUESTED: break
        
        simulator.sendall(f'SOURce:VOLTage {v_set}\n'.encode())
        simulator.sendall(f'SOURce:FREQuency {freq_set}\n'.encode())
        
        if responsive_sleep(dwell_s): break

        v_meas = parse_float(load.query("MEASure:VOLTage?").strip())
        i_meas = parse_float(load.query("MEASure:CURRent?").strip())
        p_meas = parse_float(load.query("MEASure:POWer?").strip())
        print(f"{i+1:<5} | {v_set:<12.2f} | {freq_set:<12.2f} | {dwell_s:<10} | {v_meas:<12.2f} | {i_meas:<12.2f} | {p_meas:<12.2f}")


# ======================================================================
# 🚀 MAIN SCRIPT EXECUTION
# ======================================================================

def main():
    """Main function to display menu and run selected test."""
    
    print("==========================================")
    print("  Universal Frequency Test Controller")
    print("==========================================")
    print("Select a test to run:")
    print("  1. Steady-State Tolerance Test")
    print("  2. Dynamic Step-Response Test")
    print("  3. RoCoF Ramp Test")
    print("  4. Combined Disturbance Test")
    choice = input("Enter your choice (1-4): ")

    test_functions = {
        "1": run_steady_state_test,
        "2": run_dynamic_step_test,
        "3": run_rocof_ramp_test,
        "4": run_combined_disturbance_test
    }

    if choice not in test_functions:
        print("Invalid choice. Exiting.")
        sys.exit(1)

    selected_test = test_functions[choice]
    simulator_socket = None
    load_instrument = None

    try:
        # --- Connect to instruments ---
        simulator_socket = connect_grid_simulator(SIMULATOR_HOST, SIMULATOR_PORT)
        load_instrument = connect_electronic_load(LOAD_ADDRESS)

        # --- Prepare for the test ---
        print("\nPreparing for test...")
        simulator_socket.sendall(f'SOURce:VOLTage {NOMINAL_VOLTAGE_V}\n'.encode())
        simulator_socket.sendall(f'SOURce:FREQuency {NOMINAL_FREQUENCY_HZ}\n'.encode())
        simulator_socket.sendall(b'OUTPut ON\n')
        print(f"Grid Simulator ON: {NOMINAL_VOLTAGE_V} V, {NOMINAL_FREQUENCY_HZ} Hz.")
        print(f"wait 10 sec for stabilization of Grid Simulator.")
        # Allow stabilization but check for stop
        for _ in range(10):
            if STOP_REQUESTED:
                raise KeyboardInterrupt
            time.sleep(1)
        load_instrument.write(f"CURRent:PEAK:MAXimum:AC {TEST_CURRENT_A * 1.5 if TEST_CURRENT_A > 0 else 0.1}")
        load_instrument.write(f"CURRent {TEST_CURRENT_A}")
        load_instrument.write("LOAD ON")
        print(f"Electronic Load ON: {TEST_CURRENT_A} A.")
        
        print("Stabilizing for 20 seconds...")
        if responsive_sleep(20):
            raise KeyboardInterrupt
        print("\n--> Press 'CTRL + C' at any time to stop the test gracefully. <--")

        # --- Run the selected test ---
        selected_test(simulator_socket, load_instrument)
        
        if not STOP_REQUESTED:
            print("\n--- Test Completed Successfully ---")

    except KeyboardInterrupt:
        print("\nTest interrupted by user. Proceeding to shutdown.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
    finally:
        # --- Safety Shutdown ---
        print("\nCleaning up and shutting down outputs...")
        if simulator_socket:
            simulator_socket.sendall(b'SOURce:FREQuency:SLEW:STATe OFF\n') # Ensure slew is off
            simulator_socket.sendall(f'SOURce:VOLTage {NOMINAL_VOLTAGE_V}\n'.encode()) # return to nominal V
            simulator_socket.sendall(b'OUTPut OFF\n')
            simulator_socket.close()
            print("✅ Grid Simulator output OFF and connection closed.")
            
        if load_instrument:
            load_instrument.write("LOAD OFF")
            load_instrument.write("*RST"); time.sleep(1)
            load_instrument.close()
            print("✅ Electronic Load OFF, Reset, and connection closed.")

if __name__ == "__main__":
    main()