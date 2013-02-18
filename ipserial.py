#
# clean-up, fxies to "IPSerialBridge.py" in IOcontrol repo 
# DATE:  02.15.2013 (bg)
#

import errno
import time
import socket
import select


class IPSerial(object):
    def __init__(self, address, port, timeout=0.01, sleep_on_timeout=0.01, max_timeouts=1,
            autoconnect=True):
        """
        address : str
            ip address to connect to
        
        port : int
            port to connec to
        
        timeout : float
            read/write timeout (for select) in seconds
        
        sleep_on_timeout : float
            seconds to wait after a read/write timeout
        
        max_timeouts : int
            maximum number of read/write timeouts for a given read/write
        """
        self.socket = None
        self.address = address
        self.port = port
        self.timeout = timeout
        self.sleep_on_timeout = sleep_on_timeout
        self.max_timeouts = max_timeouts
        if autoconnect:
            self.connect()
    
    def __del__(self):
        self.disconnect()
    
    def connect(self, timeout=1):
        """
        timeout : float
            connect timeout in seconds (will raise socket.timeout on timeout)
        """
        if self.socket is not None:
            raise IOError('Attempt to call connect on already connected socket: %s' % \
                self.socket)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.settimeout(timeout)
        try:
            self.socket.connect((self.address, self.port))
        except socket.timeout as E:
            # clean up
            del self.socket
            self.socket = None
            # reraise
            raise E
        self.socket.settimeout(None)
    
    def disconnect(self):
        if self.socket is not None:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
            del self.socket
            self.socket = None
    
    def read(self, nbytes=-1):
        """
        read nbytes from the socket
        
        if nbytes 0, return ""
        if nbytes <0, read until a timeout
        """
        if self.socket is None:
            raise IOError("read called on not-connected socket")
        if nbytes == 0:
            return ""
        resp = ""
        if nbytes < 0:
            break_on_timeout = True
            nbytes = 1
        else:
            break_on_timeout = False
        ntimeout = 0
        while len(resp) < nbytes:
            r, _, _ = select.select([self.socket], [], [], self.timeout)
            if len(r) != 0:
                resp += self.socket.recv(1)
            else:
                if break_on_timeout:
                    return resp
                else:
                    ntimeouts += 1
                    if ntimeouts >= self.max_timeouts:
                        raise IOError('read timed out too many times [%s >= %s]' % \
                            (ntimeouts, self.max_timeouts))
                    time.sleep(self.sleep_on_timeout)
            # if we're waiting for a timeout, keep reading until we get one
            if break_on_timeout:
                nbytes = len(resp) + 1
        return resp
    
    def write(self, data):
        """
        write data to the socket
        
        data : str
            data to write
        """
        if self.socket is None:
            raise IOError("write called on not-connected socket")
        ntimeouts = 0
        while ntimeouts < self.max_timeouts:
            _, w, _ = select.select([], [self.socket], [], self.timeout)
            if (len(w) != 0):
                self.socket.send(data)
                return
        raise IOError('write timed out too many times [%s >= %s]' % \
            (ntimeouts, self.max_timeouts))
    
    def write_then_read(self, data, nbytes=-1, pause=0.1):
        """
        write, then read from the socket (with an options brief pause)
        
        data : str
            see write
        
        nbytes : int
            see read
        
        pause : float
            seconds to wait between write and read
        """
        self.write(data)
        time.sleep(pause)
        return self.read(nbytes)


class NE500Network(IPSerial):
    def __init__(self, *args, **kwargs):
        """
        see IPSerial for additional args and kwargs
        
        NE500Network kwargs are...
        
        npumps : int
            number of pumps in network
        """
        self.npumps = kwargs.pop('npumps', 1)
        IPSerial.__init__(self, *args, **kwargs)
    
    def infuse(self, pump, volume):
        assert ((pump > 0) and (pump <= self.npumps))
        assert isinstance(volume, float)
        self.write_then_read('%02i DIR INF\r' % pump)
        self.write_then_read('%02i VOL %.4f\r' % (pump, volume))
        self.write_then_read('%02i RUN\r' % pump)
    
    def withdraw(self, pump, volume):
        assert ((pump > 0) and (pump <= self.npumps))
        assert isinstance(volume, float)
        self.write_then_read('%02i DIR WDR\r' % pump)
        self.write_then_read('%02i VOL %.4f\r' % (pump, volume))
        self.write_then_read('%02i RUN\r' % pump)