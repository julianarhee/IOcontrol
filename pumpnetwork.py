#
# pumpnetwork.py
# 
# DATE:  02.15.2013 (jyr)
#

import sys

import errno
import time
import socket
import select

import IPSerialBridge


class IPSerial(object):
    def __init__(self, address, port, timeout=0.01, sleep_on_timeout=0.01, max_timeouts=1,
            autoconnect=True):
        """
        address : str
            ip address to connect to
        
        port : int
            port to connect to
        
        timeout : float
            read/write timeout (for select() in seconds
        
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
        try:    
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.settimeout(timeout)
        except socket.error, e:
            print "Some error creating socket: %s" % e
            sys.exit(1)
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
        ntimeouts = 0
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

        nsetups : int
            number of setups in network

        """
        self.npumps = kwargs.pop('npumps', 1)
        self.nsetups = kwargs.pop('nsetups', 4)
        IPSerial.__init__(self, *args, **kwargs)

    def connect(self, timeout=1, pump_wait=0.1):
        IPSerial.connect(self, timeout)
        time.sleep(pump_wait)
        return self.read()

    def response_read(self, nbytes=5):
        assert nbytes > 2
        resp = IPSerial.read(self, nbytes)

        while not ('\x02' in resp and '\x03' in resp):
            resp = IPSerial.read(self, nbytes)
            print resp

        if(self.verbose):
            print("RECEIVED (%s; %s): %s" % (self.address, str(self), resp))

        return resp

    def call_and_response(self, data, nbytes=5, pause=0.1):
        if data[-1] != '\r':
            data += '\r'
        self.write(data)

        if(self.verbose):
            print("SENDING (%s; %s): %s\n\r" % (self.address, str(self), data))

        time.sleep(pause)

        return self.response_read(nbytes)

    def call_and_read(self, data, nbytes=-1, pause=0.1):
        if data[-1] != '\r':
            data += '\r'
        self.write(data)

        if(self.verbose):
            print("SENDING (%s; %s): %s\n\r" % (self.address, str(self), data))

        time.sleep(pause)

        return self.read()

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


    # =============== Command functions ========================

    # pump function/"program" commands sent to IO bridge:
    # 0P FUN RAT : includes RAT, VOL, DIR for pump 0P
    # DIA [<float>] : inside diam of syringe (0.1mm-50.0mm). 
    # --sets the units for VOL and DIS, too
    
    # if syringe < 10 ml, VOL units microL; if >= 10 ml (i.e., 
    #       14.01-50.0 mm DIA), VOL units ml
    # RAT [<float>] : rate of pumping, can change while running
    # VOL [<float>] : vol to be inf/wdr. 
    # --if VOL = 0.0, continuous and can change direction. 
    # --changing DIR will change accumulated DIS (vol dispensed 
    #       for a given direction, INF | WDR)
    # DIR [str] : INF | WDR 
    # -- DIR REV will reverse pumping direction I <--> W

    def continuous_flow(self, pump, commandset, continuous=1):
        response=""
        alarm = -1
        while (alarm) < 0:
            for cmd, param in commandset.items():
                reply = self.write_then_read('%02i %s %.4f' % (pump, cmd, param))
                # do sth where next command not sent until til current command processed
                # completion of command processing = when first byte of resp packet transmitted
                alarm == reply.find('?')
                return
        print "Alarm detected in pump %02i, of type %s" % (pump, reply)
        # do other stuff...
        # command errors:
        # '?' = command not recog
        # '?NA' = command not applicable
        # '?OOR' = command data out of range
        # 'A' = alarm

    def stop(self, pump):
        assert ((pump > 0) and (pump <= self.npumps))
        self.write_then_read('%02i STP\r' % pump)

    def reset(self, pump):
        """This will reset ALL pump params, regardless of its address"""
        self.write_then_read('%02i * RESET\r' % pump)

    def get_commandset(self, mode):
        """set of pertinent commands and associated parameters for particular pump modes

        cmdset is a str [ 'training' | 'cleaning' ]

        cmds : list of str elements
            ['DIA', 'RAT', 'VOL', 'DIR', 'DIS']

        params : list of str elements

        'cleaning' : dict
            {'DIA':'15.0', 'RAT':'100.0', 'VOL':'1.0', 'DIR':'WDR'}

        'cleaning_rev' : dict
            {'DIA':'15.0', 'RAT':'100.0', 'VOL':'1.0', 'DIR':'INF'}

        'training' : dict 
            {'DIA':'15.0', 'RAT':'100.0', 'VOL':'0.02', 'DIR':'INF'}
        """

        cmds = ['DIA', 'RAT', 'VOL', 'DIR']
        if mode == 'cleaning':
            # faster rate than training mode - first, infuse 10.0ml, then withdraw.
            params = ['15.0', '500.0', '1.0', 'INF']
            pump_commands = dict(zip(cmds, params))
        elif mode == 'cleaning_rev':
            # reverse, from infuse, now WITHDRAW same amt...
            params = ['15.0', '500.0', '1.0', 'WDR']
            pump_commands = dict(zip(cmds, params))

        elif mode == 'training':
            params = ['15.0', '100.0', '0.02', 'INF'] # default
            pump_commands = dict(zip(cmds, params))
        return pump_commands

    def run_commands(self, pumpID, commandset, ncycles=1, npumps=1):
        try:
            print "Running commands to pump network..."
            print "commands: ", commandset
            status = self.call_and_response('%02i\r' % pumpID)
            while not 'S' in status:
                status = self.call_and_response('%02i\r' % pumpID)

            print "SENDING commandset..."  
            for i, cmd in enumerate(commandset.keys()):
                print cmd
                # right now, this sends 1 command to 1 pump at a time...
                if npumps == 1:
                    reply = self.call_and_response('%02i %s %s\r' \
                                % (pumpID, cmd, commandset[cmd]), nbytes=5)
                    print reply
                elif npumps > 1:
                    for p in range(1, npumps+1):
                        status = self.call_and_response('%02i\r' % p)
                        while not 'S' in status:
                            status = self.call_and_response('%02i\r' % p)
                        reply = self.call_and_response('%02i %s %s\r' \
                                    % (p, cmd, commandset[cmd]), nbytes=5)
                        print reply

            print "Now, RUNNING commandset..."  
            if npumps == 1:
                runreply = self.call_and_response('%02i RUN\r' % pumpID, nbytes=5)
            elif npumps == 2:
                for p in range(1, npumps+1):
                    status = self.call_and_response('%02i\r' % p)
                    while not 'S' in status:
                        status = self.call_and_response('%02i\r' % p)
                    print "all good, pump %i" % p
                runreply = self.call_and_read('*RUN\r', nbytes=2)
                print runreply
            print "Completed cycle." 
        except socket.error, (value, message):
            print "READ error val: %s" % value
            print "READ error msg: %s" % message


    def run_commandset(self, pumpID, commandset, ncycles=1, npumps=1): # commandset is a dict (pump_commands):
    
        print "Running commands to pump network..."
        print "commands: ", commandset

        try:    
            for n in range(ncycles):
                status = self.call_and_response('%02i\r' % pumpID)
                while not 'S' in status:
                    status = self.call_and_response('%02i\r' % pumpID)

                print "Starting CYCLE: %i" % n
                for i, cmd in enumerate(commandset.keys()):
                    print cmd
                    # right now, this sends 1 command to 1 pump at a time...
                    for p in range(1, npumps+1):
                        reply = self.call_and_response('%02i %s %s\r' \
                                    % (p, cmd, commandset[cmd]), nbytes=5)
                        print reply

                print "Now, RUNNING commandset, for cycle: %i" % n
                if n == 0: # first cycle, or only 1 cycle
                    if npumps == 1:
                        runreply = self.call_and_response('%02i RUN\r' % pumpID, nbytes=5)
                    elif npumps == 2:
                        # self.write_then_read('01 ADR DUAL\r')
                        runreply = self.call_and_response('*RUN\r', nbytes=5)
                        # self.write_then_read('* ADR 01\r')
                    print "Completed first cycle."
                elif n > 0:
                    # print 'got to next cycle: cycle %i' % n
                    # DON'T SEND THE NEXT "RUN" command until pump done with first "run"
                    # if 'I' in runreply:
                    # status = self.call_and_response('%02i\r' % pumpID)
                    # while not 'S' in status:
                    #     status = self.call_and_response('%02i\r' % pumpID)

                    if npumps == 1:
                        runreply = self.call_and_response('%02i RUN\r' % pumpID, nbytes=5)
                    elif npumps == 2:
                        # self.write_then_read('01 ADR DUAL\r')
                        runreply = self.call_and_response('*RUN\r', nbytes=5)
                        # self.write_then_read('* ADR 01\r')
                    print "Completed CYCLE NO: %i" % n
        except socket.error, (value, message):
            print "READ error val: %s" % value
            print "READ error msg: %s" % message


        return runreply
        print "Successful command run."

    # other commnds of interest (for pump network):  
    
    # address:  ADR [<address(0-99)>],[DUAL|RECP] -- DUAL for running same commands to both connected pumps 
    # -- see Sect.8.5.5 System Commands in manual for details on this mode...
    
    # command burst:  <n><command>* -- <n> = pump address (0-9), must be in pump network; then carriage return.
    # -- ex, change rates for pumps 0, 1, and 2 --  '0 RAT 100* 1 RAT 250* 2 RAT 375*\r'

    # volume dispensed: DIS -- just queries, returns: I<float> W<float> <vol units>, good for how much liquid dispensed!
    # clear volume dispensd:  CLD {INF|WIDR} -- sets to 0.


def set_pump_network(setupID, pumpID, ipAddress, port, npumps=1):
    """set a set of commands for a pump or pump network

    ***NOT SURE YET IF CAN RUN MORE THAN ONE SETUP AT TIME 
        -- check "network command burst" specs... 

    setupID : int
        setup with pumps to control

    pumpID : int
        each setup has two pumps, 1 (left) or 2 (right)

    ipAddress : str
        (see IPSerial)

    port : int
        (see IPSerial)
    """
    print "Setting up commands for pump network:  setup %i, pump %02i..." \
                % (setupID, pumpID)
    n = NE500Network(ipAddress, port)
    n.verbose = 0

    def set_commandset(mode): # q, t, or c.
        """return 0 to continue, else exit"""
        if mode == '':
            return 0
        m = mode[0]
        if m == 'q' or m == 'Q':
            return 1
        elif m == 't' or m == 'T':

            # set training mode:
            print "Training mode ON"
            # get the command set...
            try:
                pump_commands = n.get_commandset('training')
                print "got commandset"
            except:
                print "Invalid entry, pump configuration not set. Try again."
                return 0

            # run command set:
            try:
                n.run_commands(pumpID, pump_commands, npumps=npumps)
                print "ran commandset"
            except socket.error, (value, message):
                print "READ error val: %s" % value
                print "READ error msg: %s" % message
                return 0

        elif m == 'c' or m == 'C':
            # set cleaning mode:
            print "Cleaning mode ON"
            print "How many cycles to run?"
            ncycles = int(raw_input())

            nphase = 0
            for i in range(ncycles):
                # get the command set...
                try:
                    if nphase == 0: 
                        print "Getting commandset for cleaning phase %i" % nphase
                        pump_commands = n.get_commandset('cleaning')
                        nphase = 1
                    elif nphase == 1:
                        print "Getting commandset for cleaning phase %i" % nphase
                        pump_commands = n.get_commandset('cleaning_rev')
                        nphase = 0
                    print "got commandset, for cycle: %i" % i

                # run command set:
                    print "Running commandset on pump: %i" % pumpID
                    if npumps == 1:
                        runreply = n.run_commands(pumpID, pump_commands, ncycles=ncycles, npumps=npumps)
                    elif npumps > 1:
                        runreply = n.run_commands(pumpID, pump_commands, ncycles=ncycles, npumps=npumps)

                except socket.error, (value, message):
                    print "READ error val: %s" % value
                    print "READ error msg: %s" % message
                    return 0

        else:
            print "Invalid command"
            return 0
        
        return pump_commands

    def print_commandset():
        print
        print "Enter pump network mode:"
        print " --"
        print "q: quit"
        print " --"
        print_configs()
        print

    def print_configs():
        pump_commands_training = n.get_commandset('training')
        pump_commands_cleaning = n.get_commandset('cleaning')
        print "t: train (current config): \n", pump_commands_training
        print "c: clean (current config): \n", pump_commands_cleaning

    while True:
        # set parameter/quit
        print_commandset()
        r = raw_input()
        pump_commands = set_commandset(r)
        didit = 1
        if didit == 1:
            break

    # n.disconnect()
    return pump_commands    
    # print "Pump network mode set."

def run_command_burst(commandset, setupID, ipAddress, port, pumps=[1,2]):
    """run 2 or more pumps simultaneously in a given network 

    commandset : dict (??)
        right now, dict returned from running set_command_set(mode)...
        can make into a zipped list?...

    setupID : int
        right now, this is just one setup...

    pumpts : list of int
        default is [1, 2] : [left, right]

    ipAddress : str 
        see IPSerial

    port : int
        see IPSerial
    """
    
    print "Running command burst to pump network..."
    n = NE500Network(ipAddress, port)

    # for pumps with secondary pump attached...
    n.write_then_read('* ADR DUAL\r')
    for i, cmd in enumerate(commandset.iterkeys()):
        n.write_then_read('* %s %s\r' % (cmd, commandset[cmd]))

    print "Commands in dual-mode finished running."
    n.write_then_read('* ADR %02f\r' % pumpID)


    # for all pumps in a network...
    for i, cmd in enumerate(commandset.iterkeys()):
        burst = ''
        for p in pumps:
            single = '%02f %s %s* ' % (p, cmd, commandset[cmd])
            burst = burst + single
        burst = burst + '\r'

        n.writen_then_read(burst)
        print "Ran command: %s, on all set pumps." % cmd

    print "All commands completed."


if __name__ == '__main__':

    pumps = {'left':1, 'right':2}
    setups = {'setup1.local':1, 'setup2.local':2, 'setup3.local':3, \
                'setup4.local':4, 'setup5.local':5, 'setup6.local':6, \
                'setup7.local':7, 'setup8.local':8, 'setup9.local':9}

    ipAddresses = {'setup1_serial.local':'192.168.0.2', \
                    'setup2_serial.local':'192.168.0.4', \
                    'setup3_serial.local':'192.168.0.6', \
                    'setup4_serial.local':'192.168.0.8', \
                    'setup5_serial.local':'192.168.0.10', \
                    'setup6_serial.local':'192.168.0.12', \
                    'setup7_serial.local':'192.168.0.14', \
                    'setup8_serial.local':'192.168.0.16', \
                    'setup9_serial.local':'192.168.0.18'}

    port = 100
    IPs = []
    for i, key in enumerate(sorted(ipAddresses.iterkeys())):
        IPs.append([i+1, key, ipAddresses[key]])
        # IPs = [[1, 'setup1_serial.local', '192.168.0.2'], 
        #           [2, 'setup2_serial.local', '192.168.0.4'],
        #           [3, 'setup3_serial.local', '192.168.0.6'], ...]

    print "What network mode would you like to run?"
    print " 1: run single pump"
    print " 2: run partiuclar setup(s), single or both pumps"
    print " 3: run simultaneously, particular setup(s), 1 pump" # or both?  FIX this...
    # print " 3: run all setups, 1 pump"
    # print " 4: run all setups, all pumps"
    
    runIndex = int(raw_input())
    if runIndex == 1:
        print "Which setup would you like to run?"
        print IPs
        setupID = int(raw_input())
        ipAddress = IPs[setupID-1][2] 
        print "Which pump? Left or Right: [1]/[2]"
        pumpID = int(raw_input())
        print "Running pump %02i, on setup%i, address %s..." \
                % (pumpID, setupID, ipAddress)

        commandset = set_pump_network(setupID, pumpID, ipAddress, port)
        # run_commandset(commandset, pumpID, ipAddress, port)

    elif runIndex == 2:
        print "How many setups are you running?"
        nsetups = int(raw_input())
        print "Enter the setup number(s): *NO spaces or commas*"
        print IPs
        setups = list(raw_input())
        setupIDs = []
        ipAddresses = []
        for setup in setups:
            sidx = int(setup)
            setupIDs.append(sidx)
            ipAddresses.append(IPs[sidx-1][2])
        print setupIDs

        print "How many pumps on setup?"
        npumps = int(raw_input())
        if npumps == 1:
            print "Which pump? Left / Right: [1]/[2]"
            pumpID = int(raw_input())
            for s, ip in zip(setupIDs, ipAddresses):
                print "Running pump %02i, on setup%i, address %s..." \
                        % (pumpID, s, ip)
                set_pump_network(s, pumpID, ip, port, npumps)
        elif npumps == 2:
            pumpID = 1
            for s, ip in zip(setupIDs, ipAddresses):
                print "Running BOTH pumps, on setup%i, address %s..." \
                        % (s, ip)
                set_pump_network(s, pumpID, ip, port, npumps)

    elif runIndex == 3:
        # get list of setups to be run
        # get pump 01, 02, or both
        # get list of CMDs and PARAMs
        # FOR-loop through [CMDS, PARAMS]:
        #       message of form: ('01 CMD PARAM* 02 CMD PARAM*\r')
        #       
        # ******FIND OUT IF EACH PUMP CAN HAVE DIFF ADDY....
        # OTHERWISE, have to run each setup separately, but can do both pumps 01-02 simultaneously!
        #
        print "fix this"