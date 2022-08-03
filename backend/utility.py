import logging
import re

from emulator import TITAN_IMAGE_NAME_PATTERN
from emulator import CLUSTER_IMAGE_NAME_PATTERN
from emulator import IMAGE_BUILD_TYPES

logger = logging.getLogger(__name__)


class utility:

    @staticmethod
    def search_youngest_images(search_in, search_num_of_youngest=1):
        '''Returns the list of images which contains sum of preassigned number
               of the youngest images for each build type below
               (ex.: cloud_android_11_release... - first group to search in
                     cloud_android_11_db... - second group to search in
                     cloud_android_11_preint... - third group to search in
                     cloud_android_12_release... - fourth group to search in
                     ...)
               input:
                     search_in - list of all images where to search
                     search_num_of_youngest - number of images to search
                     per each group mentioned above'''
        by_ver = []
        utility.__group_by_platform_ver(by_ver, search_in)
        logger.info('by_ver is: {}'.
                    format(by_ver) + '\n')
        the_youngest_images = []
        for items in by_ver:
            for build_type in IMAGE_BUILD_TYPES:
                depth = search_num_of_youngest
                the_youngest_image = None
                images_by_type = [name for name in items
                                  if build_type.casefold() in name.casefold()]
                logger.info('images_by_type is: {}'.
                            format(images_by_type) + '\n')
                while depth > 0 and images_by_type:
                    the_youngest_date = 0
                    same_date_images = []
                    for name in images_by_type:
                        date = utility.__get_image_date(name)
                        if date:
                            if date > the_youngest_date:
                                same_date_images.clear()
                                same_date_images.append(name)
                                the_youngest_date = date
                            if date == the_youngest_date:
                                same_date_images.append(name)
                    if len(same_date_images) > 1:
                        ver_of_build = 0
                        for name in same_date_images:
                            ver = int(name.split('_')[-1])
                            if ver > ver_of_build:
                                ver_of_build = ver
                                the_youngest_image = name
                    elif len(same_date_images) == 1:
                        the_youngest_image = the_youngest_images[0]
                    if the_youngest_image:
                        logger.info('the_youngest_image is: {}'.
                                    format(the_youngest_image) + '\n')
                        the_youngest_images.append(the_youngest_image)
                        images_by_type.remove(the_youngest_image)
                        depth = depth - 1
        return the_youngest_images

    @staticmethod
    def __group_by_platform_ver(by_ver, search_in):
        '''Split images in search_in list by platform version
               (ex.: android_cloud_11_... - first group,
                     android_cloud_12_... - second group,
                     cluster_cloud_... - third group)
               input:
                     search_in - list of images to search in
                     by_ver - list to store groups by platform version'''
        for pattern in [TITAN_IMAGE_NAME_PATTERN, CLUSTER_IMAGE_NAME_PATTERN]:
            by_pattern = [name for name in search_in
                          if pattern in name]
            logger.info('by_pattern is: {}'.format(by_pattern) + '\n')
            reg_exp = r"" + pattern + r"_(\d+).*"
            curr_ver = 0
            prev_ver = 0
            if by_pattern:
                for name in by_pattern:
                    search = re.search(reg_exp, name)
                    if search is not None:
                        curr_ver = int(search.group(1))
                        if curr_ver != prev_ver:
                            ver_lst = [name for name in by_pattern
                                       if pattern + '_'
                                       + str(curr_ver) in name]
                            if len(ver_lst) > 0:
                                by_pattern = [name for name in by_pattern
                                              if name not in ver_lst]
                                search_in = [name for name in search_in
                                             if name not in ver_lst]
                                if curr_ver < prev_ver:
                                    by_ver.append(ver_lst)
                                else:
                                    by_ver.insert(0, ver_lst)
                                prev_ver = curr_ver
                    else:
                        images_with_no_ver = [name for name in by_pattern
                                              if pattern + '_' in name]
                        if len(images_with_no_ver) > 0:
                            by_ver.append(images_with_no_ver)
                            by_pattern = [name for name in by_pattern
                                          if name not in images_with_no_ver]
                            search_in = [name for name in search_in
                                         if name not in images_with_no_ver]
        return None

    @staticmethod
    def __get_image_date(image_name):
        search_result = re.search(r'\d{8}', image_name)
        if search_result is not None:
            date = int(search_result.group(0))
            return date
        else:
            return None

    @staticmethod
    def filter_remote_img_by_youngest(images_dict, search_num_of_youngest):
        '''Filters out remote images so only certain number of remote images
           per each category are left in the resulting dict.
           Local images are left unchanged. The number of the remote images
           left per category is set by arg search_num_of_youngest.
           Remote images categories are determined in total 9 cats:
           [build_type:db|preint|release]x[android_version:11|12]+[cluster]'''
        all_locals_dict = {k: v for (k, v) in images_dict.items()
                           if 'Remote' not in v}
        all_remotes_dict = {k: v for (k, v) in images_dict.items()
                            if 'Remote' in v}
        youngest_remote_images = utility.search_youngest_images(
            all_remotes_dict.keys(),
            search_num_of_youngest)
        logger.info('{} youngest remote images in each build category: {}'
                    .format(search_num_of_youngest, youngest_remote_images))
        all_remotes_dict = {k: 'Remote' for k in youngest_remote_images}
        result = all_locals_dict
        result.update(all_remotes_dict)
        return result
