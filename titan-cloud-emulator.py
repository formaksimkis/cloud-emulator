#!/usr/bin/python3

import os
import logging
import argparse
import emulator
import ipaddress

from emulator import TITAN_IMAGE_NAME_PATTERN, CLUSTER_IMAGE_NAME_PATTERN
from node.master import PoolMananger

# TODO: Once /images and /instaces api calls are implemented
#       on backend, this script can request wanted info via HTTP.
#       So far, the script should run inside backend container and
#       it will in fact run backend routines in separate python process
#       which is still working approach while the backend design is stateless.

DOCKER_REGISTRY = 'https://artifactory-mb.harman.com:443' \
    '/artifactory/api/docker/platform_docker_registry'
FLASK_APP = os.environ.get('FLASK_APP', '')
POOL_NODES = os.environ.get('POOL_NODES', None)
POOL_NODES = POOL_NODES.split(',') if POOL_NODES else []
cluster = PoolMananger(POOL_NODES)


def clusterwide(func):
    def wrapper(*args, **kwargs):
        node_id = vars(args[0]).get('node_id')
        if node_id is not None:
            args[0].iface = args[0].iface.__nodes__().get(node_id)
            if args[0].iface is None:
                print(f'No node with id {node_id} exists')
                return
        cluster_ext_info = vars(args[0]).get('cluster_ext_info')
        if cluster_ext_info:
            nodes_fn = getattr(args[0].iface, '__nodes__')
            args[0].cluster_ext_info = [
                getattr(node, func.__name__)() for node in nodes_fn().values()]
        return func(*args, **kwargs)
    return wrapper


@clusterwide
def list_images(args):
    '''list available images'''
    images = args.iface.list_images(
        args.registry, TITAN_IMAGE_NAME_PATTERN)
    images.update(args.iface.list_images(
        args.registry, CLUSTER_IMAGE_NAME_PATTERN))
    print(' {:20} {:10} {:50} {}'.format(
        'VERSION', 'API Level', 'IMAGE NAME', 'LOCAL/REMOTE'))
    for image, sha in images.items():
        view = emulator.describe_image(image, sha)
        availabilty = 'Remote' if view['sha'] == 'Remote' else 'Local'
        if vars(args).get('cluster_ext_info'):
            per_node_avail = [
                '+' if view['image_name'] in node_images.keys()
                else '-' for node_images in args.cluster_ext_info]
            availabilty = f'{availabilty} ({"".join(per_node_avail)})'
        print(' {:20} {:10} {:50} {}'.format(
            'Android ' + view['version'],
            view['api'],
            view['image_name'],
            availabilty))


@clusterwide
def list_containers(args):
    '''list running containers'''
    instances = args.iface.list_containers()
    print(' {}  {:5}  {:40} {:40} {:40} {:30} {:30} {:30} {:5}'.format(
        'H', 'ID', 'IMAGE', 'LINK', 'ADB', 'TELNET', 'DEVICES', 'CONTAINTERS',
        'NODE' if vars(args).get('cluster_ext_info') else ''))
    for ident in instances:
        print('[{}] #{:<5} {:40} {:40} {:40} {:30} {:30} {:30} {:<5}'.format(
            '+' if instances[ident]['healthy'] else '-',
            ident,
            instances[ident]['image_name'][:40],
            instances[ident]['link'][:40],
            instances[ident]['adb'][:40],
            instances[ident]['telnet'][:30],
            instances[ident]['devices'][:30],
            instances[ident]['childs'],
            ident//100 if vars(args).get('cluster_ext_info') else ''))


@clusterwide
def start_image(args):
    '''launches an instance'''
    devices = []
    if args.devices is not None:
        # TODO: usb is supported on master only so far
        args.devices = args.devices.split(',')
        attached_devices = emulator.lsusb()
        devices = [{'path': device['dev_path'],
                    'vid_pid': device['vid_pid']}
                   for device in attached_devices
                   if str(device['port']) in args.devices]
    prefix = args.prefix + '_' if args.prefix else ''
    ident = args.iface.start_image(args.image_name, devices, prefix)
    if ident is None:
        print('Max number of instances reached')


@clusterwide
def stop_container(args):
    '''stops running instance'''
    args.iface.stop_container(args.id)


def lsusb(args):
    '''list available/attached usb devices'''
    devices = emulator.lsusb(args.remote_address)
    if args.remote_address:
        print(' {:15} {:15} {}'.format(
            'REMOTE IP',
            'BUS ID',
            'VID:PID'))
        for device in devices:
            print(' {:15} {:15} {}'.format(
                device['remote_address'],
                device['bus_id'],
                device['vid_pid']))
    else:
        print(' {:10} {:20} {:20} {:20} {}'.format(
            'PORT#',
            'REMOTE IP',
            'REMOTE BUS ID',
            'VID:PID',
            'DEV PATH'))
        for device in devices:
            print(' {:10} {:20} {:20} {:20} {}'.format(
                str(device['port']),
                device['remote_address'],
                device['bus_id'],
                device['vid_pid'],
                device['dev_path']))


@clusterwide
def pull(args):
    '''pulls an image from remote repo'''
    for state in args.iface.pull(args.image_name, registry=args.registry):
        print([f'{args.image_name}: {k} {v}%   ' for k, v in state.items()][0],
              end='\n' if 'Complete' in state.keys() else '\r')


@clusterwide
def drop(args):
    '''drops local image'''
    if not args.iface.delete_image(args.image_name):
        print('Image not deleted (occupied by running instance?)')


def attach(args):
    '''attaches remote usb device'''
    emulator.attach(remote_address=args.remote_address, bus_id=args.bus_id)


def detach(args):
    '''detaches remote usb device'''
    emulator.detach(port=args.port)


def nodes(args):
    '''lists cluster nodes'''
    print(' {:10} {:10} {:40} {:10}'.format(
        'NODE#',
        'ROLE',
        'URL',
        'STATE'))
    if FLASK_APP == 'backend':
        for node in args.iface.__nodes_info__():
            print(' {:<10} {:10} {:40} {:10}'.format(
                node['id'],
                node['role'].upper(),
                node['url'],
                node['state']))


def sync(args):
    for value in args.iface.sync(DOCKER_REGISTRY, TITAN_IMAGE_NAME_PATTERN):
        print(f'{value}          ', end='\n' if 'done' in value else '\r')
    for value in args.iface.sync(DOCKER_REGISTRY, CLUSTER_IMAGE_NAME_PATTERN):
        print(f'{value}          ', end='\n' if 'done' in value else '\r')


def add_node_parsers(subparsers, iface=emulator, cluster_ext_info=False):
    ''' Appends parser node related parsers to specfic subparser '''
    list_parser = subparsers.add_parser('ls', help='list available images')
    list_parser.add_argument(
        '-r', '--registry', type=str, nargs='?',
        default=None, const=DOCKER_REGISTRY,
        help=f"url of remote registry, default is {DOCKER_REGISTRY}")

    list_parser.set_defaults(
        func=list_images, iface=iface, cluster_ext_info=cluster_ext_info)

    ps_parser = subparsers.add_parser('ps', help='list running images')
    ps_parser.set_defaults(
        func=list_containers, iface=iface, cluster_ext_info=cluster_ext_info)

    start_parser = subparsers.add_parser('start', help='launch an image')
    start_parser.add_argument('image_name', help='image name to launch')
    start_parser.add_argument(
        '--devices',
        help='list of usbip port numbers of usb devces to pass '
             'to the container (separated by comma)')
    start_parser.add_argument(
        '--prefix',
        help='prefix appended to all container names stared for this instance')
    start_parser.set_defaults(
        func=start_image, iface=iface, cluster_ext_info=False)

    stop_parser = subparsers.add_parser('stop', help='stop running image')
    stop_parser.add_argument(
        'id', type=int, help='instance id from ps command')
    stop_parser.set_defaults(
        func=stop_container, iface=iface, cluster_ext_info=False)

    pull_parser = subparsers.add_parser(
        'pull', help='pull image from remote repo')
    pull_parser.add_argument(
        'image_name', help='name of the image in lower case')
    pull_parser.add_argument(
        '-r', '--registry', type=str,
        default=DOCKER_REGISTRY,
        help=f"url of remote registry, default is {DOCKER_REGISTRY}")
    pull_parser.set_defaults(
        func=pull, iface=iface, cluster_ext_info=False)

    drop_parser = subparsers.add_parser(
        'drop', help='drop local image')
    drop_parser.add_argument(
        'image_name', help='name of the image in lower case')
    drop_parser.set_defaults(
        func=drop, iface=iface, cluster_ext_info=False)

    lsusb_parser = subparsers.add_parser(
        'lsusb', help='list available/attached usb devices')
    lsusb_parser.add_argument(
        'remote_address', nargs='?', type=ipaddress.ip_address,
        default=None, help='ip address of remote client machine')
    lsusb_parser.set_defaults(func=lsusb)

    attach_parser = subparsers.add_parser(
        'attach', help='attach remote usb device')
    attach_parser.add_argument(
        'remote_address', type=ipaddress.ip_address,
        help='address of remote machine')
    attach_parser.add_argument('bus_id', help='bus id of remote device')
    attach_parser.set_defaults(func=attach)

    detach_parser = subparsers.add_parser(
        'detach', help='detach remote device')
    detach_parser.add_argument(
        'port', type=int, help='port id of attached device')
    detach_parser.set_defaults(func=detach)


def main():
    '''Entry point that parses the arguments,
       and invokes the proper functions.'''
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose", dest="verbose",
                        action="store_true", help="set verbose logging")

    subparsers = parser.add_subparsers()
    add_node_parsers(subparsers, iface=emulator)

    cluster_parser = subparsers.add_parser(
        'cluster', help='cluster info (master only)')
    cluster_subparsers = cluster_parser.add_subparsers()

    nodes_parser = cluster_subparsers.add_parser(
        'nodes', help='list nodes')
    nodes_parser.set_defaults(func=nodes, iface=cluster)

    sync_parser = cluster_subparsers.add_parser(
        'sync', help='sync images in cluster (master is a reference)')
    sync_parser.set_defaults(func=sync, iface=cluster)

    node_parser = cluster_subparsers.add_parser(
        'node', help='run command on node')
    node_parser.add_argument('node_id', type=int, help='node id')
    node_subparsers = node_parser.add_subparsers()
    add_node_parsers(node_subparsers, iface=cluster)

    add_node_parsers(cluster_subparsers, iface=cluster, cluster_ext_info=True)

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.ERROR
    logging.basicConfig(
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        level=log_level, force=True)

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
