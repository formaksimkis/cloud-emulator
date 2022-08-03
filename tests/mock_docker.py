import docker
import unittest

from threading import Lock


class APIClientMock(unittest.mock.Mock):
    __images = [{
        'Id': '0',
        'Created': '2 days ago',
        'Repository': 'reponame',
        'RepoTags': ['cloud_android_test_image_name:latest'],
    }]
    __containers = []
    __lock = Lock()

    def images(self, name=None, quiet=False, all=False, filters=None):
        return self.__images

    def inspect_image(self, image_id):
        return self.__images[int(image_id)]

    def containers(self, quiet=False, all=False, trunc=False, latest=False,
                   since=None, before=None, limit=-1, size=False,
                   filters=None):
        with self.__lock:
            return [{
                'Id': ident,
                'Name': [name],
                'Image': 'cloud_android_test_image_name:latest',
                'Created': '2 days ago',
                'Command': 'true',
                'Status': 'fake status'
            } for ident, name in zip(
                range(len(self.__containers)), self.__containers)]

    def inspect_container(self, container_id):
        with self.__lock:
            return {
                'Id': container_id,
                'Config': {
                    'Image': 'cloud_android_test_image_name',
                },
                'NetworkSettings': {
                    'Networks': {
                        'emulator_envoymesh': 'dummy'
                    }
                },
                'ID': container_id,
                'Name': self.__containers[int(container_id)],
                "State": {
                    "Status": "running",
                    "Running": True,
                    "Pid": 0,
                    "ExitCode": 0,
                    "StartedAt": "2013-09-25T14:01:18.869545111+02:00",
                    "Ghost": False
                },
                "HostConfig": {
                    'Devices': [{'PathOnHost': 'dev0'}, {'PathOnHost': 'dev1'}]
                },
            }

    def create_container(self, image, command=None, hostname=None, user=None,
                         detach=False, stdin_open=False, tty=False, ports=None,
                         environment=None, volumes=None,
                         network_disabled=False, name=None, entrypoint=None,
                         working_dir=None, domainname=None, host_config=None,
                         mac_address=None, labels=None, stop_signal=None,
                         networking_config=None, healthcheck=None,
                         stop_timeout=None, runtime=None,
                         use_config_proxy=True):
        with self.__lock:
            self.__containers += [name]
            return {'Id': str(len(self.__containers)-1)}

    def networks(self, names=None, ids=None, filters=None):
        return []

    def create_network(self, name, driver=None, options=None, ipam=None,
                       check_duplicate=None, internal=False, labels=None,
                       enable_ipv6=False, attachable=None, scope=None,
                       ingress=None):
        pass


class DockerClientMock(docker.DockerClient):
    def __init__(self, *args, **kwargs):
        self.api = APIClientMock(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self
