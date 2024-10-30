from __future__ import annotations

import csv, logging, signal, sys, threading, time, typing

import otsim.msgbus.envelope as envelope
import xml.etree.ElementTree as ET

from otsim.msgbus.envelope import Point
from otsim.msgbus.pusher   import Pusher


# physics environment simulation for thermostat

import zmq
from halucinator.external_devices.ioserver import IOServer
from time import sleep
import random

def uart_write_handler(ioserver, msg):
    txt = msg['chars'].decode('latin-1')
    # ignore for now
    # print(txt, end='', flush=True)

HEATER_GPIO = '0x48000000_256'

# units are in Fahrenheit
class HeaterModel():
    def __init__(self):
        # same as the defines in Core/Src/main.c for the thermostat
        self.RAW_TO_TEMP_A = 0.175
        self.RAW_TO_TEMP_B = -22.2


        # how quickly heat is lost to the ambient environment
        self.heat_loss_rate = 0.015
        # how quickly heat is gained with the heater
        # this ratio is desired for similar behavior as the physical model
        self.heat_gain_rate = self.heat_loss_rate * 100

        self.ambient = 70
        self.temp = 90

    def update(self, dt, heater_output):
        assert dt > 0.0
        assert 0 <= heater_output and heater_output <= 1.0

        new_temp = self.temp
        new_temp += heater_output*dt * self.heat_gain_rate
        new_temp += (self.ambient - self.temp)*dt * self.heat_loss_rate
        self.temp = new_temp

        return self.temp

    def to_raw(self, temp):
        return (temp - self.RAW_TO_TEMP_B)/self.RAW_TO_TEMP_A

    def update_to_raw(self, dt, heater_output):
        v = self.update(dt, heater_output)
        # random perturbations to simulate noise
        v += (1 - 2*random.random()) * 0.8
        return self.to_raw(v)

class LocalServer(object):
    def __init__(self, ioserver):
        self.ioserver = ioserver
        ioserver.register_topic('Peripheral.GPIO.write_pin', self.write_handler)
        ioserver.register_topic('Peripheral.GPIO.toggle_pin', self.write_handler)
        ioserver.register_topic('Peripheral.ExternalTimer.delay', self.delay)
        ioserver.register_topic('Peripheral.ExternalTimer.start_timer', self.start_timer)
        ioserver.register_topic('Peripheral.ZmqPeripheral.hw_io', self.hw_io_handler)
        self.current_time = 0
        self.timer_active = False

        # internal model values
        self.heater_model = HeaterModel()

        # input state values (initial)
        self.heater_gpio = True

        # TODO: calculate tick times from based on guest options
        self.timer_frequency = 76.5/1000.0

    def write_handler(self, ioserver, msg):
        if msg['id'] == HEATER_GPIO:
            state = msg['value'] == 1
            self.heater_gpio = state

    def hw_io_handler(self, ioserver, msg):
        # pwm is at address 0x40012c34
        if msg['offset'] == 0x12c34:
            state = msg['value']
            self.heater_gpio = state

    def delay(self, ioserver, msg):
        delay = msg['value']
        self.current_time += delay
        # update time
        d = {'value': self.current_time}
        self.ioserver.send_msg('Peripheral.ExternalTimer.update_time', d)
        self.update_model()

    def tick(self):
        if not self.timer_active:
            return None

        # wait until we have all inputs
        if self.heater_gpio is None:
            return None

        # update model values
        heater_proportion = self.heater_gpio/65535.0
        dt = self.timer_frequency

        raw = self.heater_model.update_to_raw(dt, heater_proportion)

        print('heat:', int(self.heater_model.temp), 'raw:', raw, 'pwm output:', int(heater_proportion * 1000)/1000.0)
        self.ioserver.send_msg('Peripheral.ADC.ext_adc_change', {'id': '0', 'value': int(raw)})

        self.current_time += self.timer_frequency * 1000

        # reset inputs before calling interrupt (which would get us the next values)
        self.heater_gpio = None

        self.ioserver.send_msg('Peripheral.ExternalTimer.tick_interrupt', {'value': int(self.current_time)})
        return self.heater_model.temp

    def start_timer(self, ioserver, msg):
        print('starting timer')
        self.timer_active = True

def main():
    try:
        while True:
            server.tick()
    except KeyboardInterrupt:
        pass
    io_server.shutdown()
    # io_server.join()


if __name__ == '__main__':
    main()



class Halucinator:
  def __init__(self: Halucinator, pull: str, el: ET.Element):
    self.name = el.get('name', default='ot-sim-halucinator')

    data_tag_el = el.find('tag')

    self.data_tag = data_tag_el.text

    pull_endpoint = el.findtext('pull-endpoint', default=pull)
    self.pusher   = Pusher(pull_endpoint)


  def start(self: Halucinator):
    self.io_server = IOServer(5556, 5555)
    self.server = LocalServer(self.io_server)
    self.io_server.register_topic('Peripheral.UARTPublisher.write', uart_write_handler)
    self.io_server.start()

    threading.Thread(target=self.run, daemon=True).start()


  def stop(self: Halucinator):
    self.io_server.shutdown()


  def run(self: Halucinator):
    ts   = 0
    rows = None

    while True:
      new_temp = self.server.tick()

      if new_temp is not None:
        value = new_temp
        points: typing.List[Point] = [{'tag': self.data_tag, 'value': float(value), 'ts': ts}]

        env = envelope.new_status_envelope(self.name, {'measurements': points})
        self.pusher.push('RUNTIME', env)

      ts += 1 # must be an integer
      time.sleep(0.1)


def main():
  logging.basicConfig(level=logging.ERROR)

  if len(sys.argv) < 2:
    print('no config file provided')
    sys.exit(1)

  tree = ET.parse(sys.argv[1])

  root = tree.getroot()
  assert root.tag == 'ot-sim'

  mb = root.find('message-bus')

  if mb:
    pull = mb.findtext('pull-endpoint')
  else:
    pull = 'tcp://127.0.0.1:1234'

  modules: typing.List[Halucinator] = []

  for wp in root.findall('./halucinator'):
    module = Halucinator(pull, wp)
    module.start()

    modules.append(module)

  waiter = threading.Event()

  def handler(*_):
    waiter.set()

  signal.signal(signal.SIGINT, handler)
  waiter.wait()

  for module in modules:
    module.stop()
