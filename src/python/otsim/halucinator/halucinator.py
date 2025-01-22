"""
This module allows for interacting with GPIO pins in a firmware emulated with
halucinator. Pin interactions are directly sent to the OT-Sim message bus for
use with other modules.

Required tags:
- gpio-msg-prefix: prefix to add to gpio pins for message bus envelopes
"""

from __future__ import annotations

import csv, logging, signal, sys, threading, time, typing

import otsim.msgbus.envelope as envelope
import xml.etree.ElementTree as ET

from otsim.msgbus.envelope import Point
from otsim.msgbus.pusher   import Pusher
from otsim.msgbus.subscriber import Subscriber


import zmq
from halucinator.external_devices.ioserver import IOServer
from time import sleep


class HalucinatorServer(object):
    def __init__(self, ioserver, pin_write_handler):
        self.ioserver = ioserver
        ioserver.register_topic('Peripheral.GPIO.write_pin', self.write_handler)
        ioserver.register_topic('Peripheral.GPIO.toggle_pin', self.write_handler)
        self.current_time = 0
        self.tick_delay = 500
        self.pin_write_handler = pin_write_handler

    def write_handler(self, ioserver, msg):
        pin = msg['id']
        value = msg['value']
        self.pin_write_handler(pin, value)

    def tick(self):
        self.current_time += self.tick_delay
        d = {'value': self.current_time}
        self.ioserver.send_msg('Peripheral.ExternalTimer.update_time', d)


class Halucinator:
  def __init__(self: Halucinator, pub: str, pull: str, el: ET.Element):
    self.name = el.get('name', default='ot-sim-halucinator')

    self.gpio_msg_prefix = el.find('gpio-msg-prefix').text

    pub_endpoint  = el.findtext('pub-endpoint', default=pub)
    pull_endpoint = el.findtext('pull-endpoint', default=pull)

    self.zmq_rx = int(el.findtext('zmq-rx', default='5556'))
    self.zmq_tx = int(el.findtext('zmq-tx', default='5555'))

    self.subscriber = Subscriber(pub_endpoint)
    self.pusher   = Pusher(pull_endpoint)

    self.subscriber.add_update_handler(self.handle_msgbus_update)

    self.ts = 0


  def start(self: Halucinator):
    self.subscriber.start('RUNTIME')

    self.io_server = IOServer(self.zmq_rx, self.zmq_tx)
    self.server = HalucinatorServer(self.io_server, self.pin_update)
    self.io_server.start()

    threading.Thread(target=self.run, daemon=True).start()


  def stop(self: Halucinator):
    self.io_server.shutdown()
    self.subscriber.stop()


  def run(self: Halucinator):
    while True:
      self.server.tick()
      sleep(self.server.tick_delay/1000)

      self.ts += 1 # must be an integer
      time.sleep(0.1)

  def pin_update(self, pin, val):
    tag = self.gpio_msg_prefix + str(pin)
    points: typing.List[Point] = [{'tag': tag, 'value': val, 'ts': self.ts}]
    env = envelope.new_status_envelope(self.name, {'measurements': points})
    self.pusher.push('RUNTIME', env)


  def handle_msgbus_update(self: Halucinator, env: Envelope):
    update = envelope.update_from_envelope(env)

    if update:
      for point in update['updates']:
        tag = point['tag']
        if self.gpio_msg_prefix in tag:
          pin = int(tag.split(self.gpio_msg_prefix)[1])
          pin_set = point['value']
          self.io_server.send_msg('Peripheral.GPIO.ext_pin_change', {'id': pin, 'value': pin_set})


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
    pub  = mb.findtext('pub-endpoint')
    pull = mb.findtext('pull-endpoint')
  else:
    pub  = 'tcp://127.0.0.1:5678'
    pull = 'tcp://127.0.0.1:1234'

  modules: typing.List[Halucinator] = []

  for el in root.findall('./halucinator'):
    module = Halucinator(pub, pull, el)
    module.start()

    modules.append(module)

  waiter = threading.Event()

  def handler(*_):
    waiter.set()

  signal.signal(signal.SIGINT, handler)
  waiter.wait()

  for module in modules:
    module.stop()
