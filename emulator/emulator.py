import re

import requests
import logging
import docker
import xmlrpc.client

from emulator import HOSTNAME
from emulator import TITAN_IMAGE_NAME_PATTERN
from emulator import CLUSTER_IMAGE_NAME_PATTERN
from emulator import CATALOG_URL_TEMPLATE
from emulator import IMAGE_URL_TEMPLATE
from emulator import GRPC_PORT_BASE
from emulator import SHELL_PORT_BASE
from emulator import TELNET_PORT_BASE
from emulator import TURN_ON
from emulator import TURN_SERVER_CDM
from emulator import TURN_EMU_CFG
from emulator import USBIP_RPC_URL
from emulator import REGISTRY_USER
from emulator import REGISTRY_PASS
from emulator import ARTIFACTORY_PATH
from emulator import BASE_URL
from usbip_client import usbip_client
from decimal import Decimal
from threading import Lock


logger = logging.getLogger(__name__)
usbip_client_proxy = usbip_client if USBIP_RPC_URL is None \
    else xmlrpc.client.ServerProxy(USBIP_RPC_URL, allow_none=True)

emulator_global_lock = Lock()


class emulator:
    @staticmethod
    def describe_image(image_name, sha):
        api = '<unknown>'
        version = '<unknown>'
        if TITAN_IMAGE_NAME_PATTERN in image_name:
            search_result = re.search(r'\d+', image_name)
            if search_result is not None:
                version = int(search_result.group(0))
                if version > 7:
                    api = version + 19
        elif CLUSTER_IMAGE_NAME_PATTERN in image_name:
            api = '<unknown>'
            version = 'Cluster EA9'
        return {
            'version': str(version),
            'api': str(api),
            'image_name': str(image_name),
            'sha': str(sha)
        }

    @staticmethod
    def list_images(registry=None, name_pattern=TITAN_IMAGE_NAME_PATTERN):
        '''returns the merged result dict of local and remote images
            structure of dict:
            _________________________
            |   str key: str value  |
            |image name: sha        | - for local instances
            |image name: "Remote"   | - for remote instances (don't have sha)
            |_______________________|
            If the local image name coincides with the remote one
            this image will be placed only once in the result dict
            only as a local instance'''
        client = docker.DockerClient(BASE_URL)
        lokal_images = client.images.list()
        result_images = dict()
        lokal_images = [i for i in lokal_images if
                        name_pattern in ''.join(i.tags)]
        for local in lokal_images:
            for name_local in local.tags:
                name_local = __class__.__to_short_image_name(name_local)
                result_images[name_local] = local.short_id
                logger.info('LOCAL: {}'.format(name_local))
        for path in emulator.__remote_images_paths_list(
                registry, name_pattern):
            short_name = __class__.__to_short_image_name(path)
            if short_name not in result_images.keys():
                result_images[short_name] = 'Remote'
        return result_images

    @staticmethod
    def list_containers():
        '''lists running instances'''

        client = docker.DockerClient(BASE_URL)
        containers = client.containers.list()
        cont_names = [c.name for c in containers
                      if 'emulator_titan' in c.name]
        clust_cont_names = [c.name for c in containers
                            if 'emulator_cluster' in c.name]
        cont_names.extend(clust_cont_names)

        ids = sorted(set([cont[-1] for cont in cont_names]))

        instances = {}
        for ident in ids:
            childs = [cont for cont in cont_names if cont[-1] == ident]

            healthy = False
            devices = []

            if 'titan' in ''.join(childs):
                healthy = True
                titan = [cont for cont in containers if
                         'titan' in cont.name and cont.name in childs][0]
                image_name = titan.attrs['Config']['Image']
                short_name = __class__.__to_short_image_name(image_name)
                networks = titan.attrs['NetworkSettings']['Networks']
                net_name = list(networks.keys())[0]
                devices = titan.attrs['HostConfig']['Devices'][1:]
                devices = [dev['PathOnHost'] for dev in devices]
                attached_devices = __class__.lsusb()
                devices = [dev for dev in attached_devices
                           if dev['dev_path'] in devices]
                devices = ['{}@{}/{}'.format(
                    dev['vid_pid'],
                    dev['remote_address'],
                    dev['bus_id']) for dev in devices]
                shell_cmd = 'adb connect {}:{}'.format(HOSTNAME,
                                                       SHELL_PORT_BASE +
                                                       int(ident))
                telnet_cmd = 'telnet {} {}'.format(HOSTNAME,
                                                   TELNET_PORT_BASE +
                                                   int(ident))
                link = 'http://{}/instance/{}'.format(HOSTNAME.lower(), ident)

            elif 'cluster' in ''.join(childs):
                healthy = True
                cluster = [cont for cont in containers if
                           'cluster' in cont.name and cont.name in childs][0]
                image_name = cluster.attrs['Config']['Image']
                short_name = __class__.__to_short_image_name(image_name)
                networks = cluster.attrs['NetworkSettings']['Networks']
                net_name = list(networks.keys())[0]
                shell_cmd = 'ssh  root@{} -p {}'.format(HOSTNAME,
                                                        SHELL_PORT_BASE +
                                                        int(ident))
                telnet_cmd = ''
                link = 'http://{}:{}'.format(HOSTNAME.lower(),
                                             GRPC_PORT_BASE + int(ident))
            else:
                short_name = '<unknown>'

            instances[int(ident)] = {
                'id': ident,
                'image_name': short_name,
                'healthy': healthy,
                'link': link,
                'adb': shell_cmd,
                'net_name': net_name,
                'telnet': telnet_cmd,
                'hostname': HOSTNAME.lower(),
                'port': GRPC_PORT_BASE + int(ident),
                'devices': ' '.join(devices),
                'childs': ' '.join(childs)}
        return instances

    @staticmethod
    def __get_next_instance_config():
        '''looks for already running instances and
            returns an id for the next instance'''

        containers = __class__.list_containers()
        keys = list(containers.keys())
        for ix in range(max([0] + keys) + 2):  # +2 to have latest always free
            if ix not in keys:
                break
        return (ix, GRPC_PORT_BASE + ix,
                SHELL_PORT_BASE + ix, TELNET_PORT_BASE + ix)

    @staticmethod
    def start_image(image_name, devices=[], prefix='', cluster_name=''):
        '''launches an instance
           input: image_name - name of docker image
                  devices - list of dicts of format
                      {'path': <local path in /dev>,
                       'vid_pid': <vid:pid>}
                  prefix - prefix used in container names to be launched
                  cluster_name = name of cluster docker image
        '''
        if not image_name:
            logger.warning('no image_name provided')
            return

        image_name = __class__.__to_full_image_name(image_name)
        logger.info('image full name {}'.format(image_name))

        client = docker.APIClient(BASE_URL)

        images = [image_name]

        if TURN_ON:
            images += ['instrumentisto/coturn']

        logger.info('clister name {}'.format(cluster_name))
        if cluster_name != '':
            cluster_name = __class__.__to_full_image_name(cluster_name)
            images += [cluster_name]

        for image in images:
            if not client.images(image):
                logger.error('image {} not found'.format(image))
                return

        with emulator_global_lock:
            instance_config = __class__.__get_next_instance_config()
            instance_id, instance_port, shell_port, \
                telnet_port = instance_config

            logger.info('starting instance #{} on port {}, prefix {}'.format(
                instance_id, instance_port, prefix))

            net_name = '{}emulator_envoymesh_{}'.format(prefix, instance_id)
            if not [net for net in client.networks(net_name)
                    if net['Name'] == net_name]:
                client.create_network(net_name)
                logger.info('created network {}'.format(net_name))

            if TURN_ON and 'coturn' not in ' '.join(
                    [cont['Image'] for cont in client.containers()]):
                logger.info('TURN_SERVER_CDM {}'.format(TURN_SERVER_CDM))
                coturn = client.create_container(
                    name='coturn',
                    image='instrumentisto/coturn:latest',
                    detach=True,
                    command=TURN_SERVER_CDM,
                    host_config=client.create_host_config(
                        auto_remove=True,
                        network_mode='host'))

                logger.info('created coturn {}'.format(coturn))
                client.start(container=coturn.get('Id'))

            environment = {}
            if TURN_ON:
                environment['TURN'] = TURN_EMU_CFG
                logger.info('TURN_EMU_CFG {}'.format(TURN_EMU_CFG))

            devpaths = []
            if devices != []:
                devpaths = [device['path'] for device in devices]
                devcfg = '-device qemu-xhci,id=xhci '
                for device in devices:
                    devcfg += '-device usb-host,' \
                              'vendorid=0x{},productid=0x{} ' \
                              ''.format(*device['vid_pid'].split(':'))
                environment['QEMU_EXT_PARAMS'] = devcfg
                logger.info('QEMU_EXT_PARAMS {}'.format(devcfg))

            if TITAN_IMAGE_NAME_PATTERN in image_name:
                emulator = client.create_container(
                    name='{}emulator_titan_{}'.format(prefix, instance_id),
                    image=image_name,
                    detach=True,
                    networking_config=client.create_networking_config(
                        endpoints_config={
                            net_name: client.create_endpoint_config(
                                aliases=['emulator'])}),
                    environment=environment,
                    ports=[8554, 5555, 5554],
                    host_config=client.create_host_config(
                        cap_add=["NET_ADMIN"],
                        devices=['/dev/kvm:/dev/kvm',
                                 '/dev/net/tun:/dev/net/tun'] + devpaths,
                        shm_size='128M',
                        port_bindings={5555: shell_port,
                                       5554: telnet_port,
                                       8554: instance_port},
                        auto_remove=True))
                logger.info('created emulator {}'.format(emulator))
                client.start(container=emulator.get('Id'))

                # telnet session requires auth via token kept inside
                # the container, to not complicate the things for now
                # with token exposing in the UI, just remove the tocken
                # and allowing non-auth access
                client.exec_start(
                    client.exec_create(
                        emulator.get('Id'),
                        'cp /dev/null /root/.emulator_console_auth_token'))

            cl_inst_id = 0

            if (CLUSTER_IMAGE_NAME_PATTERN in image_name) or \
                    (CLUSTER_IMAGE_NAME_PATTERN in cluster_name):
                if cluster_name != '':
                    cl_instance_config = __class__.__get_next_instance_config()
                    cl_inst_id, cl_instance_port, cl_shell_port, \
                        cl_telnet_port = cl_instance_config
                    cl_image_name = cluster_name
                else:
                    cl_inst_id, cl_instance_port, cl_shell_port, \
                        cl_telnet_port = instance_config
                    cl_image_name = image_name

                logger.info(
                    'starting cluster instance #{} on port {}, \
                        prefix {}'.format(
                            cl_inst_id, cl_instance_port, prefix))

                cluster = client.create_container(
                    name='{}emulator_cluster_{}'.format(prefix, cl_inst_id),
                    image=cl_image_name,
                    detach=True,
                    stdin_open=True, tty=True,
                    networking_config=client.create_networking_config(
                        endpoints_config={
                            net_name: client.create_endpoint_config(
                                aliases=['cluster'])}),
                    ports=[8022, 8080],
                    host_config=client.create_host_config(
                        cap_add=["NET_ADMIN"],
                        devices=['/dev/kvm:/dev/kvm',
                                 '/dev/net/tun:/dev/net/tun'] + devpaths,
                        shm_size='128M',
                        port_bindings={
                            8022: cl_shell_port, 8080: cl_instance_port},
                        auto_remove=True))
                logger.info('created emulator {}'.format(cluster))
                client.start(container=cluster.get('Id'))

        logger.info('running instance_id = {}, cluster_id = {}'.format(
            instance_id, cl_inst_id))
        if cluster_name != '':
            return instance_id, cl_inst_id
        return instance_id

    @staticmethod
    def stop_container(inst_id):
        '''stops running instance'''

        containers = __class__.list_containers()

        if inst_id is None:
            logger.warning('no id in provided')
            return

        inst = containers.get(inst_id)
        if not inst:
            logger.info('no suitable instance found for id {}'.format(inst_id))
            return

        logger.info('found instance {}'.format(inst))
        client = docker.DockerClient(BASE_URL)

        for child in inst['childs'].split():
            cont = client.containers.get(child)
            networks = cont.attrs['NetworkSettings']['Networks']

            cont.stop()
            logger.info('stopped {} '.format(child))

            for net_name, net in networks.items():
                client.networks.get(net['NetworkID']).remove()
                logger.info(f'removed net {net_name}')

        containers = __class__.list_containers()
        if TURN_ON and len(containers) == 0:
            try:
                client.containers.get('coturn').stop()
                logger.info('stopped coturn')
            except Exception:
                pass

    @staticmethod
    def lsusb(remote_address=None):
        '''list available/attached usb devices'''
        try:
            return usbip_client_proxy.lsusb(remote_address)
        except Exception:
            pass
        return []

    @staticmethod
    def attach(remote_address, bus_id):
        '''attaches remote usb device'''
        try:
            return usbip_client_proxy.attach(remote_address, bus_id)
        except Exception:
            pass
        return None

    @staticmethod
    def detach(port):
        '''detaches remote usb device'''
        try:
            return usbip_client_proxy.detach(port)
        except Exception:
            pass

    @staticmethod
    def pull(image_name, registry, pattern=TITAN_IMAGE_NAME_PATTERN):
        '''pull an image from remote repository
            input:
            image_name - short name of docker image
            registry - remote repository where need to find image
            pattern - pattern name for search image (see constants.py patterns)
            image_path - full path of remote image was found by short name
            mass_gb - dict of GB blobs,
                      which the image consists of (need to find the biggest)
            mass_mb - dict of MB blobs, which the image consists of,
                      if GB blobs are absent (need to find the biggest)
            max_value - max sized blob of downloading image,
                                 which is used for evaluating percent
            downloading_progress - dict to send pair 'State' and 'Percent'
                             for displaying download progress
            extracting_progress - dict to send pair 'State' and 'Percent'
                             for displaying extract progress
            complete_progress - dict to send pair 'State' and 'Percent'
                             for displaying complete progress
        '''

        # Start to login as an internal user
        client = docker.APIClient(base_url=BASE_URL)
        authorized = ""
        attempt = 5
        while authorized != 'Login Succeeded' and attempt >= 0:
            authorized = client.login(username=REGISTRY_USER,
                                      password=REGISTRY_PASS,
                                      registry=ARTIFACTORY_PATH,
                                      reauth=True).get('Status', "")
            attempt = attempt - 1

        image_path = emulator.__remote_images_paths_list(registry,
                                                         pattern,
                                                         image_name)
        if not image_path:
            logger.error('failed to find {} in remote registry {}'.
                         format(image_name, registry))
            return
        image_path = ARTIFACTORY_PATH + image_path
        mass_mb = dict()
        mass_gb = dict()
        steps_to_search = 200
        repeats_count = 0
        prev = 0
        downloading_progress = dict()
        extracting_progress = dict()
        complete_progress = dict()
        max_value = 0
        max_key = ''
        state = ''
        is_still_show_downloading = True
        for line in client.pull(repository=image_path,
                                stream=True,
                                decode=True):
            state = str(line.get('status', ''))
            for key, value in line.items():
                if str(key).__eq__('progress'):
                    if steps_to_search > 0:
                        key_value = str(value).split('/')[1]
                        if str(value[-2:]).__eq__('GB'):
                            mass_gb[key_value] = emulator.__get_total(value)
                            steps_to_search = 0
                        if str(value[-2:]).__eq__('MB'):
                            curr = emulator.__get_total(value)
                            mass_mb[key_value] = curr
                            if prev == curr:
                                if repeats_count < 10:
                                    repeats_count = repeats_count + 1
                                else:
                                    steps_to_search = 0
                            else:
                                repeats_count = 0
                            prev = curr
                        steps_to_search = steps_to_search - 1
                    else:
                        if mass_gb and max_value == 0:
                            values = list(mass_gb.values())
                            keys = list(mass_gb.keys())
                            max_value = max(values)
                            max_key = keys[values.index(max_value)]
                            break
                        else:
                            if mass_mb and max_value == 0:
                                values = list(mass_mb.values())
                                keys = list(mass_mb.keys())
                                max_value = max(values)
                                max_key = keys[values.index(max_value)]
                                break
                    find_str = str(value).split('/')[1]
                    if max_value != 0 and find_str.__eq__(max_key):
                        if is_still_show_downloading:
                            if state == 'Extracting':
                                is_still_show_downloading = False
                                downloading_progress['Downloading'] = 100
                                yield downloading_progress
                                break
                            current = emulator.__get_current(value)
                            total = emulator.__get_total(value)
                            download_percent = int(current / total * 100)
                            downloading_progress[state] = download_percent
                            yield downloading_progress
                        else:
                            if state == 'Extracting':
                                current = emulator.__get_current(value)
                                total = emulator.__get_total(value)
                                extract_percent = int(current / total * 100)
                                extracting_progress[state] = extract_percent
                                yield extracting_progress
        if 'Downloaded' in state or 'Image is up to date' in state:
            logger.info('the final state of downloading is: {}'.format(state))
            complete_progress['Complete'] = 100
        else:
            logger.error('the final state of downloading is Failure!')
            complete_progress['Failure'] = 0
        yield complete_progress

    @staticmethod
    def __get_total(value_str):
        '''return total value of downloading process'''
        sub_find = str(value_str).split('/')[1]
        value = 0
        if str(sub_find[-2:]).__eq__('GB'):
            value = Decimal(sub_find[:-2]) * 1024
        if str(sub_find[-2:]).__eq__('MB'):
            value = Decimal(sub_find[:-2])
        return value

    @staticmethod
    def __get_current(value_str):
        '''return current value of downloading process'''
        sub_find = str(value_str).split(']')[1].split('/')[0]
        value = 0
        if str(sub_find[-2:]).__eq__('GB'):
            value = Decimal(sub_find[1:-2]) * 1024
        if str(sub_find[-2:]).__eq__('MB'):
            value = Decimal(sub_find[1:-2])
        return value

    @staticmethod
    def __to_short_image_name(image_name):
        '''get from the whole URL of image name only
           the image name without path and tag'''
        return image_name.split('/')[-1].split(':')[0]

    @staticmethod
    def __to_full_image_name(image_name):
        ''' obtains full image name by its short name '''
        client = docker.DockerClient(BASE_URL)
        images = client.images.list()
        for image in images:
            if image.tags and image_name.lower() in image.tags[0]:
                return image.tags[0]
        return None

    @staticmethod
    def __remote_images_paths_list(registry,
                                   pattern=TITAN_IMAGE_NAME_PATTERN,
                                   image_name=None):
        '''return path(s) list of remote image(s)
            1) If image_name is empty it returns all the images paths
               from the registry match up with pattern
            2) If image_name is not empty it returns the list
               with only one path which matches up with image_name and pattern
            input:
            registry - remote repository where need to find image
            pattern - type of image name to search for paths
            image_name - image name for searching path for it'''
        remotes_list = []
        if registry:
            try:
                url = CATALOG_URL_TEMPLATE.format(registry)
                req = requests.get(
                    url=url,
                    auth=(REGISTRY_USER, REGISTRY_PASS))
                remotes = [r for r in req.json()['repositories']
                           if pattern in r]
                for remote in remotes:
                    url = IMAGE_URL_TEMPLATE.format(registry, remote)
                    req = requests.get(
                        url=url,
                        auth=(REGISTRY_USER, REGISTRY_PASS))
                    if 'latest' in req.json()['tags']:
                        if image_name and image_name in req.json()['name']:
                            return req.json()['name']
                        else:
                            remotes_list.append(req.json()['name'])
            except Exception as e:
                logger.error('failed to reach {}. Exception is: {}'
                             .format(registry, e))
        return remotes_list

    @staticmethod
    def delete_image(image_name):
        '''return True if image_name is not in local images
           return True if image is not in local images list after removing it
           return False if image is in local images list after removing it
           return False if exception happens during deleting an image'''
        image_name = __class__.__to_full_image_name(image_name)
        if not image_name:
            return True
        else:
            logger.info('image full name {}'.format(image_name))
            client = docker.APIClient(BASE_URL)
            try:
                client.remove_image(image_name)
                if not client.images(image_name):
                    logger.info('image {} is successfully deleted'.
                                format(image_name))
                    return True
                else:
                    return False
            except Exception:
                return False

    @staticmethod
    def sync(registry, pattern, ref_node_id=0):
        raise NotImplementedError()
