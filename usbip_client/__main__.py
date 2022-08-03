import os
import xmlrpc.server

from usbip_client import lsusb
from usbip_client import attach
from usbip_client import detach

USBIP_RPC_PORT = os.environ.get('USBIP_RPC_PORT', 8888)


if __name__ == '__main__':
    server = xmlrpc.server.SimpleXMLRPCServer(('0.0.0.0', USBIP_RPC_PORT))
    server.register_function(lsusb, 'lsusb')
    server.register_function(attach, 'attach')
    server.register_function(detach, 'detach')
    server.serve_forever()
