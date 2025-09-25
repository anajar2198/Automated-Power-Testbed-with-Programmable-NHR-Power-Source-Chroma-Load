import socket
import time

# --- Configuration ---
# Replace with your device's IP address
HOST = "192.168.0.149"
PORT = 5025 # Standard SCPI programming port

def send_command(sock, command):
    """Sends a command to the device."""
    sock.sendall((command + '\n').encode())

def send_query(sock, query_command):
    """Sends a query, receives, and cleans the response."""
    sock.sendall((query_command + '\n').encode())
    response = sock.recv(4096).decode()
    return response.strip().replace('\x00', '')

# --- Main Script ---
try:
    with socket.create_connection((HOST, PORT), timeout=10) as s:
        print(f"✅ Connected to {HOST}:{PORT}")

        # --- SAFETY WARNING ---
        print("\n⚠️ WARNING: This script will control a live power output.")
        print("    Press Ctrl+C now to abort if you are not ready.")
        time.sleep(5)

        # 1. Select the target instrument (AC GRID 3)
        target_instrument = 3
        print(f"\nSelecting AC GRID {target_instrument}...")
        send_command(s, f"INSTrument:NSELect {target_instrument}")

        # 2. Turn the output ON
        print("Turning output ON...")
        send_command(s, "OUTPut ON")
        time.sleep(2) # Wait for the output relay to engage

        # 3. Perform the voltage sweep
        print("\n--- Starting Voltage Sweep ---")
        for voltage_step in range(30, 151, 10):
            # Set the new voltage
            print(f"Setting voltage to {voltage_step} V...")
            send_command(s, f"VOLTage {voltage_step}")
            
            # Wait for the voltage to settle
            time.sleep(5)

            # (Optional) Verify the voltage by measuring it back
            actual_voltage_str = send_query(s, "MEASure:VOLTage?")
            print(f"  -> Actual measured voltage: {float(actual_voltage_str):.3f} V")
        
        print("--- Voltage Sweep Complete ---\n")

        # 4. Ramp down and turn off for safety
        print("Ramping down voltage and turning output OFF.")
        send_command(s, "VOLTage 0")
        time.sleep(1)
        send_command(s, "OUTPut OFF")
        print("✅ Output is now OFF.")


except socket.timeout:
    print(f"\n❌ Error: Connection to {HOST} timed out.")
except ConnectionRefusedError:
    print(f"\n❌ Error: Connection to {HOST} was refused. Check the IP address.")
except Exception as e:
    print(f"\n❌ An unexpected error occurred: {e}")