import pyvisa
import time
import socket
import msvcrt # Used for non-blocking keyboard checks on Windows

# ======================================================================
# ⚙️ CONFIGURATION PARAMETERS
# ======================================================================
# --- NHR 9400 Grid Simulator (Voltage Source) ---
SIMULATOR_HOST = "192.168.0.149"
SIMULATOR_PORT = 5025
SIMULATOR_INSTRUMENT = 3 

# --- Chroma 63804 Electronic Load (Current Sink) ---
LOAD_ADDRESS = "GPIB0::8::INSTR" 

# --- Sweep & Test Parameters ---
VOLTAGE_START_V = 100
VOLTAGE_STOP_V = 150
VOLTAGE_STEP_V = 25

CURRENT_START_A = 0
CURRENT_STOP_A = 10
CURRENT_STEP_A = 2.5

# Interval to wait at each V-I condition before measuring
INTERVAL_S = 20


def send_query_socket(sock, query):
    """Helper to send a query to a socket and get a clean response."""
    sock.sendall((query + '\n').encode())
    response = sock.recv(4096).decode().strip().replace('\x00', '')
    return response

def print_safety_limits(sock):
    """Query and print all 16 NHR safety values in a nice table."""
    settings_str = send_query_socket(sock, "SOURce:SAFety?")
    settings = settings_str.split(',')

    labels = [
        "Max RMS Voltage (V)",
        "Max Peak Voltage (V)",
        "Min Frequency (Hz)",
        "Max Frequency (Hz)",
        "Max RMS Current (A)",
        "Max Peak Current (A)",
        "Max Voltage Slew Rate (V/us)",
        "Max Current Slew Rate (A/us)",
        "Max Power (W)",
        "Max Apparent Power (VA)",
        "Max Reactive Power (VAR)",
        "Power Factor Limit",
        "Crest Factor Limit",
        "Max Harmonics Order",
        "Peak Current Limit (A)",
        "Reserved"
    ]

    print("\n--- Safety Limits ---")
    if len(settings) == 16:
        for lbl, val in zip(labels, settings):
            try:
                print(f"{lbl:<28}: {float(val):>10.3f}")
            except ValueError:
                print(f"{lbl:<28}: {val.strip():>10}")
    else:
        print(f"⚠️ Unexpected response: {settings_str}")

def connect_grid_simulator(host, port):
    """Connects to and configures the NHR Grid Simulator."""
    print(f"Connecting to Grid Simulator at {host}:{port}...")
    s = socket.create_connection((host, port), timeout=10)
    s.sendall((f'INSTrument:NSELect {SIMULATOR_INSTRUMENT}\n').encode())
    # Set generous protection limits
    s.sendall(b'SOURce:CURRent 20\n') # 20A current limit
    s.sendall(b'SOURce:POWer 2500\n') # 2500W power limit

    print_safety_limits(s)
    
    print("✅ Grid Simulator connected and configured.")
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
    """Safely converts a string to a float, returning NaN on error."""
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return float('nan')
    
    
# ======================================================================
# 🚀 MAIN SCRIPT
# ======================================================================

simulator_socket = None
load_instrument = None

try:
    # --- Connect to both instruments ---
    simulator_socket = connect_grid_simulator(SIMULATOR_HOST, SIMULATOR_PORT)
    load_instrument = connect_electronic_load(LOAD_ADDRESS)

    # --- Prepare for sweep ---
    print("\nPreparing for test. Turning Grid Simulator ON.")
    simulator_socket.sendall(b'OUTPut ON\n')
    time.sleep(2)
    print("--> Press 'q' at any time to stop the sweep and save results. <--")
    print("\n--- Starting Nested V-I Sweep ---")
    print(f"{'V Set (V)':<12} | {'I Set (A)':<12} | {'V Meas (V)':<12} | {'I Meas (A)':<12} | {'P Meas (W)':<12}")
    print("-" * 68)

    # --- Outer Loop: Voltage Sweep ---
    v_range = range(VOLTAGE_START_V, VOLTAGE_STOP_V + 1, VOLTAGE_STEP_V)
    for v_set in v_range:
        simulator_socket.sendall(f'VOLTage {v_set}\n'.encode())
        time.sleep(1.5)

        # --- Inner Loop: Current Sweep ---
        i_set = CURRENT_START_A
        while i_set <= CURRENT_STOP_A:
            if msvcrt.kbhit() and msvcrt.getch().decode().lower() == 'q':
                print("\n🛑 Hard stop requested by user!")
                raise KeyboardInterrupt # Immediately stops the try block
            # This is the specific command sequence required by the Chroma load in AC mode
            load_instrument.write(f"CURRent:PEAK:MAXimum:AC {i_set * 1.5 if i_set > 0 else 0.1}")
            load_instrument.write(f"CURR {i_set}")
            load_instrument.write("LOAD ON")
            time.sleep(1)
            
            # ADDED: Verification step to read back the current setpoint
            # print("Verifying the current setpoint...")
            readback_current_str = load_instrument.query("CURRent?").strip()
            readback_current = float(readback_current_str)
            # print(f"--> Verification successful: Instrument reports setpoint is {readback_current:.2f} A")

            # Optional but recommended: Add a check to ensure it was set correctly
            if abs(readback_current - i_set) > 0.1: # Check if it's within a 0.1A tolerance
                raise Exception(f"Failed to set current correctly! Expected {i_set}, but read back {readback_current}")
            
            time.sleep(2) # Wait for measurement to stabilize before reading V, I, P
        
            # Take measurements from the electronic load
            v_meas = parse_float(load_instrument.query("MEASure:VOLTage?").strip())
            i_meas = parse_float(load_instrument.query("MEASure:CURRent?").strip())
            p_meas = parse_float(load_instrument.query("MEASure:POWer?").strip())
            
            # load_instrument.write("LOAD OFF")
            
            print(f"{v_set:<12.2f} | {i_set:<12.2f} | {v_meas:<12.2f} | {i_meas:<12.2f} | {p_meas:<12.2f}")
            
            i_set += CURRENT_STEP_A

            time.sleep(INTERVAL_S)
        print("-" * 68)

    print("--- Sweep Completed Successfully ---")

except KeyboardInterrupt:
    print("\nUser interrupted the test. Proceeding to save and shut down.")
except Exception as e:
    print(f"\n❌ An error occurred during the test: {e}")

finally:
    # --- Safety Shutdown ---
    print("\nCleaning up and shutting down outputs...")
    if simulator_socket:
        simulator_socket.sendall(b'VOLTage 0\n'); time.sleep(1)
        simulator_socket.sendall(b'OUTPut OFF\n')
        simulator_socket.close()
        print("✅ Grid Simulator output OFF and connection closed.")
        
    if load_instrument:
        load_instrument.write("LOAD OFF"); load_instrument.write("CURRent 0")
        load_instrument.write("*RST"); time.sleep(1)
        load_instrument.close()
        print("✅ Electronic Load OFF, Reset, and connection is closed.")