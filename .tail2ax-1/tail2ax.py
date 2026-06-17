#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ##############################################################################
import time
import os
import sys
from threading import Thread, Event, Timer
from pathlib import Path
import signal
from xmlrpc.client import ServerProxy

# ##############################################################################
from bridge.config import read_config
from bridge.logger import setup_logger
from bridge.subscriber import TAILSubscriber
from bridge.mapper import Tail2AxMapper
from bridge.sender import AxSender
from bridge.xmlrpcserver import XMLRPCThread
from bridge import pydaemon

# ##############################################################################
VERSION = '1.0.0'
BUILD = '20220927112856'

# ##############################################################################
CMD = ['enable_blips_c',
       'disable_blips_c',
       'enable_blips_s',
       'disable_blips_s',
       'keepalive']


# ##############################################################################
class TAIL2Asterix(Thread):
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger(self.config)
        self._pidfile = self.config['daemon']['pidfile']
        self._subscriber = TAILSubscriber(self.config)
        self._mapper = Tail2AxMapper(self.config, self._subscriber)
        self._sender = AxSender(self.config, self._mapper)
        self._rpc = XMLRPCThread(self, self.config['default']['rpc'], self.logger)
        self._stopping = False
        self._ev = Event()
        self._ev.clear()
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        Thread.__init__(self)

    def run(self):
        self.logger.info('starting tail2ax. version:{} build:{}...'.format(VERSION, BUILD))
        self._subscriber.start()
        self._mapper.start()
        self._sender.start()
        self._rpc.start()
        if self.config['default']['keepalive']:
            self.logger.info("keepalive enable: {} secs".format(self.config['default']['keepalive']))
            self._keepalive_timer = Timer(self.config['default']['keepalive'], self.stop)
            self._keepalive_timer.start()
        else:
            self.logger.info("keepalive disable")
        while True:
            if int(time.time()) % 3600 == 0:
                self.logger.info("<<< MARK >>>")
            if self._ev.wait(1):
                break
        time.sleep(self.config['default']['exit_timeout'])
        try:
            os.remove(self._pidfile)
        except FileNotFoundError:
            pass

    def stop(self, signum=None, stackframe=None):
        if not self._stopping:
            self._stopping = True
            self._subscriber.stop()
            self._mapper.stop()
            self._sender.stop()
            self._rpc.stop()
            self.logger.info('ending tail2ax...')
            self.logger.info('{} {}'.format(chr(9988), '-' * 60))
            self._ev.set()

    def enable_blips_c(self):
        self.logger.info('enable_blips_c')
        self._subscriber.enable_blips_c()
        return True

    def disable_blips_c(self):
        self.logger.info('disable_blips_c')
        self._subscriber.disable_blips_c()
        return True

    def enable_blips_s(self):
        self.logger.info('enable_blips_s')
        self._subscriber.enable_blips_s()
        return True

    def disable_blips_s(self):
        self.logger.info('disable_blips_s')
        self._subscriber.disable_blips_s()
        return True

    def keepalive(self):
        if self.config['default']['keepalive']:
            self._keepalive_timer.cancel()
            self._keepalive_timer = Timer(self.config['default']['keepalive'], self.stop)
            self._keepalive_timer.start()
        return True


if __name__ == '__main__':
    global bridge
    config = read_config('tail2ax.yaml')

    if sys.platform != 'win32' and len(sys.argv) < 3:
        action = sys.argv[1]
        if action in CMD:
            s = ServerProxy('http://{}:{}'.format(config['default']['rpc']['host'], config['default']['rpc']['port']))
            eval('s.{}()'.format(action))
            os._exit(0)
        bridge = TAIL2Asterix(config)
        pydaemon.HOME = os.path.abspath('.')
        pin = Path(bridge.config['daemon']['stdin'])
        pout = Path(bridge.config['daemon']['stdout'])
        perr = Path(bridge.config['daemon']['stderr'])
        pidfile = Path(bridge.config['daemon']['pidfile'])
        pout.touch()
        perr.touch()
        pydaemon.startstop(stdout=str(pout),
                           stderr=str(perr),
                           stdin=str(pin),
                           pidfile=str(pidfile),
                           startmsg='{} started with pid %s'.format(sys.argv[0])
                           )
    else:
        bridge = TAIL2Asterix(config)

    bridge.start()
    bridge.join()
    os._exit(0)
