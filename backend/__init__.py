import os
import logging

DOMAINNAME = os.environ.get(
    'DOMAINNAME',
    'ad.harman.com')

DOCKER_REGISTRY = os.environ.get(
    'DOCKER_REGISTRY',
    'https://artifactory-mb.harman.com:443'
    '/artifactory/api/docker/platform_docker_registry')
DOCKER_REGISTRY = None if DOCKER_REGISTRY == '' else DOCKER_REGISTRY

LDAP_SERVER = os.environ.get(
    'LDAP_SERVER',
    'ldaps://ldapmd.ad.harman.com:3269')

ADMIN_GROUP_NAME = os.environ.get(
    'ADMIN_GROUP_NAME',
    None)

AUTH_TEST_CREDS = os.environ.get('AUTH_TEST_CREDS', None)
AUTH_TEST_CREDS = AUTH_TEST_CREDS.split(',') if AUTH_TEST_CREDS else []

POOL_NODES = os.environ.get('POOL_NODES', None)
POOL_NODES = POOL_NODES.split(',') if POOL_NODES else []

USER_GROUP_NAME = os.environ.get('USER_GROUP_NAME', None)
USER_GROUP_NAME = set(
    map(str.strip,
        USER_GROUP_NAME.lower()[1:-1].split(','))) if USER_GROUP_NAME else {}
USER_GROUP_NAME = {' '.join(a.split()) for a in USER_GROUP_NAME}
if os.environ.get('DEBUG', None):
    logging.basicConfig(
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        level=logging.DEBUG)

from backend.backend import app  # nopep8
from backend.auth import login_manager  # nopep8
from backend.auth import auth  # nopep8

app.config.update(SECRET_KEY=os.urandom(16))
app.register_blueprint(auth)
login_manager.init_app(app)
