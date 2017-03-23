# -*- coding: utf-8 -*-

import logging
import logging.handlers
import sys

def initLogger():
    global logger 
    logger = logging.getLogger('distgear')
    logfile = 'distgear.log'
    loglevel = logging.INFO
    logger.setLevel(loglevel)
    #handler = logging.handlers.TimedRotatingFileHandler(logfile, when="midnight", backupCount=loglevel)
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(module)s %(funcName)s [%(lineno)d] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    #sys.stdout = RedirectLogger(logger, logging.INFO)
    #sys.stderr = RedirectLogger(logger, logging.ERROR)

class RedirectLogger(object):
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
    
    def write(self, message):
        #message = str(message)
        if message.rstrip() != "":
            self.logger.log(self.level, message.rstrip())

    def flush(self):
        for handler in self.logger.handlers:
            handler.flush()


# maybe this module will be import many times
# but it will be loaded only once according to python import policy
logger = None
initLogger()

