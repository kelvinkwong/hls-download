#!/usr/bin/env python3

import sys
import ffmpegio
import logging

logging.basicConfig(level=logging.DEBUG)
fragment = sys.argv[1]
stream, fragment = ffmpegio.audio.read(fragment)
logging.debug(stream)
logging.debug(fragment)