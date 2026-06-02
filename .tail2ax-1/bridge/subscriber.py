# -*- coding: utf-8 -*-

# ##############################################################################
from threading import Thread, Event
import logging
import sys
import io
import zmq
import queue
import ctypes
import binascii

from pprint import pprint  # noqa: F401

# ##############################################################################
from . constants import LOGGING_LEVEL
from . types import BLIP_T, BLIP_S_T


# ##############################################################################
class TAILSubscriber(Thread):
    def __init__(self, config):
        self._config = config
        self._url = self._config['tail']['url']
        self._topic_c = self._config['tail']['topic_mode_c']
        self._topic_s = self._config['tail']['topic_mode_s']
        self._btopic_c = bytes(self._topic_c, encoding='ascii')
        self._btopic_s = bytes(self._topic_s, encoding='ascii')
        self._poll_timeout = self._config['tail']['zmq_poll_timeout']
        self._queue_timeout = self._config['tail']['output_queue_wait_timeout']
        self._output_queue_maxsize = self._config['tail']['output_queue_max_size']
        self._output_queue = queue.Queue(maxsize=self._output_queue_maxsize)
        self._output_queue_wl = int(self._output_queue_maxsize * self._config['tail']['output_queue_warning_level'])
        self._setup_logger()
        self._enable_blips_c = True
        self._enable_blips_s = True
        self._ev = Event()
        self._ev.clear()
        self._end = False
        Thread.__init__(self)

    def run(self):
        self._end = False
        self._log.info("starting subscriber: max_output_queue_size:{}".format(self._output_queue_maxsize))
        self._log.info("mode-c listening @{}/{}".format(self._url, self._topic_c))
        self._log.info("blips mode-c: {}".format("enabled" if self._enable_blips_c else "disabled"))
        self._log.info("mode-s listening @{}/{}".format(self._url, self._topic_s))
        self._log.info("blips mode-s: {}".format("enabled" if self._enable_blips_s else "disabled"))
        self._zmq_context = zmq.Context()
        self._zmq_socket = self._zmq_context.socket(zmq.SUB)
        self._zmq_socket.set(zmq.TCP_KEEPALIVE, 1)
        self._zmq_socket.set(zmq.TCP_KEEPALIVE_IDLE, 2 * 60)
        self._zmq_socket.set(zmq.TCP_KEEPALIVE_INTVL, 30)
        self._zmq_socket.connect(self._url)
        self._zmq_socket.subscribe(self._btopic_c)
        self._zmq_socket.subscribe(self._btopic_s)
        self._zmq_poller = zmq.Poller()
        self._zmq_poller.register(self._zmq_socket, zmq.POLLIN)
        while not self._ev.is_set():
            try:
                events = self._zmq_poller.poll(self._poll_timeout)
                if self._zmq_socket in dict(events):
                    topic, msg = self._zmq_socket.recv_multipart()
                    if topic == self._btopic_c:
                        if not self._enable_blips_c:
                            continue
                        blip = BLIP_T()
                        mlen = ctypes.sizeof(blip)
                        mode = 'C'
                    elif topic == self._btopic_s:
                        if not self._enable_blips_s:
                            continue
                        blip = BLIP_S_T()
                        mlen = ctypes.sizeof(blip)
                        mode = 'S'
                    else:
                        self._log.warning("topic '{}' not valid".format(topic))
                        continue

                    if len(msg) != mlen:
                        self._log.warning("message length ({} bytes) incorrect. should be {} bytes".format(len(msg), mlen))
                        continue
                    self._log.debug('"{}"'.format(binascii.hexlify(msg).decode('ascii')))
                    msg_buffer = io.BytesIO(msg)
                    msg_buffer.readinto(blip)
                    flags = bytes(blip.flags)
                    self._check_output_queue_level()
                    try:
                        self._output_queue.put((mode, flags, blip.to_dict()), block=True, timeout=self._queue_timeout)
                    except queue.Full:
                        self._log.error("output queue FULL ({} items)".format(self._output_queue_maxsize))
            except zmq.error.ZMQError:
                self._log.debug(sys.exc_info()[1])
            except:
                self._log.exception()
        self._end = True

    def _check_output_queue_level(self):
        if self._output_queue_maxsize <= 0:
            return
        qs = self._output_queue.qsize()
        if qs >= self._output_queue_wl:
            self._log.warning("output queue over limit ({}/{}) {:.1f}%".format(qs, self._output_queue_maxsize, (qs / self._output_queue_maxsize) * 100))

    def stop(self):
        self._log.info("ending subscriber...")
        self._ev.set()
        while not self._end:
            pass
        self._zmq_socket.close()
        self._zmq_context.term()

    def _setup_logger(self):
        self._log = logging.getLogger('{}.{}'.format(self._config['logger']['name'],
                                                     self._config['tail']['log_name']))
        self._log.setLevel(LOGGING_LEVEL[self._config['tail']['log_level']])

    def enable_blips_c(self):
        self._log.info('enable_blips_c')
        self._enable_blips_c = True

    def disable_blips_c(self):
        self._log.info('disable_blips_c')
        self._enable_blips_c = False

    def enable_blips_s(self):
        self._log.info('enable_blips_s')
        self._enable_blips_s = True

    def disable_blips_s(self):
        self._log.info('disable_blips_s')
        self._enable_blips_s = False
