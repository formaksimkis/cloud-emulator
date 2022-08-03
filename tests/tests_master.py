import sys
import time
import json
import logging
import unittest
import requests
from queue import Empty
from flask import Flask, jsonify
from flask_socketio import SocketIO
from multiprocessing import Process, Queue
from parameterized import parameterized_class

from node.master import RemoteNode
from node.master import PoolMananger


class TestEndlessList(list):
    def __init__(self, value):
        self.current = 0
        list.__init__(self, value)

    def __first__(self):
        self.current = 0
        return list.__getitem__(self, self.current)

    def __next__(self):
        self.current = self.current + 1 \
            if self.current + 1 < len(self) else self.current
        return list.__getitem__(self, self.current)


class StubSlaveNode(object):
    def __init__(self, port=9999):
        self.port = port
        self.queue = Queue()
        self.process = None
        self.app = Flask(__name__)
        self.sio = SocketIO(self.app, async_mode='threading')

        @self.app.route('/sync')
        def sync():
            return jsonify('ok')

        @self.app.route('/pull')
        def pull():
            for value in self.__get_value():
                self.sio.emit(
                    'progress',
                    json.dumps({'text': value}),
                    namespace='/image_name')
            return jsonify({'state': 'Complete'})

    def __sync(self, timeout=10):
        start_time = time.time()
        while time.time() < start_time + timeout:
            try:
                requests.get(
                    f'http://localhost:{self.port}/sync', timeout=1).json()
                return True
            except Exception:
                pass
        return False

    def __get_value(self):
        last_reported = value = {'Failure': 0}
        while value != {'Complete': 100}:
            try:
                value = ''
                for symbol in self.queue.get(timeout=1):
                    value += symbol
                value = json.loads(value)
                yield value
                last_reported = value
            except Empty as e:
                yield last_reported

    def __enable_logs(self, enabled):
        for module in sys.modules.keys():
            logging.getLogger(module).disabled = not enabled

    def start_server(self):
        self.__enable_logs(True)
        self.app.run(port=self.port, use_reloader=False)

    def start(self):
        self.__enable_logs(False)
        self.process = Process(target=self.start_server)
        self.process.start()
        self.__enable_logs(True)
        return self.__sync()

    def stop(self):
        try:
            self.__enable_logs(False)
            self.process.terminate()
            self.process.join()
        except Exception:
            pass
        # self.__enable_logs(True)

    def set_value(self, value):
        value = json.dumps(value)
        self.queue.put(value)


class TestCaseRemoteNode(unittest.TestCase):
    def setUp(self):
        print(f'START {self._testMethodName}')
        self.node = RemoteNode('http://localhost:9999')
        self.slave = StubSlaveNode()
        self.reported_values = TestEndlessList([
            {'Downloading': x} for x in range(101)] + [
            {'Extracting': x} for x in range(101)] + [
            {'Complete': 100}])
        self.slave.set_value(self.reported_values.__first__())

    def tearDown(self):
        self.slave.stop()
        print(f'END {self._testMethodName}')

    def assertProgress(self, value):
        state_defs = ['Failure', 'Downloading', 'Extracting', 'Complete']
        self.assertTrue(any(x in value.keys() for x in state_defs))

    def test_pull_ok(self):
        latest_value = None
        self.assertTrue(self.slave.start())
        for value in self.node.pull('image_name', 'repo_path'):
            self.assertProgress(value)
            self.slave.set_value(self.reported_values.__next__())
            latest_value = value
        self.assertEqual(latest_value, {'Complete': 100})

    def test_pull_nok_no_slave(self):
        for value in self.node.pull('image_name', 'repo_path'):
            self.assertEqual(value, {'Failure': 0})

    def test_pull_nok_slave_disconnect(self):
        latest_value = None
        self.assertTrue(self.slave.start())
        for value in self.node.pull('image_name', 'repo_path'):
            self.assertProgress(value)
            latest_value = value
            if 'Downloading' in value.keys() and value['Downloading'] > 20:
                self.slave.stop()
            else:
                self.slave.set_value(self.reported_values.__next__())
        self.assertEqual(latest_value, {'Failure': 0})


@parameterized_class(('no_of_slaves',), [(1,), (2,), (3,), (5,), (10,), ])
class TestCasePoolMananger(unittest.TestCase):
    def setUp(self):
        print(f'START {self._testMethodName}')
        self.slaves = [
            f'http://localhost:{x}' for x in
            range(9999, 9999 - self.no_of_slaves, -1)]
        self.pool = PoolMananger(self.slaves)
        self.pool.nodes = {k: v for k, v in list(self.pool.nodes.items())[1:]}
        self.slaves = [
            StubSlaveNode(x) for x in
            range(9999, 9999 - self.no_of_slaves, - 1)]
        self.reported_values = TestEndlessList([
            {'Downloading': x} for x in range(101)] + [
            {'Extracting': x} for x in range(101)] + [
            {'Complete': 100}])
        [slave.set_value(self.reported_values.__first__())
            for slave in self.slaves]

    def tearDown(self):
        [slave.stop() for slave in self.slaves]
        print(f'END {self._testMethodName}')

    def assertProgress(self, value):
        state_defs = ['Failure', 'Downloading', 'Extracting', 'Complete']
        self.assertTrue(any(x in value.keys() for x in state_defs))

    def test_pull_ok(self):
        latest_value = None
        self.assertTrue(all([slave.start() for slave in self.slaves]))
        for value in self.pool.pull('image_name', 'repo_path'):
            self.assertProgress(value)
            [slave.set_value(self.reported_values.__next__())
                for slave in self.slaves]
            latest_value = value
        self.assertEqual(latest_value, {'Complete': 100})

    def test_pull_nok_no_slave(self):
        for value in self.pool.pull('image_name', 'repo_path'):
            self.assertEqual(value, {'Failure': 0})

    def test_pull_nok_slave_disconnect(self):
        latest_value = None
        self.assertTrue(all([slave.start() for slave in self.slaves]))
        for value in self.pool.pull('image_name', 'repo_path'):
            self.assertProgress(value)
            latest_value = value
            if 'Downloading' in value.keys() and value['Downloading'] > 20:
                [slave.stop() for slave in self.slaves]
            else:
                [slave.set_value(self.reported_values.__next__())
                    for slave in self.slaves]
        self.assertEqual(latest_value, {'Failure': 0})
