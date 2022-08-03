import os
import socket

''' If running within docker, the host name must be pass as env var'''
HOSTNAME = os.environ.get('HOSTNAME', socket.gethostname())

''' Upload server URL'''
UPLOAD_SERVER = os.environ.get('UPLOAD_SERVER', 'inmdlx423as006')

'''Titan images pattern to search'''
TITAN_IMAGE_NAME_PATTERN = os.environ.get(
    'TITAN_IMAGE_NAME_PATTERN', 'cloud_android')

'''Cluster images pattern to search'''
CLUSTER_IMAGE_NAME_PATTERN = os.environ.get(
    'CLUSTER_IMAGE_NAME_PATTERN', 'cloud_cluster')

'''Type of image builds on remote repository
    REL - release
    DB - daily
    PREINT - preint'''
IMAGE_BUILD_TYPES = ['REL', 'DB', 'PREINT']

'''Registry path templates'''
CATALOG_URL_TEMPLATE = '{}/v2/_catalog'
IMAGE_URL_TEMPLATE = '{}/v2/{}/tags/list'

'''Remote registry path prefix to pull images'''
ARTIFACTORY_PATH = "artifactory-mb.harman.com:5036/"

'''Remote registry user for internal access'''
REGISTRY_USER = os.environ.get('REMOTE_REGISTRY_USER', 'svc_titanemu')

'''Remote registry user's password for internal access'''
REGISTRY_PASS = os.environ.get('REMOTE_REGISTRY_PASS', '')

'''Limited number of instances to launch per user'''
MAX_INSTANCES_PER_USER = os.environ.get('MAX_INSTANCES_PER_USER', 4)

'''Hour when the actualization local images job starts'''
SCHEDULER_JOB_HOUR = os.environ.get('SCHEDULER_JOB_HOUR', 3)

'''Minute when the actualization local images job starts'''
SCHEDULER_JOB_MINUTE = os.environ.get('SCHEDULER_JOB_MINUTE', 30)

'''Num of youngest images to show in list
   of remote images per each build category'''
NUM_OF_REMOTE_IMAGES_PER_CAT = os.environ.get(
    'NUM_OF_REMOTE_IMAGES_PER_CAT', 5)

'''Baseline for port ranging'''
GRPC_PORT_BASE = 8443
SHELL_PORT_BASE = 9555
TELNET_PORT_BASE = 10555

''' TURN configuration. Note that cloud setup requires TURN server to
    make it possible to establish WebRTC connections towards emulator.'''
TURN_EXTERNAL_IP = os.environ.get('TURN_EXTERNAL_IP')
TURN_ON = True if TURN_EXTERNAL_IP else False
TURN_PORT = 3478
TURN_USER = 'emulator'
TURN_PASSWORD = 'titan'
TURN_URL = 'turn:{}:{}'.format(TURN_EXTERNAL_IP, TURN_PORT)
TURN_SERVER_CDM = '--lt-cred-mech ' + \
                  '--user={}:{} '.format(TURN_USER, TURN_PASSWORD) + \
                  '--external-ip={} '.format(TURN_EXTERNAL_IP) + \
                  '--realm=titan.emulator.harman.realm.org'
TURN_EMU_CFG = 'printf {\"iceServers\":[{' + \
                   '\"urls\":\"{}\",'.format(TURN_URL) + \
                   '\"username\":\"{}\",'.format(TURN_USER) + \
                   '\"credential\":\"{}\"'.format(TURN_PASSWORD) + '}]}'

USBIP_RPC_URL = os.environ.get('USBIP_RPC_URL')

BASE_URL = 'unix://var/run/docker.sock'
