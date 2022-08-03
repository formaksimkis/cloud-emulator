import sys
import webbrowser

import requests
import yaml
import logging
from itertools import groupby
from flask import Flask, request, jsonify, render_template
from flask_login import login_required, current_user
from flask_socketio import SocketIO
from werkzeug.utils import redirect

import emulator
from backend.utility import utility

from emulator import HOSTNAME, MAX_INSTANCES_PER_USER
from emulator import UPLOAD_SERVER
from emulator import NUM_OF_REMOTE_IMAGES_PER_CAT
from emulator import TITAN_IMAGE_NAME_PATTERN
from emulator import CLUSTER_IMAGE_NAME_PATTERN

from backend import DOMAINNAME
from backend import DOCKER_REGISTRY
from backend import POOL_NODES

from backend.errors import MAX_INSTANCES_PER_USER_ERROR
from backend.errors import UPLOAD_CONNECTION_ERROR
from backend.errors import MAX_INSTANCES_REACHED_ERROR
from backend.errors import DELETE_IMAGE_ERROR

from backend.scheduler import Scheduler
from backend.envoy_config import add_envoy_route
from backend.envoy_config import remove_envoy_route

from node.master import PoolMananger

logger = logging.getLogger(__name__)

# emulator_iface = emulator                # signle node setup
emulator_iface = PoolMananger(POOL_NODES)  # pool setup

scheduler = Scheduler(emulator_iface)

app = Flask(__name__)
socketio = SocketIO(app)


@app.route('/')
@login_required
def index():
    instances = emulator_iface.list_containers()
    local_images = []
    remote_images = []
    images_clust_local_to_launch = []
    running_cockpit_instance_pair = []
    all_images_dict = emulator_iface.list_images(DOCKER_REGISTRY,
                                                 TITAN_IMAGE_NAME_PATTERN)
    all_images_dict.update(
        emulator_iface.list_images(DOCKER_REGISTRY,
                                   CLUSTER_IMAGE_NAME_PATTERN))
    # Find 'num_to_filter' images for each build type
    # in remote images.
    # Remove rest of remote images in all_images_dict,
    # which are older than the youngest's filtered.
    num_to_filter = int(NUM_OF_REMOTE_IMAGES_PER_CAT)
    req_num_to_filter = request.args.get(
        'remote_images_per_cat',
        default=int(NUM_OF_REMOTE_IMAGES_PER_CAT),
        type=int)
    if req_num_to_filter is not None and req_num_to_filter >= 0:
        num_to_filter = req_num_to_filter
    if num_to_filter:
        all_images_dict = utility.filter_remote_img_by_youngest(
            all_images_dict,
            num_to_filter)
    for image, sha in all_images_dict.items():
        item = emulator_iface.describe_image(image, sha)
        item['image_name'] = item.get('image_name').upper()
        if sha.startswith('Remote'):
            remote_images.append(item)
        else:
            if CLUSTER_IMAGE_NAME_PATTERN in image.lower():
                images_clust_local_to_launch.append(item)
            else:
                local_images.append(item)

    username = str(current_user).split('@')[0]
    is_admin = current_user.admin

    instances = [inst for ident, inst in instances.items()]
    if not is_admin:
        instances = [inst for inst in instances if username in inst['childs']]
    for inst in instances:
        inst['shown_id'] = int(inst['id']) + 1
        inst['image_name'] = inst.get('image_name').upper()

    remote_addr = request.headers.get('x-forwarded-for')

    attached_devices = emulator.lsusb()
    attached_devices = [dev for dev in attached_devices
                        if remote_addr == dev['remote_address']]
    devices = emulator.lsusb(remote_addr)
    ivi_instances = [
        i for i in instances
        if "_emulator_titan_"
        in i['childs'] and "cockpit" not in i['childs']]
    cluster_instances = [
        i for i in instances
        if "_emulator_cluster_"
        in i['childs'] and "cockpit" not in i['childs']]
    cockpit_instances = [i for i in instances
                         if "cockpit" in i['childs']]
    if cockpit_instances:
        cockpit_instances_network_sorted = sorted(
            cockpit_instances, key=lambda x: x['net_name'])
        for key, value in groupby(
                cockpit_instances_network_sorted, key=lambda x: x['net_name']):
            running_cockpit_instance_pair.append(list(value))
    cluster_remote_images = [
        i for i in remote_images
        if CLUSTER_IMAGE_NAME_PATTERN.upper() in i['image_name']]
    ivi_remote_images = [
        i for i in remote_images
        if TITAN_IMAGE_NAME_PATTERN.upper() in i['image_name']]

    logger.info('username {}, admin {}'.format(username, is_admin))
    logger.info('client address {}'.format(remote_addr))
    logger.info('instances {}'.format(instances))
    logger.info('local images {}'.format(local_images))
    logger.info('remote images {}'.format(remote_images))
    logger.info('attached_devices {}'.format(attached_devices))
    logger.info('devices {}'.format(devices))

    return render_template(
        'mainpage.html',
        containers_title='Running instances',
        images_title='Downloaded Images',
        ivi_instances=ivi_instances,
        cluster_instances=cluster_instances,
        cockpit_instances=running_cockpit_instance_pair,
        images_local_to_launch=local_images,
        images_clust_local_to_launch=images_clust_local_to_launch,
        ivi_images_remote_to_download=ivi_remote_images,
        cluster_images_remote_to_download=cluster_remote_images,
        images_remote_to_download=remote_images,
        remote_addr=remote_addr,
        attached_devices=attached_devices,
        devices=devices)


@app.route('/launch/<image_name>')
@login_required
def launch(image_name):
    devices = []
    requested_devices = request.args.get('devs')
    cluster_name = request.args.get('cluster')
    username = str(current_user).split('@')[0]

    logger.info('request to launch image {} with devs {} from user {}'.format(
        image_name, requested_devices, username))
    logger.info('rewuest to launch cluster image {}'.format(cluster_name))

    if TITAN_IMAGE_NAME_PATTERN in image_name.lower():
        # Requested image is IVI/Titan image
        attached_devices = emulator.lsusb()
        logger.info('attached_devices {}'.format(attached_devices))

        devices = [{'path': device['dev_path'],
                    'vid_pid': device['vid_pid']}
                   for device in attached_devices
                   if str(device['port']) in requested_devices]

        logger.info('devices to pass {}'.format(devices))

    logger.info('image_name to pass {}'.format(image_name))
    logger.info('devices to pass {}'.format(devices))
    logger.info('username to pass {}'.format(username + '_'))

    instances = emulator_iface.list_containers()
    owned_instances = len([v for k, v in instances.items()
                           if username in v.get('childs')])
    if owned_instances >= int(MAX_INSTANCES_PER_USER):
        logger.error('max number of launched images is reached: {}'
                     .format(owned_instances))
        return jsonify({'error': MAX_INSTANCES_PER_USER_ERROR})

    if cluster_name is not None:
        ident = emulator.start_image(
            image_name, devices, username + '_cockpit_', cluster_name)
    else:
        ident = emulator_iface.start_image(
            image_name, devices, username + '_')

    if ident is None:
        return jsonify({'error': MAX_INSTANCES_REACHED_ERROR})

    instances = emulator_iface.list_containers()
    if cluster_name is not None:
        ivi_inst = instances[ident[0]]
        cluster_inst = instances[ident[1]]
        ivi_inst['image_name'] = ivi_inst.get('image_name').upper()
        cluster_inst['image_name'] = cluster_inst.get('image_name').upper()
        inst = {'ivi': ivi_inst, 'cluster': cluster_inst}
        inst['shown_id'] = int(ivi_inst['id']) + 1

        logger.info('started instances {} and {}'.format(ident[0], ident[1]))

        hostname = ivi_inst['hostname'] + '.' + DOMAINNAME
        add_envoy_route(ident[0], hostname, int(ivi_inst['port']))
        add_envoy_route(ident[1], hostname, int(cluster_inst['port']))
        return jsonify(inst)
    else:
        inst = instances[ident]
        inst['shown_id'] = int(inst['id']) + 1
        inst['image_name'] = inst.get('image_name').upper()
        logger.info('started instance {}'.format(inst))

        hostname = inst['hostname'] + '.' + DOMAINNAME
        add_envoy_route(ident, hostname, int(inst['port']))
        return jsonify(inst)


@app.route('/stop/<ident>')
@login_required
def stop(ident):
    username = str(current_user).split('@')[0]
    logger.info('request to stop instance {} from user {}'.format(
        ident, username))

    instances = emulator_iface.list_containers()
    instances = [inst for ident, inst in instances.items()]

    for inst in instances:
        if int(inst['id']) == int(ident):
            logger.info('stopping instance {} {}'.format(
                inst['id'], inst['image_name']))
            emulator_iface.stop_container(int(inst['id']))
            break

    hostname = inst['hostname'] + '.' + DOMAINNAME
    remove_envoy_route(ident, hostname, int(inst['port']))

    return '{}'


@app.route('/attach/<addr>/<bus_id>')
@login_required
def attach(addr, bus_id):
    logger.info('request to attach device at {}/{}'.format(addr, bus_id))

    device = emulator.attach(remote_address=addr, bus_id=bus_id)
    logger.info('attached device {}'.format(device))

    return jsonify(device)


@app.route('/detach/<ident>')
@login_required
def detach(ident):
    logger.info('request to detach device {}'.format(ident))

    attached_devices = emulator.lsusb()
    device = [device for device in attached_devices
              if device['port'] == int(ident)]
    if device != []:
        device = device[0]
        logger.info('detaching device {}'.format(device))
        emulator.detach(port=int(ident))
        return jsonify(device)
    else:
        return '{}'


@app.route('/pull/<image_name>')
@login_required
def pull(image_name):
    image_name_lower = image_name.lower()
    name_pattern = TITAN_IMAGE_NAME_PATTERN \
        if TITAN_IMAGE_NAME_PATTERN in image_name_lower \
        else CLUSTER_IMAGE_NAME_PATTERN
    namespace = "/" + image_name
    for v in emulator_iface.pull(image_name_lower,
                                 DOCKER_REGISTRY, name_pattern):
        for state_progress, percent_of_download in v.items():
            socketio.emit(
                "progress",
                {"text": state_progress + ':' + str(percent_of_download)},
                namespace=namespace)
            if state_progress == 'Complete':
                return jsonify({'state': state_progress})
            if state_progress == 'Failure':
                return jsonify({'state': state_progress})


@app.route('/delete/<image_name>')
@login_required
def deleteImage(image_name):
    logger.info('request to delete image {}'.format(image_name))
    if not emulator_iface.delete_image(image_name):
        return jsonify({'error': DELETE_IMAGE_ERROR})
    else:
        return jsonify({})


@app.route('/upload/<user_name>')
@login_required
def uploadImage(user_name):
    logger.info('request to upload image from {}'.format(user_name))
    url = "http://" + UPLOAD_SERVER
    req = requests.get(url + "/upload", params={'user': user_name})
    logger.info('got response from node {}:'.format(url))
    if not user_name == req.json():
        return jsonify({'error': UPLOAD_CONNECTION_ERROR})
    else:
        return jsonify({'url': url})
