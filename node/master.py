import json
import random
import logging
import requests
import socketio
import threading
from enum import Enum

from concurrent.futures import ThreadPoolExecutor

import emulator
from emulator import HOSTNAME
from node import MAX_INSTANCES_PER_NODE

logger = logging.getLogger(__name__)


class NodeAvailState(Enum):
    OFFLINE = 0
    ONLINE = 1

    def __str__(self):
        return 'ONLINE' if self.value else 'OFFLINE'


class RemoteNode:
    ''' Represents a node running on remote machine '''
    def __init__(self, node_url):
        self.node_url = node_url
        self.avail_state = NodeAvailState.OFFLINE

    def __request_node(self, api_path, params={}):
        try:
            url = self.node_url + api_path
            req = requests.get(url, params=params)
            self.avail_state = NodeAvailState.ONLINE
            logger.info('got response from node {}:'.format(url))
            logger.info(req.json())
            return req.json()
        except Exception as e:
            self.avail_state = NodeAvailState.OFFLINE
            logger.info('node {} not available'.format(self.node_url))
            return {}

    def list_images(self, registry=None, name_pattern=''):
        return self.__request_node('/images', {'pattern': name_pattern})

    def list_containers(self):
        return self.__request_node('/instances')

    def start_image(self, image_name, devices=[], prefix=''):
        return self.__request_node('/launch', {
            'image_name': image_name,
            'devices': devices,
            'prefix': prefix})

    def stop_container(self, ident):
        return self.__request_node('/stop', {'ident': ident})

    def pull(self, image_name, registry, pattern=''):
        progress_cv = threading.Condition()
        progress_value = {}

        def __pull_request_wrapper(api_path, params={}):
            nonlocal progress_cv, progress_value
            value = self.__request_node(api_path, params)
            with progress_cv:
                if value == {'state': 'Complete'}:
                    progress_value = {'Complete': 100}
                else:
                    progress_value = {'Failure': 0}
                progress_cv.notify()

        pull_thread = threading.Thread(
            target=__pull_request_wrapper, args=(
                '/pull', {
                    'image_name': image_name,
                    'registry': registry,
                    'pattern': pattern}))

        pull_thread.start()

        sio = socketio.Client(reconnection=False)

        def __progress(data):
            nonlocal progress_cv, progress_value
            with progress_cv:
                # socketio messages are delivered to the client
                # out of order from time to time, so do not update
                # the progress if Complete was received earlier
                if (progress_value != {'Complete': 100} and
                        progress_value != {'Failure': 0}):
                    progress_value = json.loads(data).get('text')
                progress_cv.notify()

        def __disconnect():
            nonlocal progress_cv, progress_value
            with progress_cv:
                if progress_value != {'Complete': 100}:
                    progress_value = {'Failure': 0}
                progress_cv.notify()

        namespace = '/' + image_name
        sio.on('progress', __progress, namespace)
        sio.on('disconnect', __disconnect, namespace)

        reported_value = {'Failure': 0}
        try:
            sio.connect(self.node_url, namespaces=[namespace])
            with progress_cv:
                while True:
                    progress_cv.wait()
                    reported_value = progress_value

                    if ('Failure' in reported_value.keys() or
                            'Complete' in reported_value.keys()):
                        break
                    yield reported_value
        except Exception as e:
            logger.info(f'exception from sio {e}')

        pull_thread.join()
        sio.disconnect()
        yield reported_value

    def delete_image(self, image_name):
        return self.__request_node('/delete', {'image': image_name})


class SelfNode:
    ''' Represents a node which is running localy with the backend
        as a monolith instance. If the node is running as separate
        instance on single machine with the backend, RemoteNode
        entity should be used then. '''
    def __init__(self):
        self.node_url = 'local-self-node'
        self.avail_state = NodeAvailState.ONLINE

    def list_images(self, registry=None, name_pattern=''):
        return json.loads(json.dumps(emulator.list_images(
            registry, name_pattern)))

    def list_containers(self):
        return json.loads(json.dumps(emulator.list_containers()))

    def start_image(self, image_name, devices=[], prefix=''):
        return json.loads(json.dumps(emulator.start_image(
            image_name, devices, prefix)))

    def stop_container(self, ident):
        return json.loads(json.dumps(emulator.stop_container(ident)))

    def pull(self, image_name, registry, pattern=''):
        for value in emulator.pull(image_name, registry, pattern):
            yield value

    def delete_image(self, image_name):
        return json.loads(json.dumps(emulator.delete_image(image_name)))


class BalancingStrategy:
    ''' Implements the balancing strategy among nodes in the pool '''
    def select_node(nodes):
        ''' Returns a tuple with the index and node instance of the
            node to be used for the next image launching.
            The tuple (None, None) is returned if max number of
            instances per node is reached. '''
        inst_per_node = {k: len(v.list_containers()) for k, v in nodes.items()}
        inst_per_node = {k: v for k, v in inst_per_node.items()
                         if nodes[k].avail_state == NodeAvailState.ONLINE}
        logger.info(f'instances per nodes at node select: {inst_per_node}')

        min_inst_per_node = min(inst_per_node.values())
        if min_inst_per_node >= MAX_INSTANCES_PER_NODE:
            logger.info(f'max instances per node reached {min_inst_per_node}')
            return (None, None)

        min_inst_nodes = [k for k, v in inst_per_node.items()
                          if v == min_inst_per_node]
        logger.info(f'nodes with min instances {min_inst_nodes}')

        if len(min_inst_nodes) == 1 and min_inst_nodes[0] == 0:
            selected = (0, nodes[0])  # only master self-node left
        else:
            min_inst_nodes = [k for k in min_inst_nodes if k != 0]
            node_id = random.choice(min_inst_nodes)
            selected = (node_id, nodes[node_id])
        logger.info(f'selected {selected}')
        return selected


class PoolMananger:
    ''' Represents a pool of nodes. The implementation must have common
        inteface with emulator, so it is transparent for the caller if it is
        interfacing to just signle emulator instance or to the pool of them '''
    NODE_INDEX_BASE = 100

    def __init__(self, urls):
        self.nodes = {
            **{0: SelfNode()},  # node=0 is backend itself
            **{k: RemoteNode(url) for k, url in enumerate(urls, start=1)}}

    def __nodes__(self):
        ''' For debug purposes only '''
        return self.nodes

    def __nodes_info__(self):
        ''' For debug purposes only '''
        self.list_containers()  # update avail state
        return [
            {'id': node_id,
             'url': node.node_url,
             'role': 'master' if not node_id else 'slave',
             'state': node.avail_state}
            for node_id, node in self.nodes.items()]

    def __to_instance_index(self, node_index, instance_index):
        return self.NODE_INDEX_BASE*node_index + instance_index

    def __from_instance_index(self, instance_index):
        return (instance_index // self.NODE_INDEX_BASE,
                instance_index % self.NODE_INDEX_BASE)

    def list_images(self, registry=None, name_pattern=''):
        ''' Return only images present in all nodes '''
        images = [node.list_images(registry, name_pattern)
                  for node in self.nodes.values()]
        intersect = set.intersection(*map(set, [[
            k for k, v in d.items() if v != 'Remote'] for d in images]))
        intersect_and_remote = {
            k: v for d in images for k, v in d.items()
            if k in intersect or v == 'Remote'}
        out_of_intersect = {
            k: 'Remote' for d in images for k, v in d.items()
            if k not in intersect and v != 'Remote'}
        return {**intersect_and_remote, **out_of_intersect}

    def list_containers(self):
        instances = dict()
        for index, node in self.nodes.items():
            for ident, container in node.list_containers().items():
                instance_index = self.__to_instance_index(index, int(ident))
                container['id'] = instance_index
                # TODO: To be corrected once cluster graphics link
                # is modified to be routed via envoy without react app
                if 'cloud_android' in container['image_name']:
                    container['link'] = 'http://{}/instance/{}'.format(
                        HOSTNAME.lower(), instance_index)
                instances[instance_index] = container
        return instances

    def start_image(self, image_name, devices=[], prefix=''):
        if devices:
            # select master node if device passing is requested
            node_index, target_node = (0, self.nodes[0])
        else:
            # Although it is expected all nodes have the same set of images,
            # filter out nodes where desired image is not present
            nodes = {k: v for k, v in self.nodes.items()
                     if v.list_images(name_pattern=image_name.lower())}
            node_index, target_node = BalancingStrategy.select_node(nodes)
        if target_node is None:
            return None  # launch failed
        ident = target_node.start_image(image_name, devices, prefix)
        return self.__to_instance_index(node_index, ident)

    def stop_container(self, ident):
        node_index, ident = self.__from_instance_index(ident)
        self.nodes[node_index].stop_container(ident)

    def describe_image(self, image_name, sha):
        return emulator.describe_image(image_name, sha)

    def pull(self, image_name, registry, pattern=''):
        progress_cv = threading.Condition()
        progress_values = [{'Downloading': 0} for node in self.nodes]

        def __pull_wrapper(node_index, node):
            nonlocal progress_cv, progress_values
            logger.info(f'enter __pull_wrapper {node_index}')
            for value in node.pull(image_name, registry, pattern):
                with progress_cv:
                    logger.info(f'__pull_wrapper {node_index}, {value}')
                    progress_values[node_index] = value
                    progress_cv.notify()
                if 'Failure' in value.keys() or 'Complete' in value.keys():
                    logger.info(f'exit __pull_wrapper {node_index}')
                    return

        with ThreadPoolExecutor(max_workers=len(self.nodes)) as executor:
            pull_futures = executor.map(
                __pull_wrapper, range(len(self.nodes)), self.nodes.values())

            __progress_values = [{'Downloading': 0} for node in self.nodes]
            reported_value = {'Failure': 0}

            with progress_cv:
                while True:
                    progress_cv.wait()
                    __progress_values = progress_values

                    # The reporting strategy is that the value with lower state
                    # is reported first; mean value is returned if there are
                    # several nodes in the same state.
                    for state in ['Failure', 'Downloading',
                                  'Extracting', 'Complete']:
                        state_values = [
                            prog_val for prog_val in __progress_values
                            if state in prog_val.keys()]
                        if state_values:
                            values = [int(prog_val[state])
                                      for prog_val in state_values]
                            reported_value = {state: sum(values)//len(values)}
                            break

                    if ('Failure' in reported_value.keys() or
                            'Complete' in reported_value.keys()):
                        break

                    yield reported_value

            # wait till complete
            for f in pull_futures:
                pass

            yield reported_value

    def delete_image(self, image_name):
        success = True
        for node in self.nodes.values():
            result = node.delete_image(image_name)
            logger.info('result of deleting an image: {} on node: {} is: {}'
                        .format(image_name, node.node_url, result))
            if not result:
                success = False
        return success

    def sync(self, registry, pattern, ref_node_id=0):
        ''' Synchronizes local images on the nodes in the cluster to
            the set of images on the node pointed by ref_node_id:
            missing images are pulled, extra images are removed '''
        if ref_node_id >= len(self.nodes):
            return

        ref_images = self.nodes[ref_node_id].list_images()
        ref_images = [i for i in ref_images.keys() if pattern in i]

        nodes = [node for node_index, node in self.nodes.items()
                 if node_index != ref_node_id]

        images_to_remove = []
        images_to_pull = []

        for node in nodes:
            node_images = [
                i for i in node.list_images().keys() if pattern in i]

            images_to_remove += [
                i for i in node_images if i not in ref_images]
            images_to_pull += [
                i for i in ref_images if i not in node_images]

        for image_name in images_to_remove:
            self.delete_image(image_name)
            yield f'deleting {image_name}: done'

        for image_name in images_to_pull:
            for progress in self.pull(image_name, registry):
                for state, value in progress.items():
                    yield f'pulling {image_name}: {state} {value}%'
            yield f'pulling {image_name}: done'
