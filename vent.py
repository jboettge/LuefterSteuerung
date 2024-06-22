import json
import sqlite3
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
import math
special_mode = False

ventilator_api_set_url = "http://192.168.243.60:8008/api/data/ventilation_task/GAIN:k?"
ventilator_api_get_url = "http://192.168.243.60:8008/api/data/ventilation_task/GAIN:y?data&mime=application/json"
keller_api_url = "http://192.168.243.61:8083/ZAutomation/api/v1/devices/ZWayVDev_zway_26-0-49-1"
aussen_api_url = "http://192.168.243.61:8083/ZAutomation/api/v1/devices/ZWayVDev_zway_5-0-49-1"
username = "admin"
password_temp = "4482HgRd3"
password_vent = "5582KxVF"


def get_temperature():
    response_keller = requests.get(keller_api_url, auth=HTTPBasicAuth(username, password_temp))
    response_aussen = requests.get(aussen_api_url, auth=HTTPBasicAuth(username, password_temp))
    return response_keller.json()['data']['metrics']['level'], response_aussen.json()['data']['metrics']['level']


def set_vent(v_vent):
    json_data = {'v': v_vent}
    json_post = json.dumps(json_data)
    headers = {'Content-Type': 'application/json'}
    response = requests.post(ventilator_api_set_url, auth=HTTPBasicAuth(username, password_vent), headers=headers,
                             data=json_post)
    return response.status_code == 200


def get_vent():
    response = requests.get(ventilator_api_get_url, auth=HTTPBasicAuth(username, password_vent))
    v_out = json.loads(response.text)
    return v_out['v']


def calculate_optimal_voltage(t_aussen, t_keller):
    global special_mode
    if special_mode:
        return 0.2

    if t_aussen < 12:
        v_vent = 0.2
    elif 12 <= t_aussen <= 20:
        # Define the temperature and v_vent ranges for the linear mapping
        temperature_range = [12, 20]  # 12 to 20 degrees
        v_vent_range = [0.5, 0.1]  # 0.5 to 0 for v_vent

        # Calculate v_vent using a linear mapping
        v_vent = ((t_aussen - temperature_range[0]) / (temperature_range[1] - temperature_range[0])) * (
                    v_vent_range[1] - v_vent_range[0]) + v_vent_range[0]
    else:
        v_vent = 0.2

    # If the current temperature is higher than the target temperature, increase the ventilation
    if t_keller > t_aussen:
        v_vent += 0.1

    # Ensure v_vent stays within the range 0.0 to 1.0
    v_vent = max(0.1, min(v_vent, 1.0))

    return v_vent



# def calculate_optimal_voltage(t_aussen, t_keller):
#     global special_mode
#     if special_mode:
#         return 0.1
#
#     a = 0.1  # Define your constant a
#     b = 0.02  # Define your constant b
#
#     if t_aussen < 12:
#         v_vent = 0.1
#     elif 12 <= t_aussen <= 20:
#         # Calculate v_vent using an exponential mapping
#         v_vent = a * math.exp(b * t_aussen)
#     else:
#         v_vent = 0.1
#
#     # If the current temperature is higher than the target temperature, increase the ventilation
#     if t_keller > t_aussen:
#         v_vent += 0.1
#     # If the current temperature is lower than the target temperature, reduce the ventilation
#     elif t_keller < t_aussen:
#         v_vent = 0.1
#
#     # Ensure v_vent stays within the range 0.1 to 1.0
#     v_vent = max(0.1, min(v_vent, 1.0))
#
#     return v_vent

# Connect to SQLite database
conn = sqlite3.connect('temperature_data.db')
c = conn.cursor()

# Create table
c.execute('''
    CREATE TABLE IF NOT EXISTS Temperature (
        id INTEGER PRIMARY KEY,
        date TEXT NOT NULL,
        t_keller REAL NOT NULL,
        t_aussen REAL NOT NULL
    )
''')


# Function to insert temperature data
def insert_temperature(t_keller, t_aussen):
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO Temperature (date, t_keller, t_aussen) VALUES (?, ?, ?)", (date, t_keller, t_aussen))
    conn.commit()


# Function to retrieve the last 365 days of temperature data
def get_last_year_temperatures():
    c.execute("SELECT * FROM Temperature ORDER BY date DESC LIMIT 365")
    return c.fetchall()


# Don't forget to close the connection when you're done
# conn.close()

t_keller, t_aussen = get_temperature()
v_vent = get_vent()
v_vent = calculate_optimal_voltage(t_aussen, t_keller)
insert_temperature(t_keller, t_aussen)
conn.close()
set_vent(v_vent)
print("Kellertemperatur [°C]:", t_keller)
print("Aussentemperatur [°C]:", t_aussen)
print("Delta [°C]:", t_keller - t_aussen)
print("Ventilator [%]:", v_vent)
exit(0)
