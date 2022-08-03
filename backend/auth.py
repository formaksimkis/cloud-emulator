import jwt
import json
import logging
from datetime import datetime, timedelta

from flask import Blueprint
from flask_login import LoginManager
from flask_login import login_required, login_user, logout_user, current_user
from flask_login import UserMixin
from flask import request, redirect, render_template
from ldap3 import Server, Connection, ALL, SUBTREE

from . import LDAP_SERVER
from . import ADMIN_GROUP_NAME
from . import AUTH_TEST_CREDS
from . import USER_GROUP_NAME

auth = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
active_users = {}  # dict of active users, key is user's email


class User(UserMixin):
    ''' Bacis class representing user '''

    def __init__(self, id):
        self.id = id
        self.admin = False

    def __repr__(self):
        return self.id


@login_manager.user_loader
def load_user(username):
    ''' Should return a user if logged in otherwize None '''
    return active_users.get(username, None)


@auth.route('/token', methods=['GET'])
def get_token():
    if not current_user.is_authenticated:
        return '', 401

    private_key_file = 'jwt_secrets_priv.jwks'

    # Note you really shouldn't have multiple keys in the jwks,
    # as we will only use the last one.
    with open(private_key_file) as f:
        jwks = json.load(f)
        for key in jwks['keys']:
            private_key = (
                key['kid'],
                jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key)))

    token = {
        # The KeyID, envoy will use this to pick the proper decryption key.
        'kid': private_key[0],
        # Both the 'iss' and 'aud' must match what is expected
        # in the envoy.yaml configuration
        # under "issuer" and "audiences",
        # without it the token will be rejected.
        'iss': 'android-emulator@jwt-provider.py',
        'aud': 'android.emulation.control.EmulatorController',
        # we give users 2 hours of access.
        'exp': datetime.now() + timedelta(hours=2),
        'iat': datetime.now(),
        'name': str(current_user)}
    return jwt.encode(token, private_key[1], algorithm='RS256')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    ''' Login handler
        Authentcates users via ldap '''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            if username in AUTH_TEST_CREDS:
                # always accepted
                user = User(username)
                user.admin = True if 'admin' in username else False
            else:
                server = Server(LDAP_SERVER, use_ssl=True, get_info=ALL)
                connection = Connection(
                    server,
                    user=username,
                    password=password,
                    auto_bind=True)
                connection.search(
                    search_base='dc=ad,dc=harman,dc=com',
                    search_filter='(sAMAccountName={})'.format(
                        username.split('@')[0]),
                    search_scope=SUBTREE,
                    attributes=['memberOf'])
                memberOf = set(
                    map(lambda x: x.lower().split(',')[0].split('=')[1],
                        connection.response[0]['attributes']['memberOf']))
                connection.unbind()
                logger.info('allowedusers {}, '.format(USER_GROUP_NAME))
                logger.info('memberOf {}, '.format(memberOf))
                commonGroupsFound = (USER_GROUP_NAME & memberOf)
                logger.info('commonGroupsFound {}, '.format(commonGroupsFound))
                if (len(commonGroupsFound) > 0 or
                        ADMIN_GROUP_NAME.lower() in memberOf):
                    user = User(username)
                    user.admin = True \
                        if ADMIN_GROUP_NAME.lower() in memberOf else False
                    login_user(user)
                    active_users[username] = user
                    logger.info(
                        'USER LOGIN OK {}, admin {}'.format(
                            username, user.admin))
                    return redirect(request.args.get('next'))
                else:
                    logger.info(
                        'USER NOT ALLOWED TO LOGIN IN {}'.format(username))
                    return render_template('login.html', notallowed=True)
        except Exception:
            logger.info('USER LOGIN FAILED {}'.format(username))
            return render_template('login.html', failed=True)
    else:
        return render_template('login.html', failed=False, notallowed=False)


@auth.route("/logout")
@login_required
def logout():
    ''' Logout handler '''
    try:
        del active_users[str(current_user)]
    except Exception:
        pass
    logger.info('USER LOGOUT {}'.format(str(current_user)))
    logout_user()
    return '{}'
