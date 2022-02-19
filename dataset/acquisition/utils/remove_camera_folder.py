import argparse
import glob
import os
import shutil


def remove_camera_folder(path: str):
    '''
    Removes a camera folder inside the given folder
    :param current_video_path:
    :return:
    '''

    camera_folder_name = "00000"
    camera_folder_path = os.path.join(path, camera_folder_name)

    all_files = glob.glob(os.path.join(camera_folder_path, "*"))

    for current_file in all_files:
        basename = os.path.basename(current_file)
        new_location = os.path.join(path, basename)
        print(f"Moving {current_file} to {new_location}")
        os.rename(current_file, new_location)

    shutil.rmtree(camera_folder_path)


if __name__ == "__main__":

    # Loads configuration file
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=str, required=True)

    arguments = parser.parse_args()

    root_directory = arguments.directory

    top_level_directories = glob.glob(os.path.join(root_directory, "*"))
    # Elaborates each top level directory
    for current_top_level_directory in top_level_directories:
        if not os.path.isdir(current_top_level_directory):
            continue

        # Gets all video
        video_paths_list = sorted(glob.glob(os.path.join(current_top_level_directory, "*")))
        video_paths_list = [current_path for current_path in video_paths_list if os.path.isdir(current_path)]

        for current_video_path in video_paths_list:
            remove_camera_folder(current_video_path)























