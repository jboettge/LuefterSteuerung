"""Constants for the RSPro RS510 Modbus RTU Home Assistant integration.

Register addresses and protocol details based on the RS510 user manual
(A700000006570784) and Modbus register map (A700000010414499).
The RS510 shares its platform with the Delta VFD-EL series.
"""

DOMAIN = "rs510"

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_SLAVE_ADDRESS = "slave_address"
CONF_MIN_FREQUENCY = "min_frequency"
CONF_MAX_FREQUENCY = "max_frequency"
CONF_POLL_INTERVAL = "poll_interval"

# ---------------------------------------------------------------------------
# RS510-2P7-SH1 Communication defaults (from manual Group 09)
#   P09-00 = 1   →  Slave address 1
#   P09-01 = 0   →  Modbus RTU
#   P09-02 = 2   →  19200 baud  (NOT 9600!)
#   P09-03 = 0   →  1 Stop bit
#   P09-04 = 0   →  No parity
#   P09-05 = 0   →  8-bit data
# ---------------------------------------------------------------------------
DEFAULT_BAUDRATE = 19200
DEFAULT_SLAVE_ADDRESS = 1
DEFAULT_MIN_FREQUENCY = 0.0
DEFAULT_MAX_FREQUENCY = 50.0   # P00-12 default
DEFAULT_POLL_INTERVAL = 30     # seconds
DEFAULT_NAME = "RS510 Lüfter"

# ---------------------------------------------------------------------------
# Parameter register mapping
#
# Each parameter P(GG)-(nn) maps to holding register address 0xGGnnH.
#   GG = group number in hex, nn = parameter number in hex.
#   Example: P08-03 → 0x0803H, P10-11 → 0x0A0BH
#
# Read with FC=03 (Read Holding Registers).
# Write with FC=06 (Write Single Holding Register).
# ---------------------------------------------------------------------------

# Key parameters (address = group*0x100 + param_hex)
PARAM_CONTROL_MODE     = 0x0000  # P00-00  V/F=0, SLV=1
PARAM_MOTOR_DIRECTION  = 0x0001  # P00-01  0=FWD, 1=REV
PARAM_RUN_SOURCE       = 0x0002  # P00-02  0=Keypad, 1=Terminal, 2=Communication
PARAM_ALT_RUN_SOURCE   = 0x0003  # P00-03
PARAM_FREQ_SOURCE      = 0x0005  # P00-05  0=Keypad, ..., 5=Communication
PARAM_ALT_FREQ_SOURCE  = 0x0006  # P00-06
PARAM_COMM_FREQ_CMD    = 0x0008  # P00-08  Communication frequency (0.01 Hz)
PARAM_FREQ_UPPER_LIMIT = 0x000C  # P00-12  Max frequency (0.01 Hz)
PARAM_FREQ_LOWER_LIMIT = 0x000D  # P00-13  Min frequency (0.01 Hz)
PARAM_ACCEL_TIME_1     = 0x000E  # P00-14  Acceleration time 1 (0.1 s)
PARAM_DECEL_TIME_1     = 0x000F  # P00-15  Deceleration time 1 (0.1 s)

# Communication parameters (Group 09)
PARAM_STATION_NUMBER   = 0x0900  # P09-00  Slave address (1-32)
PARAM_COMM_MODE        = 0x0901  # P09-01  0=RTU, 1=ASCII, 2=BACnet
PARAM_BAUD_RATE        = 0x0902  # P09-02  0=4800, 1=9600, 2=19200, 3=38400
PARAM_STOP_BIT         = 0x0903  # P09-03  0=1bit, 1=2bits
PARAM_PARITY           = 0x0904  # P09-04  0=None, 1=Even, 2=Odd
PARAM_DATA_FORMAT      = 0x0905  # P09-05  0=8bit, 1=7bit
PARAM_COMM_TIMEOUT     = 0x0906  # P09-06  Timeout (0.1 s, 0.0-25.5)
PARAM_TIMEOUT_ACTION   = 0x0907  # P09-07  0=Decel stop, 1=Coast, 2=Decel2, 3=Continue

# ---------------------------------------------------------------------------
# Dedicated Modbus control & monitoring registers
# (Delta VFD platform — outside the parameter address space)
#
# Prerequisite: set P00-02=2 (run from communication) and
#               P00-05=5 (frequency from communication) via keypad first.
# ---------------------------------------------------------------------------

# --- Control command register (write, FC=06) ---
REG_CONTROL_CMD      = 0x2000

# Control word bit definitions (written to REG_CONTROL_CMD):
#   Bit 0:  RUN       1=Run, 0=Stop
#   Bit 1:  DIRECTION  1=Reverse, 0=Forward
#   Bit 2:  JOG FWD   1=Jog forward
#   Bit 3:  JOG REV   1=Jog reverse
#   Bit 4:  RESET     1=Fault reset (self-clearing)
#   Bits 5-15: Reserved (write 0)
CMD_STOP          = 0x0000  # All bits 0 → stop
CMD_RUN_FORWARD   = 0x0001  # Bit 0=1
CMD_RUN_REVERSE   = 0x0003  # Bit 0=1, Bit 1=1
CMD_JOG_FORWARD   = 0x0005  # Bit 0=1, Bit 2=1
CMD_JOG_REVERSE   = 0x000B  # Bit 0=1, Bit 1=1, Bit 3=1
CMD_RESET_FAULT   = 0x0010  # Bit 4=1
CMD_EMERGENCY_STOP = 0x0080  # Bit 7=1

# --- Frequency setpoint register (write, FC=06) ---
REG_FREQ_SETPOINT    = 0x2001  # 0.01 Hz units  (e.g. 5000 = 50.00 Hz)

# --- Monitoring registers (read, FC=03) ---
REG_STATUS_WORD      = 0x2100  # Status word
REG_SET_FREQ         = 0x2101  # Set frequency         (0.01 Hz)
REG_OUT_FREQ         = 0x2102  # Actual output freq    (0.01 Hz)
REG_OUT_CURRENT      = 0x2103  # Output current        (0.01 A)
REG_DC_VOLTAGE       = 0x2104  # DC bus voltage        (0.1 V)
REG_OUT_VOLTAGE      = 0x2105  # Output voltage        (0.1 V)
REG_MOTOR_SPEED      = 0x2106  # Motor speed           (RPM)
REG_HEATSINK_TEMP    = 0x2107  # Heatsink temperature  (1 °C)
# Number of consecutive monitoring registers to read in one request
REG_MONITOR_COUNT    = 8

# Status word bit definitions (read from REG_STATUS_WORD):
#   Bit 0:  READY     1=Drive ready
#   Bit 1:  RUNNING   1=Motor running
#   Bit 2:  REVERSE   1=Reverse direction
#   Bit 3:  FAULT     1=Fault active
#   Bit 4:  ALARM     1=Warning/Alarm
STATUS_BIT_READY   = 0x0001
STATUS_BIT_RUNNING = 0x0002
STATUS_BIT_REVERSE = 0x0004
STATUS_BIT_FAULT   = 0x0008
STATUS_BIT_ALARM   = 0x0010

# --- Fault code register ---
REG_FAULT_CODE       = 0x2108  # Current fault code (if present)

# ---------------------------------------------------------------------------
# Preset speed modes
# ---------------------------------------------------------------------------
PRESET_LOW = "Niedrig"
PRESET_MEDIUM = "Mittel"
PRESET_HIGH = "Hoch"

PRESET_FREQUENCY: dict[str, float] = {
    PRESET_LOW: 15.0,     # 15 Hz
    PRESET_MEDIUM: 30.0,  # 30 Hz
    PRESET_HIGH: 50.0,    # 50 Hz (rated)
}

# ---------------------------------------------------------------------------
# RS510 Fault codes (from manual section 5.1)
# ---------------------------------------------------------------------------
FAULT_CODES: dict[int, str] = {
    0:  "Kein Fehler",
    1:  "OC-A  Überstrom bei Beschleunigung",
    2:  "OC-C  Überstrom bei Konstantbetrieb",
    3:  "OC-d  Überstrom bei Verzögerung",
    4:  "OC-S  Überstrom bei Start",
    5:  "OV-C  Überspannung Betrieb/Verzögerung",
    6:  "OH    Kühlkörper Übertemperatur",
    7:  "OL1   Motor Überlast",
    8:  "OL2   Umrichter Überlast",
    9:  "OC    Überstrom bei Stopp",
    10: "CL    Umrichter Strombegrenzung",
    11: "PF    Eingangsphase fehlt",
    12: "LV-C  Unterspannung Betrieb",
    13: "OVSP  Motor Überdrehzahl",
    14: "OH4   Motor Übertemperatur",
    15: "CtEr  Stromerfassungsfehler",
    16: "HPErr Hardwareschutz Fehler",
}

# ---------------------------------------------------------------------------
# RS485 connector pinout (CON2, 8-pin)
# Pin 1: Data+   Pin 2: Data-
# Pin 3: Data+   Pin 6: Data-
# Pin 7: +5 V    Pin 8: GND
# Pin 4, 5: Reserved
# ---------------------------------------------------------------------------
