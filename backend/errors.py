from emulator import MAX_INSTANCES_PER_USER

'''Custom errors templates to send to frontend'''

'''Limit of running instances per user'''
MAX_INSTANCES_PER_USER_ERROR = dict(
    reason='Running instances limit is reached!',
    description='Num of running instances per user should not exceed: '
                + str(MAX_INSTANCES_PER_USER))

'''Limit on running instances is reached error'''
MAX_INSTANCES_REACHED_ERROR = dict(
    reason='Running instances limit is reached!',
    description='The maximum number of running instances '
                'allowed in the system is reached')

'''Error deleting image'''
DELETE_IMAGE_ERROR = dict(
    reason='Image cant be deleted!',
    description='Deleting is not possible, '
                'image is launched or occupied ')

'''Error upload server connection'''
UPLOAD_CONNECTION_ERROR = dict(
    reason='Connection upload server error!',
    description='Uploading is not possible, '
                'please check network connection ')
