import os
import yaml
import logging

logger = logging.getLogger(__name__)

ENVOY_LDS_FILENAME = '/var/lib/envoy/lds.yaml'
ENVOY_CDS_FILENAME = '/var/lib/envoy/cds.yaml'


def format_resource(ident, hostname, port):
    return [{
        '@type': 'type.googleapis.com/envoy.config.cluster.v3.Cluster',
        'name': 'isntance{}'.format(ident),
        'connect_timeout': '0.250s',
        'type': 'strict_dns',
        'lb_policy': 'round_robin',
        'http2_protocol_options': {},
        'load_assignment': {
            'cluster_name': 'isntance{}'.format(ident),
            'endpoints': [{
                'lb_endpoints': [{
                    'endpoint': {
                        'address': {
                            'socket_address': {
                                'address': hostname,
                                'port_value': port
                            }
                        }
                    }
                }]
            }]
        }
    }]


def format_route(ident):
    return [{
        'match': {
            'prefix': '/instance/{}/android.emulation.control'.format(ident)},
        'route': {
            'cluster': 'isntance{}'.format(ident),
            'max_grpc_timeout': '0s',
            'prefix_rewrite': '/android.emulation.control'
        }
    }]


def add_cds_resource(resources, ident, hostname, port):
    if [r for r in resources if f'isntance{ident}' == r['name']]:
        logger.info('resources for instance {} '
                    'is already in config'.format(ident))
        return resources

    new_resource = format_resource(ident, hostname, port)
    logger.info('add resources for instance {}: {}'.format(
        ident, new_resource))

    resources.insert(0, new_resource[0])
    return resources


def remove_cds_resource(resources, ident, hostname, port):
    if not [r for r in resources if f'isntance{ident}' == r['name']]:
        logger.info('no resources for instance {} '.format(ident))
        return resources

    resource_to_remove = format_resource(ident, hostname, port)
    resources.remove(resource_to_remove[0])

    logger.info('remove resources for instance {}'.format(ident))
    return resources


def add_lds_route(routes, ident):
    if [r for r in routes if r['match'].get('prefix') and
            f'instance/{ident}' in r['match']['prefix']]:
        logger.info('routes for instance {} '
                    'is already in config'.format(ident))
        return routes

    new_route = format_route(ident)
    logger.info('add routes for instance {}: {}'.format(ident, new_route))

    routes.insert(0, new_route[0])
    return routes


def remove_lds_route(routes, ident):
    if not [r for r in routes if r['match'].get('prefix') and
            f'instance/{ident}' in r['match']['prefix']]:
        logger.info('no routes for instance {} '.format(ident))
        return routes

    route_to_remove = format_route(ident)
    routes.remove(route_to_remove[0])

    logger.info('remove routes for instance {}'.format(ident))
    return routes


def update_config(filename, func):
    with open(filename, 'r+') as file:
        config = yaml.full_load(file)
        func(config)
        file.seek(0)
        yaml.dump(config, file)
        file.truncate()


def add_envoy_route(ident, hostname, port):
    update_config(
        ENVOY_CDS_FILENAME,
        lambda config:
            add_cds_resource(config['resources'], ident, hostname, port))

    update_config(
        ENVOY_LDS_FILENAME,
        lambda config:
            add_lds_route(
                config[
                    'resources'][0][
                    'filter_chains'][0][
                    'filters'][
                    'typed_config'][
                    'route_config'][
                    'virtual_hosts'][0][
                    'routes'],
                ident))

    os.system('/bin/sed -i s/dummy/dummy/ {}'.format(ENVOY_CDS_FILENAME))
    os.system('/bin/sed -i s/dummy/dummy/ {}'.format(ENVOY_LDS_FILENAME))


def remove_envoy_route(ident, hostname, port):
    update_config(
        ENVOY_CDS_FILENAME,
        lambda config:
            remove_cds_resource(config['resources'], ident, hostname, port))

    update_config(
        ENVOY_LDS_FILENAME,
        lambda config:
            remove_lds_route(
                config[
                    'resources'][0][
                    'filter_chains'][0][
                    'filters'][
                    'typed_config'][
                    'route_config'][
                    'virtual_hosts'][0][
                    'routes'],
                ident))

    os.system('/bin/sed -i s/dummy/dummy/ {}'.format(ENVOY_CDS_FILENAME))
    os.system('/bin/sed -i s/dummy/dummy/ {}'.format(ENVOY_LDS_FILENAME))
