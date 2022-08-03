import os
import logging

'''Limited number of instances to launch per node'''
MAX_INSTANCES_PER_NODE = int(os.environ.get('MAX_INSTANCES_PER_NODE', 4))

if os.environ.get('DEBUG', None):
    logging.basicConfig(
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        level=logging.DEBUG)
