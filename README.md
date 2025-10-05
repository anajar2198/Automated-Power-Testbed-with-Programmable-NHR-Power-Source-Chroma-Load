# Automated Power Testbed with Programmable NHR Power Source & Chroma Load

This repository contains Python scripts for automating a power electronics testbed consisting of an NHR 9400 series Grid Simulator and a Chroma 63800 series Electronic Load.

The primary script (`Control_Both.py`) performs a nested voltage and current sweep, logs the data, and provides safety features for robust, unattended testing.

## Table of Contents
1.  [Hardware Requirements](#hardware-requirements)
2.  [Software & Setup](#software--setup)
3.  [Script Descriptions](#script-descriptions)
4.  [How to Use the Main Script](#how-to-use-the-main-script)
5.  [Key SCPI Commands Discovered](#key-scpi-commands-discovered)

---

## Hardware Requirements

This test suite is designed for the following specific hardware configuration:

1.  **Power Source:** **NHR 9400 Series Regenerative Grid Simulator**
    * **Connection:** TCP/IP (Ethernet)
    * The script is configured to use `Instrument 3` in a three-channel AC mode.

2.  **Electronic Load:** **Chroma 63800 Series Programmable AC/DC Load** (e.g., 63804)
    * **Connection:** GPIB
    * The script assumes a standard GPIB setup (e.g., `GPIB0::8::INSTR`).

You must have the appropriate GPIB interface (like a National Instruments GPIB-USB adapter) connected to your computer and the Chroma load. Both instruments should be on the same network or directly connected as required.

---

## Software & Setup

1.  **Python Environment:**
    * It is recommended to use a virtual environment. The scripts were developed using `miniconda`.
    * Install the required Python library, `pyvisa`, for GPIB communication:
        ```bash
        pip install pyvisa pyvisa-py
        ```

2.  **VISA Backend:**
    * You must have a VISA backend installed on your system for `pyvisa` to communicate with the GPIB hardware.
    * A common choice is [NI-VISA](https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html) from National Instruments.

3.  **Configuration:**
    * Before running, open the scripts and update the configuration parameters at the top of each file to match your setup:
        * `SIMULATOR_HOST`: The IP address of your NHR Grid Simulator.
        * `LOAD_ADDRESS`: The GPIB address of your Chroma Electronic Load.
        * Sweep parameters (`VOLTAGE_START_V`, `CURRENT_STOP_A`, etc.).

---

## Script Descriptions

### `Control_Both.py`
This is the main, fully integrated script for running a complete test sequence.
* **Functionality:**
    * Connects to both the NHR Grid Simulator and the Chroma Electronic Load.
    * Configures the Grid Simulator with appropriate safety and protection limits.
    * Configures the Chroma Load for **AC Crest Factor (ACF) Mode**, which was found to be critical for stable operation.
    * Performs a nested sweep: for each voltage step, it sweeps through a range of current steps.
    * Provides a **"hard stop"** feature: you can press **'q'** at any time to immediately halt the test.
    * **Automatically saves** all collected data to a `sweep_results.csv` file upon completion, error, or user interruption.
    * Includes robust `try...except...finally` blocks to ensure instruments are safely shut down in all scenarios.

### `NHR_control_test.py`
A utility script for controlling only the NHR Grid Simulator.
* **Functionality:**
    * Connects to the simulator.
    * Performs a simple voltage sweep.
    * Verifies the voltage at each step.
    * Safely ramps down and turns off the output.

### `Control Load.py`
A utility script for controlling only the Chroma Electronic Load.
* **Functionality:**
    * Connects to the load.
    * Configures it for ACF mode.
    * Performs a simple current sweep.
    * Includes robust safety and cleanup procedures.

---

## How to Use the Main Script (`Control_Both.py`)

1.  **Verify Hardware Connections:** Ensure the NHR simulator is connected via Ethernet and the Chroma load is connected via GPIB. Ensure the output of the simulator is wired to the input of the load.
2.  **Configure Parameters:** Open `Control_Both.py` and set the correct `SIMULATOR_HOST`, `LOAD_ADDRESS`, and desired sweep ranges.
3.  **Run the Script:** Execute the script from your terminal:
    ```bash
    python Control_Both.py
    ```
4.  **Monitor the Test:** The script will print the status of each step to the console.
5.  **Stop the Test (Optional):** Press the **`q`** key at any point during the sweep to stop the test immediately.
6.  **Collect Results:** After the test finishes (or is stopped), a file named `sweep_results.csv` will be created in the same directory with all the measurement data.

---

## Key SCPI Commands Discovered

This project involved significant debugging to find the correct, stable command sequences. The key findings for the **Chroma 63800 AC Load in AC Mode** are:

* **Mode Setting:** The command `MODE ACF` is required to put the load into a stable AC Crest Factor mode. Using the simpler `FUNCtion CURRent` caused instability.
* **Turn-On Sequence:** The load requires a specific sequence to begin drawing current reliably:
    1.  Configure `MODE`, `CFACTor`, `PFACtor`, and the RMS current (`CURRent`).
    2.  Send the `LOAD ON` command. This enables the input to sense the source voltage.
    3.  Send the `CURRent:PEAK:MAXimum:AC` command. This sets the peak current limit and acts as the final trigger for the load to start sinking power.