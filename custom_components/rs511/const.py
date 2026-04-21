"""Constants for the RSPro RS511 Modbus RTU integration."""

DOMAIN = "rs511"

# Config entry keys
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_SLAVE_ADDRESS = "slave_address"
CONF_MIN_FREQUENCY = "min_frequency"
CONF_MAX_FREQUENCY = "max_frequency"
CONF_POLL_INTERVAL = "poll_interval"

# Defaults
DEFAULT_BAUDRATE = 9600
DEFAULT_SLAVE_ADDRESS = 1
DEFAULT_MIN_FREQUENCY = 0.0
DEFAULT_MAX_FREQUENCY = 50.0
DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_NAME = "RS511 Lüfter"

# -----------------------------------------------------------------------
# RS511 Modbus RTU Register Map
#
# All registers accessed via Function Code 03 (Read Holding Registers)
# and Function Code 06 (Write Single Register).
#
# Communication defaults: 9600 baud, 8N1, slave address 1.
# Frequency values are in units of 0.01 Hz  (e.g. 5000 → 50.00 Hz).
# Current values are in units of 0.01 A.
# Voltage values are in units of 0.1 V.
# -----------------------------------------------------------------------

# --- Control registers (write with FC=06) ---
REG_CONTROL_CMD = 0x2000    # Run / Stop / Reset command
REG_FREQ_SETPOINT = 0x2001  # Frequency setpoint (0.01 Hz units)

# --- Status registers (read with FC=03) ---
REG_STATUS_WORD = 0x3000    # Running status bitmask
REG_OUT_FREQ = 0x3001       # Actual output frequency (0.01 Hz)
REG_OUT_CURRENT = 0x3002    # Output current (0.01 A)
REG_DC_VOLTAGE = 0x3003     # DC bus voltage (0.1 V)
REG_OUT_VOLTAGE = 0x3004    # Output voltage (0.1 V)
REG_MOTOR_SPEED = 0x3005    # Motor speed (RPM)
REG_FAULT_CODE = 0x3006     # Active fault code (0 = no fault)

# --- Control commands (written to REG_CONTROL_CMD) ---
CMD_RUN_FORWARD = 0x0001
CMD_RUN_REVERSE = 0x0002
CMD_STOP = 0x0003
CMD_EMERGENCY_STOP = 0x0005
CMD_RESET_FAULT = 0x0006

# --- Status word bitmask ---
STATUS_BIT_RUNNING = 0x0001   # 1 = running
STATUS_BIT_REVERSE = 0x0002   # 1 = reverse direction
STATUS_BIT_FAULT = 0x0004     # 1 = fault active
STATUS_BIT_READY = 0x0008     # 1 = ready to run

# --- Preset speed modes ---
PRESET_LOW = "Niedrig"
PRESET_MEDIUM = "Mittel"
PRESET_HIGH = "Hoch"

# Preset frequencies in Hz
PRESET_FREQUENCY: dict[str, float] = {
    PRESET_LOW: 20.0,
    PRESET_MEDIUM: 35.0,
    PRESET_HIGH: 50.0,
}

# --- Fault code descriptions ---
FAULT_CODES: dict[int, str] = {
    0: "Kein Fehler",
    1: "Überstrom Beschleunigung",
    2: "Überstrom Verzögerung",
    3: "Überstrom Konstantbetrieb",
    4: "Überspannung Beschleunigung",
    5: "Überspannung Verzögerung",
    6: "Überspannung Konstantbetrieb",
    7: "Zwischenkreis-Überspannung",
    8: "Steuerungsversorgung Fehler",
    9: "Unterspannung",
    10: "Umrichter Überlast",
    11: "Motor Überlast",
    12: "Eingangsphase fehlt",
    13: "Ausgangsphase fehlt",
    14: "Kühlkörper Überhitzung",
    15: "Externe Störung",
    16: "Kommunikationsfehler",
    17: "Kontaktorfehler",
    18: "Stromerfassungsfehler",
    19: "Motor Überhitzung",
    23: "Kurzschluss Fehler",
}
