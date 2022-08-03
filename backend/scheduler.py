import logging
import re

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from backend import DOCKER_REGISTRY
from emulator import SCHEDULER_JOB_HOUR, SCHEDULER_JOB_MINUTE
from emulator import TITAN_IMAGE_NAME_PATTERN, CLUSTER_IMAGE_NAME_PATTERN
from backend.utility import utility

logger = logging.getLogger(__name__)


class Scheduler:

    def __init__(self, emulator_iface):
        self.emulator_iface = emulator_iface
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(self.__listener,
                                    EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        '''main job starts on a backend once a day'''
        self.scheduler.add_job(self.__main_job,
                               'cron',
                               day_of_week='mon-sun',
                               hour=SCHEDULER_JOB_HOUR,
                               minute=SCHEDULER_JOB_MINUTE)
        self.scheduler.start()

    def __main_job(self):
        logger.info('main job started')
        self.__sync_cluster_images(DOCKER_REGISTRY, TITAN_IMAGE_NAME_PATTERN)
        self.__sync_cluster_images(DOCKER_REGISTRY, CLUSTER_IMAGE_NAME_PATTERN)
        self.__actualize_local_images_job()

    def __second_job(self):
        # TODO (inform admin if some images are not downloaded
        #  or space is not left,
        #  send a mail for example)
        logger.info('second job started')

    def __listener(self, event):
        logger.info('job event: {} Event.jobid {}'.format(event, event.job_id))
        if not event.exception:
            job = self.scheduler.get_job(event.job_id)
            if job and job.name == '__main_job':
                self.scheduler.add_job(self.__second_job)

    def __sync_cluster_images(self, registry, pattern):
        '''Syncs images in the cluster to master's set'''
        for value in self.emulator_iface.sync(registry, pattern):
            if 'done' in value:
                logger.info(f'{value}')

    def __actualize_local_images_job(self):
        '''This func is for:
           makes two youngest lists of images: remote and local
           deletes all local images which is not in local youngest list
           checks if some youngest remote image is already in local youngest
               if not, job makes less than 3 attempts
               to download the new image from remote youngest list
               after successfully downloading deletes all images of such type
               already downloaded from existed the youngest local image,
               if it is not downloaded after 3 attempts we do not
               guarantee that the image will be in the final refreshed list
               to display on the frontend
           job ends with success if all the new remote youngest images
           are on a local user space now'''
        local_list = self.__get_local_list_images()
        remote_list = self.__get_remote_list_images()

        youngest_local_images = utility.search_youngest_images(local_list)
        logger.info('youngest local images: {}'.format(youngest_local_images))

        youngest_remote_images = utility.search_youngest_images(remote_list)
        logger.info('youngest remote images: {}'.
                    format(youngest_remote_images))

        images_fail_to_delete = []
        for image in local_list:
            if image not in youngest_local_images:
                result = self.emulator_iface.delete_image(image)
                if result:
                    logger.info('deleted: {}'.format(image))
                else:
                    images_fail_to_delete.append(image)
                    logger.info('not deleted: {}'.format(image))

        for image in youngest_remote_images:
            if image not in youngest_local_images:
                logger.info('image to download: {}'.format(image))
                attempt = 0
                is_downloaded = False
                while attempt <= 3 and not is_downloaded:
                    result = ''
                    for v in self.emulator_iface.pull(
                            image,
                            DOCKER_REGISTRY,
                            TITAN_IMAGE_NAME_PATTERN
                            if TITAN_IMAGE_NAME_PATTERN in image
                            else CLUSTER_IMAGE_NAME_PATTERN):
                        for state_progress in v.keys():
                            result = state_progress
                    attempt = attempt + 1
                    if result == 'Complete':
                        logger.info('image is downloaded: {}'
                                    .format(image))
                        is_downloaded = True
                        logger.info("image {} is successfully downloaded "
                                    "after {} attempt".format(image, attempt))
                        self.__delete_useless_images(
                            image,
                            youngest_local_images,
                            images_fail_to_delete)
                    if result == 'Failure':
                        logger.error("image {} is not downloaded "
                                     "after {} attempt".format(image, attempt))
                if not is_downloaded:
                    logger.error("image {} is not downloaded at all after "
                                 "{} attempt".format(image, attempt))
            else:
                logger.error("image {} is already downloaded".format(image))
                continue

        logger.info('images fail to delete: {}'
                    .format(images_fail_to_delete))
        local_list_refreshed = self.__get_local_list_images()
        if self.__is_in_list(local_list_refreshed, youngest_remote_images):
            logger.info('Job was finished successfully')
            return 0
        else:
            logger.info('Job was finished unsuccessfully')
            raise Exception('Smth went wrong!')

    def __get_local_list_images(self):
        all_images_dict = self.__get_all_images_dict()
        return [k for k, v in all_images_dict.items()
                if v != 'Remote']

    def __get_remote_list_images(self):
        return self.__get_all_images_dict().keys()

    def __get_all_images_dict(self):
        all_images_dict = self.emulator_iface.list_images(
            DOCKER_REGISTRY, TITAN_IMAGE_NAME_PATTERN)
        all_images_dict.update(
            self.emulator_iface.list_images(
                DOCKER_REGISTRY, CLUSTER_IMAGE_NAME_PATTERN))
        return all_images_dict

    def __is_in_list(self, lst_one, lst_two):
        if lst_two:
            if lst_two.pop() in lst_one:
                self.__is_in_list(lst_one, lst_two)
            else:
                return False
        return True

    def __delete_useless_images(self,
                                image,
                                youngest_local_images,
                                images_fail_to_delete):
        i = re.search(r"\d{8}" + r"_\d+", image).start()
        if i:
            sub_str_image_to_delete = image[:i]
            logger.info('sub str image to delete: {}'.format(
                sub_str_image_to_delete))
            images_to_delete = [name for name in youngest_local_images
                                if sub_str_image_to_delete in name]
            logger.info('images to delete: {}'.format(
                images_to_delete))
            for img_name in images_to_delete:
                result = self.emulator_iface.delete_image(img_name)
                if result:
                    logger.info('deleted: {}'.format(img_name))
                else:
                    images_fail_to_delete.append(img_name)
                    logger.info('not deleted: {}'.format(img_name))
        return None
