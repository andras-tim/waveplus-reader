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
from typing import List, Tuple

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

        raw_data = self.curr_val_char.read()
        raw_data = struct.unpack('<BBBBHHHHHHHH', raw_data)

        return parse_data(raw_data)

    def disconnect(self):
        if self.peripheral is None:
            return

        self.peripheral.disconnect()
        self.peripheral = None
        self.curr_val_char = None


# ===================================
# Class Sensor and sensor definitions
# ===================================


class Sensor:
    UNIT = None

    def __int__(self, raw_data):
        self.__value = self._convert(raw_data)

    def _convert(self, raw_data):
        return raw_data

    @property
    def value(self):
        return self.__value

    def __str__(self) -> str:
        return '{} {}'.format(self.__value, self.__class__.UNIT)


class HumiditySensor(Sensor):
    UNIT = '%rH'

    def _convert(self, raw_data):
        return raw_data / 2.0


class RadonSensor(Sensor):
    UNIT = 'Bq/m3'

    def _convert(self, raw_data):
        if 0 <= raw_data <= 16383:
            return raw_data

        return 'N/A'  # Either invalid measurement, or not available


class TemperatureSensor(Sensor):
    UNIT = '°C'

    def _convert(self, raw_data):
        return raw_data / 100.0


class AtmPressureSensor(Sensor):
    UNIT = 'hPa'

    def _convert(self, raw_data):
        return raw_data / 50.0


class Co2Sensor(Sensor):
    UNIT = 'ppm'


class VocSensor(Sensor):
    UNIT = 'ppb'


SENSORS_V1 = [
    ('Humidity', HumiditySensor),
    ('Radon ST avg', RadonSensor),
    ('Radon LT avg', RadonSensor),
    ('Temperature', TemperatureSensor),
    ('Pressure', AtmPressureSensor),
    ('CO2 level', Co2Sensor),
    ('VOC level', VocSensor),
]


def parse_data(raw_data: tuple) -> Tuple[List[str], List[Sensor]]:
    sensor_version = raw_data[0]

    if sensor_version == 1:
        sensor_spec = SENSORS_V1
    else:
        print('ERROR: Unknown sensor version.\n')
        print('GUIDE: Contact Airthings for support.\n')

        sys.exit(1)

    titles = []
    sensors = []

    for sensor, raw_value in zip(sensors, raw_data[4:]):
        titles.append(sensor[0])
        sensors.append(sensor[1](raw_value))

    return titles, sensors


def main():
    # ---- Initialize ----#
    waveplus = WavePlus(SERIAL_NUMBER)

    if MODE == 'terminal':
        print('\nPress ctrl+C to exit program\n')

    print('Device serial number: {}'.format(SERIAL_NUMBER))

    line_index = 0

    try:
        while True:
            waveplus.connect()

            # read values
            header, sensors = waveplus.read()

            if line_index == 0:
                if MODE == 'terminal':
                    print(tableprint.header(header, width=12))
                elif MODE == 'pipe':
                    print(header)

            # extract
            data = [str(sensor) for sensor in sensors]

            if MODE == 'terminal':
                print(tableprint.row(data, width=12))
            elif MODE == 'pipe':
                print(data)

            waveplus.disconnect()

            if line_index > 20:
                line_index = 0

            time.sleep(SAMPLE_PERIOD)
    finally:
        waveplus.disconnect()


if __name__ == '__main__':
    main()
