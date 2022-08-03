import unittest

from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from .mock_docker import DockerClientMock
from .mock_docker import APIClientMock

import emulator


class TestCase(unittest.TestCase):
    def setUp(self):
        pass

    @patch('docker.DockerClient', new_callable=DockerClientMock)
    @patch('docker.APIClient', new_callable=APIClientMock)
    def test_create_multiple_containers_in_parallel(self, fake_api_client, _):
        no_of_containers = 10
        with ThreadPoolExecutor(max_workers=no_of_containers) as executor:
            futures = executor.map(
                emulator.start_image,
                no_of_containers*['cloud_android_test_image_name'])
            for _ in futures:
                pass

        containers = [cont['Name'][0] for cont in fake_api_client.containers()]
        cont_ids = [int(cont.split('_')[-1]) for cont in containers]
        self.assertTrue(all(
            [ident in cont_ids for ident in range(no_of_containers)]))
