# MIT License
#
# Copyright (c) 2018 Airthings AS
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# https://airthings.com

# ===============================
# Module import dependencies
# ===============================

import struct
import sys
import time
from enum import IntEnum

import tableprint
from bluepy.btle import DefaultDelegate, Peripheral, Scanner, UUID

# ===============================
# Script guards for correct usage
# ===============================

if len(sys.argv) < 3:
    print("ERROR: Missing input argument SN or SAMPLE-PERIOD.")
    print("USAGE: read_waveplus.py SN SAMPLE-PERIOD [pipe > yourfile.txt]")
    print("    where SN is the 10-digit serial number found under the magnetic backplate of your Wave Plus.")
    print("    where SAMPLE-PERIOD is the time in seconds between reading the current values.")
    print("    where [pipe > yourfile.txt] is optional and specifies that you want to pipe your results to yourfile.txt.")

    sys.exit(1)

if sys.argv[1].isdigit() is not True or len(sys.argv[1]) != 10:
    print("ERROR: Invalid SN format.")
    print("USAGE: read_waveplus.py SN SAMPLE-PERIOD [pipe > yourfile.txt]")
    print("    where SN is the 10-digit serial number found under the magnetic backplate of your Wave Plus.")
    print("    where SAMPLE-PERIOD is the time in seconds between reading the current values.")
    print("    where [pipe > yourfile.txt] is optional and specifies that you want to pipe your results to yourfile.txt.")

    sys.exit(1)

if sys.argv[2].isdigit() is not True or int(sys.argv[2]) < 0:
    print("ERROR: Invalid SAMPLE-PERIOD. Must be a numerical value larger than zero.")
    print("USAGE: read_waveplus.py SN SAMPLE-PERIOD [pipe > yourfile.txt]")
    print("    where SN is the 10-digit serial number found under the magnetic backplate of your Wave Plus.")
    print("    where SAMPLE-PERIOD is the time in seconds between reading the current values.")
    print("    where [pipe > yourfile.txt] is optional and specifies that you want to pipe your results to yourfile.txt.")

    sys.exit(1)

if len(sys.argv) > 3:
    MODE = sys.argv[3].lower()
else:
    MODE = 'terminal'  # (default) print to terminal

if MODE != 'pipe' and MODE != 'terminal':
    print("ERROR: Invalid piping method.")
    print("USAGE: read_waveplus.py SN SAMPLE-PERIOD [pipe > yourfile.txt]")
    print("    where SN is the 10-digit serial number found under the magnetic backplate of your Wave Plus.")
    print("    where SAMPLE-PERIOD is the time in seconds between reading the current values.")
    print("    where [pipe > yourfile.txt] is optional and specifies that you want to pipe your results to yourfile.txt.")

    sys.exit(1)

SERIAL_NUMBER = int(sys.argv[1])
SAMPLE_PERIOD = int(sys.argv[2])


# ====================================
# Utility functions for WavePlus class
# ====================================

def parse_serial_number(manu_data_hex_str):
    if manu_data_hex_str is None or manu_data_hex_str == 'None':
        return 'Unknown'

    manu_data = bytearray.fromhex(manu_data_hex_str)
    if not (((manu_data[1] << 8) | manu_data[0]) == 0x0334):
        return 'Unknown'

    SN = manu_data[2]
    SN |= (manu_data[3] << 8)
    SN |= (manu_data[4] << 16)
    SN |= (manu_data[5] << 24)

    return SN


# ===============================
# Class WavePlus
# ===============================

class WavePlus:
    def __init__(self, serial_number):
        self.peripheral = None
        self.curr_val_char = None
        self.mac_address = None
        self.serial_number = serial_number
        self.uuid = UUID('b42e2a68-ade7-11e4-89d3-123b93f75cba')

    def connect(self):
        # Auto-discover device on first connection
        if self.mac_address is None:
            scanner = Scanner().withDelegate(DefaultDelegate())
            searchCount = 0

            while self.mac_address is None and searchCount < 50:
                devices = scanner.scan(0.1)  # 0.1 seconds scan period
                searchCount += 1

                for dev in devices:
                    manu_data = dev.getValueText(255)
                    serial_number = parse_serial_number(manu_data)

                    if serial_number == self.serial_number:
                        self.mac_address = dev.addr  # exits the while loop on next conditional check
                        break  # exit for loop

            if self.mac_address is None:
                print("ERROR: Could not find device.")
                print("GUIDE: (1) Please verify the serial number.")
                print("       (2) Ensure that the device is advertising.")
                print("       (3) Retry connection.")

                sys.exit(1)

        # Connect to device
        if self.peripheral is None:
            self.peripheral = Peripheral(self.mac_address)

        if self.curr_val_char is None:
            self.curr_val_char = self.peripheral.getCharacteristics(uuid=self.uuid)[0]

    def read(self):
        if self.curr_val_char is None:
            print('ERROR: Devices are not connected.')
            sys.exit(1)

        rawdata = self.curr_val_char.read()
        rawdata = struct.unpack('<BBBBHHHHHHHH', rawdata)

        sensors = Sensors()
        sensors.set(rawdata)

        return sensors

    def disconnect(self):
        if self.peripheral is None:
            return

        self.peripheral.disconnect()
        self.peripheral = None
        self.curr_val_char = None


# ===================================
# Class Sensor and sensor definitions
# ===================================

class SensorIndex(IntEnum):
    HUMIDITY = 0
    RADON_SHORT_TERM_AVG = 1
    RADON_LONG_TERM_AVG = 2
    TEMPERATURE = 3
    REL_ATM_PRESSURE = 4
    CO2_LVL = 5
    VOC_LVL = 6


SENSOR_UNITS = [
    '%rH',
    'Bq/m3',
    'Bq/m3',
    '°C',
    'hPa',
    'ppm',
    'ppb',
]

SENSOR_HEADERS = [
    'Humidity',
    'Radon ST avg',
    'Radon LT avg',
    'Temperature',
    'Pressure',
    'CO2 level',
    'VOC level',
]


class Sensors:
    def __init__(self):
        self.sensor_version = None
        self.sensor_data = [None] * len(SENSOR_UNITS)

    def set(self, rawData):
        self.sensor_version = rawData[0]
        if self.sensor_version == 1:
            self.sensor_data[SensorIndex.HUMIDITY] = rawData[1] / 2.0
            self.sensor_data[SensorIndex.RADON_SHORT_TERM_AVG] = self.conv2radon(rawData[4])
            self.sensor_data[SensorIndex.RADON_LONG_TERM_AVG] = self.conv2radon(rawData[5])
            self.sensor_data[SensorIndex.TEMPERATURE] = rawData[6] / 100.0
            self.sensor_data[SensorIndex.REL_ATM_PRESSURE] = rawData[7] / 50.0
            self.sensor_data[SensorIndex.CO2_LVL] = rawData[8]
            self.sensor_data[SensorIndex.VOC_LVL] = rawData[9]
        else:
            print('ERROR: Unknown sensor version.\n')
            print('GUIDE: Contact Airthings for support.\n')
            sys.exit(1)

    def conv2radon(self, radon_raw):
        if 0 <= radon_raw <= 16383:
            return radon_raw

        return 'N/A'  # Either invalid measurement, or not available

    def get_value(self, sensor_index):
        return self.sensor_data[sensor_index]

    def get_unit(self, sensor_index):
        return SENSOR_UNITS[sensor_index]

    def __iter__(self):
        return zip(self.sensor_data, SENSOR_UNITS)


def main():
    # ---- Initialize ----#
    waveplus = WavePlus(SERIAL_NUMBER)

    if MODE == 'terminal':
        print('\nPress ctrl+C to exit program\n')

    print('Device serial number: {}'.format(SERIAL_NUMBER))

    try:
        if MODE == 'terminal':
            print(tableprint.header(SENSOR_HEADERS, width=12))
        elif MODE == 'pipe':
            print(SENSOR_HEADERS)

        while True:
            waveplus.connect()

            # read values
            sensors = waveplus.read()

            # extract
            data = [
                '{} {}'.format(data, unit)
                for data, unit in sensors
            ]

            if MODE == 'terminal':
                print(
                    tableprint.row(data, width=12))
            elif MODE == 'pipe':
                print(
                    data)

            waveplus.disconnect()

            time.sleep(SAMPLE_PERIOD)
    finally:
        waveplus.disconnect()


if __name__ == '__main__':
    main()
