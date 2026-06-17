# -*- coding: utf-8 -*-
from threading import Thread
from xmlrpc.server import SimpleXMLRPCServer
from functools import wraps


# ##############################################################################
def xmlrpc_log(method):
    @wraps(method)
    def _wf(self, *params):
        if self._log is not None:
            self._log.debug("calling {}{}".format(method.__name__, repr(params)))
        res = method(self, *params)
        if self._log is not None:
            self._log.debug("return {}".format(repr(res)))
        return res
    return _wf


# ------------------------------------------------------------------------------
class XMLRPCServer(SimpleXMLRPCServer):
    allow_reuse_address = True

    def __init__(self, addr, **kw):
        self._log = None
        self._parent = None

        if 'logger' in kw:
            self._log = kw['logger']
            del kw['logger']
            kw['logRequests'] = False

        if 'parent' in kw:
            self._parent = kw['parent']
            del kw['parent']
        try:
            SimpleXMLRPCServer.__init__(self, addr, **kw)
        except OSError:
            pass

    def _dispatch(self, method, params):
        try:
            func = getattr(self, 'xmlrpc_{}'.format(method))
        except AttributeError:
            raise Exception('method "{}" is not supported'.format(method))
        else:
            return func(*params)

    def shutdown(self):
        SimpleXMLRPCServer.shutdown(self)
        self.socket.close()

    @xmlrpc_log
    def xmlrpc_enable_blips_c(self):
        if self._parent is not None:
            return self._parent.enable_blips_c()
        return False

    @xmlrpc_log
    def xmlrpc_disable_blips_c(self):
        if self._parent is not None:
            return self._parent.disable_blips_c()
        return False

    @xmlrpc_log
    def xmlrpc_enable_blips_s(self):
        if self._parent is not None:
            return self._parent.enable_blips_s()
        return False

    @xmlrpc_log
    def xmlrpc_disable_blips_s(self):
        if self._parent is not None:
            return self._parent.disable_blips_s()
        return False

    def xmlrpc_keepalive(self):
        if self._parent is not None:
            return self._parent.keepalive()
        return False


# ------------------------------------------------------------------------------
class XMLRPCThread(Thread):
    def __init__(self, parent, config, logger):
        self._parent = parent
        self._cfg = config
        self._host = self._cfg['host']
        self._port = self._cfg['port']
        self._log = logger.getChild('xmlrpc')
        self._log.setLevel(self._cfg['loglevel'])
        self._server = XMLRPCServer((self._host, self._port), parent=self._parent, logger=self._log, allow_none=True)
        Thread.__init__(self)

    def run(self):
        self._log.info('starting xmlrpc server on http://{}:{}'.format(self._host, self._port))
        try:
            self._server.serve_forever()
        except ValueError:
            pass

    def stop(self):
        self._server.shutdown()
        self._log.info('stopping xmlrpc server...')
