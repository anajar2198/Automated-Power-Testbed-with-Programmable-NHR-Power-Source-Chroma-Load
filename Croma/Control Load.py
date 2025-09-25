import pyvisa
import time

# ======================================================================
# ⚙️ CONFIGURATION PARAMETERS
# ======================================================================
INSTRUMENT_ADDRESS = "GPIB0::8::INSTR"

# --- Parameters to Set ---
MODE = "ACF"          
ISET_A = 10.0         
IP_MAX_A = 15.0       
CREST_FACTOR = 1.414
POWER_FACTOR = 1.000

# ======================================================================
# 🔌 HELPER FUNCTION
# ======================================================================
def parse_float(value_str):
    """Safely converts a string to a float, returning NaN on error."""
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return float('nan') # Return Not a Number for invalid strings
    
def connect_and_configure_load(address):
    """Initializes and configures the Chroma load with diagnostic steps."""
    print(f"Connecting to instrument at {address}...")
    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(address)
    inst.write_termination = '\n'
    inst.read_termination = '\n'
    inst.timeout = 5000
    
    inst.clear()
    # ADDED: More print statements and a longer delay
    print("Step 1: Resetting instrument...")
    inst.write("*RST")
    time.sleep(2) # CHANGED: Increased delay to 2 seconds
    inst.write("*CLS")
    
    # ADDED: More print statements and a new delay
    print(f"Step 2: Setting MODE to {MODE}...")
    inst.write(f"MODE {MODE}")
    time.sleep(0.5) # ADDED: New delay to allow mode change to complete

    # ADDED: More print statements
    print("Step 3: Setting AC parameters (CF and PF)...")
    inst.write(f"CFACTor {CREST_FACTOR}")
    inst.write(f"PFACtor {POWER_FACTOR}")
    inst.write(f"CURR:PEAK:MAX:AC {IP_MAX_A}")
    
    # ADDED: More print statements
    print("Step 4: Checking for errors after setup...")
    error_string = inst.query("SYSTem:ERRor?").strip()
    if error_string not in ["0", "OK"] and not error_string.startswith("0,"):
        raise Exception(f"Load reported an error during setup: {error_string}")
        
    identity = inst.query("*IDN?").strip()
    print(f"✅ Connected and configured: {identity}")
    return inst

# ======================================================================
# 🚀 MAIN SCRIPT
# ======================================================================

load_instrument = None
try:
    load_instrument = connect_and_configure_load(INSTRUMENT_ADDRESS)

    # ADDED: Delay to allow settings to apply
    print("Allowing settings to apply...")
    time.sleep(0.5) 

    for i in range(int(ISET_A) + 1):

        print("Sending LOAD ON command...")
        load_instrument.write("LOAD ON")
        
        # ADDED: Verification step to confirm the load is ON
        load_status = load_instrument.query("LOAD:STATus?").strip()
        print(f"Verification: Load status is now '{load_status}' (1 means ON)")
        if load_status not in ["1", "OK"]:
            raise Exception("Failed to turn the load on. Please check the instrument.")
        
        # MOVED & ADDED: Set the current only after the load is confirmed to be ON
        print(f"Setting current to {i} A...")
        load_instrument.write(f"CURR {i}")
        load_instrument.write("LOAD ON")

        # ADDED: Verification step to read back the current setpoint
        print("Verifying the current setpoint...")
        readback_current_str = load_instrument.query("CURRent?").strip()
        readback_current = float(readback_current_str)
        print(f"--> Verification successful: Instrument reports setpoint is {readback_current:.2f} A")

        # Optional but recommended: Add a check to ensure it was set correctly
        if abs(readback_current - i) > 0.1: # Check if it's within a 0.1A tolerance
            raise Exception(f"Failed to set current correctly! Expected {ISET_A}, but read back {readback_current}")

        time.sleep(2) # Wait for measurement to stabilize before reading V, I, P

        # ... measurements follow ...
        
        print("Verifying settings by taking live measurements...")
        v_meas_str = load_instrument.query("MEASure:VOLTage?").strip()
        i_meas_str = load_instrument.query("MEASure:CURRent?").strip()
        p_meas_str = load_instrument.query("MEASure:POWer?").strip()

        v_meas = parse_float(v_meas_str)
        i_meas = parse_float(i_meas_str)
        p_meas = parse_float(p_meas_str)
        
        print("\n--- ✅ Live Readings ---")
        print(f"  Voltage : {v_meas:.2f} V")
        print(f"  Current : {i_meas:.2f} A")
        print(f"  Power   : {p_meas:.2f} W")
        print("------------------------")
        time.sleep(5) 

    print("\n--- ✅ Loop Complete ---")
    input("\n--> Press Enter to turn load OFF and exit. ")

except Exception as e:
    print(f"\n❌ An unhandled error occurred: {e}")

finally:
    # --- Safety Cleanup with Full Reset ---
    if load_instrument:
        print("\nCleaning up and closing connection...")
        load_instrument.write("LOAD OFF")
        load_instrument.write("CURRent 0")
        # *** FIX: Reset the instrument to ensure a clean state for the next run ***
        load_instrument.write("*RST")
        time.sleep(1) # Allow time for reset to complete
        load_instrument.close()
        print("✅ Load is OFF, Reset, and connection is closed.")