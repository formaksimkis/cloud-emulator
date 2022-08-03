import json
import logging
import requests
from flask import Flask, request, jsonify
from flask_socketio import SocketIO

import emulator

logger = logging.getLogger(__name__)
app = Flask(__name__)
socketio = SocketIO(app)


@app.route('/images')
def images():
    name_pattern = request.args.get('pattern', '')
    images = emulator.list_images(None, name_pattern)
    logger.info('request for images from {}: {}'.format(
        request.remote_addr, images))
    return jsonify(images)


@app.route('/instances')
def instances():
    instances = emulator.list_containers()
    logger.info('request for instances from {}: {}'.format(
        request.remote_addr, instances))
    return jsonify(instances)


@app.route('/launch')
def launch():
    image_name = request.args.get('image_name', None)
    devices = request.args.get('devices', [])
    prefix = request.args.get('prefix', 'anonymous_')

    logger.info('request for launch from {}:'.format(request.remote_addr))
    logger.info('image_name {}'.format(image_name))
    logger.info('devices {}'.format(devices))
    logger.info('prefix {}'.format(prefix))

    ident = emulator.start_image(image_name, devices, prefix)
    return jsonify(ident)


@app.route('/stop')
def stop():
    ident = request.args.get('ident', None)

    logger.info('request for stop from {}:'.format(request.remote_addr))
    logger.info('ident {}'.format(ident))

    emulator.stop_container(int(ident))
    return jsonify({})


@app.route('/pull')
def pull():
    image_name = request.args.get('image_name', None)
    registry = request.args.get('registry', None)
    pattern = request.args.get('pattern', None)

    namespace = "/" + image_name
    for value in emulator.pull(image_name, registry, pattern):
        for state_progress, percent_of_download in value.items():
            socketio.emit("progress", json.dumps(
                {"text": {state_progress: str(percent_of_download)}}),
                namespace=namespace)
            if state_progress == 'Complete' or state_progress == 'Failure':
                return jsonify({'state': state_progress})


@app.route('/delete')
def delete():
    image_name = request.args.get('image', None)
    logger.info('request for delete from {}: image {}'.format(
        request.remote_addr, image_name))
    return jsonify(emulator.delete_image(image_name))
