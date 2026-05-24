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
#
# Confirmed on RS510-2P7-SH1 (found via systematic probe + power-cycle test):
#   0x0700 (P07-00): Run/Stop command register. FC06 read/write.
#                    0 = Stop, 1 = Forward run, 2 = Reverse run (unconfirmed)
#   0x0701 (P07-01): Live frequency command register (0.01 Hz). FC06 read/write.
#                    Values must be in range [P00-13 min .. P00-12 max] or 0.
#                    After power cycle the VFD starts with these stored values.
#   0x0702 (P07-02): Read-back run status (1 = running forward)
#   0x3000+ : Read-only status block. Individual register meaning TBD.
#   0x2000/0x2001/0x2100+ : Do NOT exist on this device (exception 131).
#   0x1000  : Accepts FC06 write=0 only (meaning unclear; likely watchdog/stop).
#
# Prerequisite: set P00-02=2 (run from communication) and
#               P00-05=5 (frequency from communication) via keypad first.
# ---------------------------------------------------------------------------

# --- Run/Stop command register (FC06 read/write) ---
REG_CONTROL_CMD      = 0x0700  # P07-00: 0=stop, 1=forward, 2=reverse

# --- Frequency command register (FC06 read/write, 0.01 Hz units) ---
# CONFIRMED: writing 5000 to P07-03 caused OL1 overload — motor received power.
# P07-01 is a status echo only. P07-03 is the live frequency command register.
REG_FREQ_SETPOINT    = 0x0703  # P07-03: live frequency (0.01 Hz); e.g. 1500 = 15.00 Hz

# Run/Stop command values for REG_CONTROL_CMD (P07-00):
CMD_STOP           = 0x0000  # stop motor
CMD_RUN_FORWARD    = 0x0001  # run forward
CMD_RUN_REVERSE    = 0x0002  # run reverse (unconfirmed; reverse direction)
#   Bit 4:  FWD       1=Forward direction
#   Bit 5:  REV       1=Reverse direction
#   Bit 12: ESTOP     1=Emergency stop
#   Bit 13: RESET     1=Fault reset
CMD_STOP           = 0x0001  # Bit 0
CMD_RUN_FORWARD    = 0x0012  # Bit 1 (RUN) + Bit 4 (FWD)
CMD_RUN_REVERSE    = 0x0022  # Bit 1 (RUN) + Bit 5 (REV)
CMD_JOG_RUN        = 0x0003  # Bit 0 + Bit 1 (JOG)
CMD_RESET_FAULT    = 0x2000  # Bit 13
CMD_EMERGENCY_STOP = 0x1000  # Bit 12

# --- Monitoring registers (read, FC=03, confirmed responding) ---
# 0x3000–0x3020 all respond. 0x3001/0x3003/… hold constant values (31,32,33…)
# that appear to be firmware/model identification, not live monitoring data.
# Live monitoring layout is TBD — read 0x3000 block while running to decode.
# Known: 0x301D=1690, 0x301F=1734 (plausible as voltages ×10: 169 V / 173 V).
# 0x300F=1 and 0x3011=1 mirror P09-00 (slave addr) and a comm setting.
REG_STATUS_WORD      = 0x3000  # 0 when stopped; expected to change when running
REG_SET_FREQ         = 0x3001  # constant 31 when stopped – possibly model code
REG_OUT_FREQ         = 0x3002  # 0 when stopped – candidate output frequency
REG_OUT_CURRENT      = 0x3004  # 0 when stopped – candidate output current
REG_DC_VOLTAGE       = 0x301D  # 1690 idle – candidate DC bus voltage (×10 → 169 V)
REG_OUT_VOLTAGE      = 0x301F  # 1734 idle – candidate output voltage (×10 → 173 V)
REG_HEATSINK_TEMP    = 0x3006  # unverified
REG_TORQUE           = 0x3007  # unverified
REG_MOTOR_SPEED      = 0x3008  # unverified
REG_FAULT_CODE       = 0x300B  # unverified (0 when stopped = no fault, plausible)
# Read 0x3000–0x300C in one request for basic status
REG_MONITOR_START    = 0x3000
REG_MONITOR_COUNT    = 13

# Status word bit definitions (read from REG_STATUS_WORD = 0x2101):
# Exact bit definitions may vary — verify empirically with rs510_test.py.
STATUS_BIT_READY   = 0x0001
STATUS_BIT_RUNNING = 0x0002
STATUS_BIT_REVERSE = 0x0004
STATUS_BIT_FAULT   = 0x0008
STATUS_BIT_ALARM   = 0x0010

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
