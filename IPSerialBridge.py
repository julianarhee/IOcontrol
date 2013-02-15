#
#  IPSerialBridge.py
#  Basic NE500 pump control.
#
#  DATE: 02.15.2013 (jyr)
#  
#

import errno
import time
import socket
import select

import sys




class IPSerialBridge:

    def __init__(self, address, port):
        self.socket = None
        self.address = address
        self.port = port
        
    
    def __del__(self):
        self.disconnect()
    
    def connect(self, timeout=1):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(timeout)#timeout)
        except socket.error, e:
            print "Some error creating socket: %s" % e
            sys.exit(1)

        try:
            self.socket.connect((self.address, self.port)) #(self.address, self.port)
            self.socket.setblocking(0)
            self.socket.settimeout(0)
        except socket.gaierror, e:
            print "Address-related error connecting to server: %s" % e
            sys.exit(1)
        except socket.error, e:
            print "Connection error: %s" % e
            sys.exit(1)
        # self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # self.socket.settimeout(timeout)#timeout)
        # self.socket.connect((self.address, self.port)) #(self.address, self.port)
        # self.socket.setblocking(0)
        # self.socket.settimeout(0)
        #self.kq = select.kqueue()
        #self.kq.control([select.kevent(self.socket, select.KQ_FILTER_READ, select.KQ_EV_ADD)],0)

        
    def disconnect(self):
        #self.kq.control([select.kevent(self.socket, select.KQ_FILTER_READ, select.KQ_EV_DELETE)],0)
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
      
    
    def read(self):
        still_reading = 1
        response = ""

        while(still_reading and len(response)<5):
            try:
                response += self.socket.recv(5)
                print "added response from recv: ", response
                print "response length: ", len(response)
                if len(response) == 5:
                    still_reading = 1
            except socket.error, (value, message):
                print "READ error val: %s" % value
                print "READ error msg: %s" % message
                # sys.exit(1)
                # if(value == errno.EWOULDBLOCK or value == errno.EAGAIN):
                    # time.sleep(5.0)
                    # pass
                    # print message # should be commented out, just check out error
                    # pass
                    # still_reading = 0 # should be commented out
                # else:
                    # print "Network error"
                    # pass  # TODO deal with this

            if(response != None and len(response) > 0 and response[-1] == '\n'):
                still_reading = 0
        
        
        if(self.verbose):
            print("RECEIVED (%s; %s): %s" % (self.address, str(self), response))

        
        return response


    def safesend(self, msg):
        msglen = len(msg)
        totalsent = 0
        while totalsent < msglen:
            sent = self.send(msg[totalsent:])
            if sent == 0:
                raise RuntimeError, 'connection broken'
            totalsent = totalsent + sent

        return totalsent
        
    
    def send(self, message, noresponse = 0):
        
        # check the socket to see if there is junk in there already on the receive side
        # if so, this is here in error, and should be flushed
        (ready_to_read, ready_to_write, in_error) = select.select([self.socket],[],[self.socket], 0)
        if(len(ready_to_read) != 0):
            self.read()
        
        # send the outgoing message
        self.socket.send(message + "\n\r")
        
        # self.verbose = 0
        if(self.verbose):
            print("SENDING (%s; %s): %s\n\r" % (self.address, str(self), message))
        
        # time.sleep(0.1)  # allow some time to pass
        
        if(noresponse):
            return
        
        ## alternative read, 50 ms
        #print "reading",
        #s = time.time()
        ##kq = select.kqueue()
        ##kq.control([select.kevent(self.socket, select.KQ_FILTER_READ, select.KQ_EV_ADD)],0)
        #evs = self.kq.control(None, 1, 30)
        ##kq.control([select.kevent(self.socket, select.KQ_FILTER_READ, select.KQ_EV_DELETE)],0)
        #r = ""
        #for e in evs:
        #    if e.flags & select.KQ_FILTER_READ:
        #        print "%.3f" % (time.time() -s), "read flag!",
        #        r = self.read()
        #print "%.3f" % (time.time() - s)
        #return r
        #
        ##read the response, 50 ms
        #print "reading",
        ready = 0
        # print "ready val ", ready
        retry_timeout = 0.1
        timeout = 30.0
        tic = time.time()
        while(not ready):
            # print "tick", time.time() - tic,
            # takes ~50 ms
            (ready_to_read, ready_to_write, in_error) = select.select([self.socket],[],[self.socket], retry_timeout)
            # print "tock", time.time() - tic,
            if(len(ready_to_read) != 0):
                ready = 1
            if(time.time() - tic > timeout):
                return ""
        # print "%.3f" % (time.time() - tic),
        #r = self.read()
        #print r
        #return r
        return self.read()
        

# PumpInfuse = """01 FUN RAT
#     01 DIR INF
#     01 VOL 0.5
#     01 RUN"""

PumpInfuse = """01 DIR INF
    01 VOL 0.02
    01 RUN"""    

# PumpWDraw = """01 FUN RAT
#     01 DIR WDR
#     01 VOL 0.02
#     01 RUN\r"""

PumpWDraw = """01 DIR WDR
    01 VOL 0.04
    01 RUN"""


if __name__ == "__main__":

    print "Instantiating"
    bridge = IPSerialBridge("192.168.0.10", 100)
    bridge.verbose = 1
    
    print "Connecting"
    connecting = None
    try:
        connecting = bridge.connect()
    except socket.error as msg:
        print "Sending during CONNECTING went bad: ", msg
        # sys.exit(1)

    # connecting.close()
    # connecting = bridge.connect()
    # if connecting != 0:
    #     sys.exit(1)

    print "Testing"
    try: 
        response = bridge.send("Test")
    except socket.error as msg:
        print "Sending during TESTING went bad: ", msg

     # connecting.close()

    # print "Testing"
    # response = bridge.send("Test")


    print "What test would you like to perform?"
    print " 1: infuse"
    print " 2: withdraw"
    print " 3: stop"
    cmdIndex = int(raw_input())


    if cmdIndex == 1:
        print "infusing"
        for command in PumpInfuse.splitlines():
            cmd = command.strip() 
            response = bridge.send(cmd,0)
            print "Attempting cmd: %s" % cmd 
            print "out ", response
    elif cmdIndex == 2:
        print "withdrawing"
        for command in PumpWDraw.splitlines():
            cmd = command.strip()
            response = bridge.send(cmd,0)
            print "out ", response
    elif cmdIndex == 3:
        print "stopping"
        response = bridge.send("01 STP",1)
        print "out ", response
    else:
        print "Unknown command..."


print "out of loop"


    # bridge.disconnect()

    
    # print "Sending"
    # response = bridge.send("Test")
    
    # print "Response :", response

    # bridge.disconnect()

    # print "Instantiating again"
    # bridge = IPSerialBridge("192.168.0.10", 100)

    # print "Connecting again"
    # bridge.connect()

    # print "Sending vol amt"
    # response = bridge.send("01 VOL 0.0")

    # bridge.release()


    # print "Running"
    # run_it = bridge.send("01 RUN")
    
    # print "stopping"
    # stp_it = bridge.send("01 STP")

    # print "Sending"
    # response = bridge.send("Test")
    
    # print "Response :", response

    # pumps={'01':1, '02':2}
    # print "Testing command"
    # response = bridge.send(sorted(pumps.keys())[0] + " FUN RAT") 

    # response2 = bridge.send(sorted(pumps.keys())[0] + " VOL 0.02")
