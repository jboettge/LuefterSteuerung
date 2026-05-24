"""Constants for the RSPro RS510 Modbus RTU Home Assistant integration.

Register addresses and protocol details based on the L510s manual.
The RS510-2P7-SH1 is an OEM of the TECO L510 (single-phase 230V, 2.7kW).
Communication registers are in Appendix 3 of the L510 manual.
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
# Dedicated Modbus communication registers (L510 manual, Appendix 3)
#
# Prerequisite: set P00-02=2 (run from communication) and
#               P00-05=5 (frequency from communication) via keypad first.
# ---------------------------------------------------------------------------

# --- Run/Stop command register (0x2501, FC06 write) ---
REG_CONTROL_CMD      = 0x2501  # Operation Signal

# --- Frequency command register (0x2502, FC06 write, 0.01 Hz units) ---
REG_FREQ_SETPOINT    = 0x2502  # Frequency Command; e.g. 1500 = 15.00 Hz

# Run/Stop command values for REG_CONTROL_CMD (0x2501):
#   bit 0: Run (1=run, 0=stop)
#   bit 1: Direction (0=forward, 1=reverse)
#   bit 3: Fault Reset
CMD_STOP           = 0x0000  # stop
CMD_RUN_FORWARD    = 0x0001  # bit0=Run, bit1=0 (forward)
CMD_RUN_REVERSE    = 0x0003  # bit0=Run, bit1=1 (reverse)
CMD_RESET_FAULT    = 0x0008  # bit3=Reset (write then write CMD_STOP)
CMD_EMERGENCY_STOP = 0x0000  # same as stop for L510

# --- Monitoring registers (0x2520–0x2532, FC03 read) ---
REG_MONITOR_START    = 0x2520
REG_MONITOR_COUNT    = 19     # 0x2520 through 0x2532 inclusive
# Individual monitoring registers (offset from 0x2520):
REG_STATUS_WORD      = 0x2520  # [0]  status bits
REG_FAULT_CODE       = 0x2521  # [1]  fault code (0 = no fault)
REG_DIO_STATUS       = 0x2522  # [2]  DI/DO status
REG_SET_FREQ         = 0x2523  # [3]  frequency command echo (0.01 Hz)
REG_OUT_FREQ         = 0x2524  # [4]  output frequency (0.01 Hz)
REG_OUT_VOLTAGE      = 0x2525  # [5]  output voltage (0.1 V)
REG_DC_VOLTAGE       = 0x2526  # [6]  DC bus voltage (1 V)
REG_OUT_CURRENT      = 0x2527  # [7]  output current (0.1 A)
REG_OUT_POWER        = 0x2529  # [9]  output power (0.1 kW)
REG_HEATSINK_TEMP    = 0x2531  # [17] heatsink temperature (0.1 °C)
REG_CURRENT_PCT      = 0x2532  # [18] current ratio (%)

# Status word bit definitions (register 0x2520):
STATUS_BIT_RUNNING   = 0x0001  # bit 0: inverter running
STATUS_BIT_REVERSE   = 0x0002  # bit 1: reverse direction
STATUS_BIT_READY     = 0x0004  # bit 2: ready
STATUS_BIT_FAULT     = 0x0008  # bit 3: fault active
STATUS_BIT_DATA_ERR  = 0x0010  # bit 4: communication data error
STATUS_BIT_ALARM     = 0x0010  # alias for DATA_ERR (used as alarm indicator)

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
# RS510/L510 Fault codes (register 0x2521H, from L510 manual section 5.1)
# ---------------------------------------------------------------------------
FAULT_CODES: dict[int, str] = {
    0:  "Kein Fehler",
    1:  "OH    Übertemperatur",
    2:  "OC    Überstrom (gestoppt)",
    3:  "LV    Unterspannung",
    4:  "OV    Überspannung",
    6:  "bb    Externer Basisblock",
    7:  "CtEr  CPU-Fehler",
    8:  "PdEr  PID-Rückmeldung verloren",
    9:  "EPr   EEPROM-Fehler",
    11: "OL3   Drehmomenten-Überlast",
    12: "OL2   Umrichter Überlast",
    13: "OL1   Motor Überlast",
    14: "EFO   Externer Kommunikationsfehler",
    15: "E.S.  Externer Stopp",
    16: "LOC   Parameter gesperrt",
    18: "OC-C  Überstrom Konstantbetrieb",
    19: "OC-A  Überstrom Beschleunigung",
    20: "OC-d  Überstrom Verzögerung",
    21: "OC-S  Überstrom Start",
    23: "LV-C  Unterspannung im Betrieb",
    24: "OV-C  Überspannung Verzögerung",
    25: "OH-C  Übertemperatur im Betrieb",
    33: "Err6  Kommunikationsfehler",
    34: "Err7  Parameterkonflikt",
    40: "OVSP  Motor Überdrehzahl",
    41: "PF    Eingangsphase fehlt",
    44: "OH4   Motor Übertemperatur",
    46: "CL    Strombegrenzung",
}

# ---------------------------------------------------------------------------
# RS485 connector pinout (CON2, 8-pin)
# Pin 1: Data+   Pin 2: Data-
# Pin 3: Data+   Pin 6: Data-
# Pin 7: +5 V    Pin 8: GND
# Pin 4, 5: Reserved
# ---------------------------------------------------------------------------
