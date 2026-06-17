# -*- coding: utf-8 -*-
from threading import Thread, Event
import logging
import queue
import socket
import binascii
from pprint import pprint  # noqa: F401


# ##############################################################################
from . constants import LOGGING_LEVEL
from . asterix_encoder import AsterixEncoder


# ##############################################################################
class AxSender(Thread):
    def __init__(self, config, mapper):
        self._config = config
        self._mapper = mapper
        self._encoder = AsterixEncoder()
        self._socks = []

        # unicast endpoints
        if self._config['ax']['unicast']:
            for uep in self._config['ax']['unicast_endpoints']:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socks.append((s, (uep['addr'], uep['port'])))

        # multicast endpoints
        if self._config['ax']['multicast']:
            for mep in self._config['ax']['multicast_endpoints']:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, mep['ttl'])
                self._socks.append((s, (mep['group'], mep['port'])))

        self._input_queue = self._mapper._output_queue
        self._input_queue_timeout = self._config['ax']['input_queue_wait_timeout']

        self._setup_logger()
        self._ev = Event()
        self._ev.clear()
        Thread.__init__(self)

    def run(self):
        self._log.info("starting sender [SAC:{} SIC:{}] ({} endpoint/s)".format(
            self._config['default']['SAC'], self._config['default']['SIC'], len(self._socks)))
        ep_cnt = 1
        if self._config['ax']['unicast']:
            for uep in self._config['ax']['unicast_endpoints']:
                self._log.info("endpoint #{}: @udp://{}:{} (unicast)".format(ep_cnt, uep['addr'], uep['port']))
                ep_cnt += 1
        if self._config['ax']['multicast']:
            for mep in self._config['ax']['multicast_endpoints']:
                self._log.info("endpoint #{}: @udp://{}:{} ttl={} (multicast)".format(ep_cnt, mep['group'], mep['port'], mep['ttl']))
                ep_cnt += 1
        while not self._ev.is_set():
            try:
                data = self._input_queue.get(block=True, timeout=self._input_queue_timeout)
                self._log.debug(data)
                try:
                    encoded = self._encoder.encode(data)
                    self._log.debug('"{}"'.format(binascii.hexlify(encoded).decode('ascii')))
                    for sock, endpoint in self._socks:
                        sock.sendto(encoded, endpoint)
                except:
                    self._log.exception('Upsss!')
            except queue.Empty:
                pass

    def stop(self):
        self._log.info("ending sender...")
        for s, e in self._socks:
            try:
                self._log.info("closing {}:{}...".format(*e))
                s.close()
            except:
                pass
        self._ev.set()

    def _setup_logger(self):
        self._log = logging.getLogger('{}.{}'.format(self._config['logger']['name'],
                                                     self._config['ax']['log_name']))
        self._log.setLevel(LOGGING_LEVEL[self._config['ax']['log_level']])
