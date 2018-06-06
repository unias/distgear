#!/usr/bin/python3

import os, random
import netifaces

#from log import logger

def loadenv(configpath):
    configfile = open(configpath)
    #logger.info ("load environment from %s" % configpath)
    for line in configfile:
        line = line.strip()
        if line == '':
            continue
        keyvalue = line.split("=")
        if len(keyvalue) < 2:
            continue
        key = keyvalue[0].strip()
        value = keyvalue[1].strip()
        #logger.info ("load env and put env %s:%s" % (key, value))
        os.environ[key] = value
        
def gen_token():
    return str(random.randint(10000, 99999))+"-"+str(random.randint(10000, 99999))

def ip_to_int(addr):
    addr = addr.split('/')[0]
    [a, b, c, d] = addr.split('.')
    return (int(a)<<24) + (int(b)<<16) + (int(c)<<8) + int(d)

def int_to_ip(num):
    return str((num>>24)&255)+"."+str((num>>16)&255)+"."+str((num>>8)&255)+"."+str(num&255)

# getip : get ip from network interface
# ifname : name of network interface
def getip(ifname):
    if ifname not in netifaces.interfaces():
        return False # No such interface
    else:
        addrinfo = netifaces.ifaddresses(ifname)
        if 2 in addrinfo:
            return netifaces.ifaddresses(ifname)[2][0]['addr']
        else:
            return False # network interface is down


