import socket
import logging
import subprocess
import os.path
import time
import re

USBIP_PORT = 3240
USBIP_CONN_TMO = 1  # seconds

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
logging.basicConfig(level=LOGLEVEL)

logger = logging.getLogger(__name__)


class usbip_client:
    '''Note: the client must be run with root privileges to properly retrieve
       info about usb devices and perform attach/detach'''
    @staticmethod
    def lsusb(remote_address=None):
        '''list available/attached usb devices'''
        result = []

        if remote_address is None:
            # list attached devices
            cmd = 'usbip port'
            out = subprocess.run(cmd, capture_output=True, shell=True).stdout
            logger.info(out)

            try:
                '''
                'usbip port' output format as per version (usbip-utils 2.0)

                Imported USB devices
                ====================
                Port 00: <Port in Use> at High Speed(480Mbps)
                       unknown vendor : unknown product (7392:a833)
                       3-1 -> usbip://127.0.0.1:3240/1-11
                           -> remote bus/dev 001/006
                Port 01: <Port in Use> at Full Speed(12Mbps)
                       unknown vendor : unknown product (0b05:17cb)
                       3-2 -> usbip://127.0.0.1:3240/1-12
                           -> remote bus/dev 001/007
                '''

                matches = re.findall(r'[\\\n]'
                                     r'.*\s(\d+):.*[\\\n]'
                                     r'.*\((\w+:\w+)\)[\\\n]'
                                     r'.*(\d+-\d+).*\/(\d.*):\d+'
                                     r'\/(\d+-\d+\.?\d*)',
                                     out.decode())

                for match in matches:
                    port, vid_pid, local_bus_id, remote_address, bus_id = match

                    sys_path = '/sys/bus/usb/devices/' + local_bus_id
                    busnum_path = sys_path + '/busnum'
                    devnum_path = sys_path + '/devnum'

                    if os.path.isfile(busnum_path) and \
                            os.path.isfile(devnum_path):
                        with open(busnum_path) as busnum_file:
                            busnum = busnum_file.read()[:-1]
                        with open(devnum_path) as devnum_file:
                            devnum = devnum_file.read()[:-1]
                        dev_path = \
                            '/dev/bus/usb/' + busnum.zfill(3) + \
                            '/' + devnum.zfill(3)
                    else:
                        dev_path = ''

                    device = {'port': int(port),
                              'remote_address': remote_address,
                              'bus_id': bus_id,
                              'vid_pid': vid_pid,
                              'dev_path': dev_path}

                    logger.info('found attached usb device {}'.format(device))
                    result += [device]
            except Exception:
                pass
            return result

        # else list not-attached remote devices
        try:
            # try to connect to usbipd firstly to see
            # if it running, othersize usbip client migth
            # hang for several seconds
            skt = socket.socket()
            skt.settimeout(USBIP_CONN_TMO)
            skt.connect((remote_address, USBIP_PORT))
            skt.close()

            cmd = 'usbip list -r {}'.format(remote_address)
            out = subprocess.run(cmd, capture_output=True, shell=True).stdout
            logger.info(out)

            '''
            'usbip list' output format as per version (usbip-utils 2.0)

            Exportable USB devices
            ======================
             - 127.0.0.1
                   1-12: unknown vendor : unknown product (0b05:17cb)
                       : /sys/devices/pci0000:00/0000:00:14.0/usb1/1-12
                       : unknown class / unknown subclass / unknown protocol (ff/01/01)  # nopep8

                   1-11: unknown vendor : unknown product (7392:a833)
                       : /sys/devices/pci0000:00/0000:00:14.0/usb1/1-11
                       : (Defined at Interface level) (00/00/00)

            '''

            matches = re.findall(
                r'(\d+-\d+\.?\d*):.*\((\w+:\w+)\)', out.decode())
            for bus_id, vid_pid in matches:
                logger.info('found remote usb device at {}, '
                            'bus_id {}, vid:pid {}'
                            ''.format(remote_address, bus_id, vid_pid))

                result += [{'remote_address': str(remote_address),
                            'bus_id': bus_id, 'vid_pid': vid_pid}]
        except Exception as e:
            pass

        return result

    @staticmethod
    def attach(remote_address, bus_id):
        '''attaches remote usb device'''
        if remote_address is None or bus_id is None:
            return

        cmd = 'usbip attach -r {} -b {}'.format(remote_address, bus_id)
        subprocess.run(cmd, capture_output=True, shell=True)

        '''
            usbip tool seems to be working asyncly.
            once attach command is issued, the actual device
            appears in the list of attached devices after some tmo
        '''
        tmo = 0.5
        attempts = 10
        attached_device = []
        while len(attached_device) == 0 and attempts > 0:
            devices = __class__.lsusb()
            attached_device = [device for device in devices if
                               device['remote_address'] == str(remote_address)
                               and device['bus_id'] == bus_id]
            attempts -= 1
            time.sleep(tmo)

        return attached_device[0]

    @staticmethod
    def detach(port):
        '''detaches remote usb device'''
        if port is None:
            return True

        cmd = 'usbip detach -p {}'.format(port)
        subprocess.run(cmd, capture_output=True, shell=True)
        return True
