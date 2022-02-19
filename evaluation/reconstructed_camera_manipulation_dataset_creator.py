import os
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from dataset.batching import single_batch_elements_collate_fn
from dataset.video_dataset import MulticameraVideoDataset
from model.utils.object_ids_helper import ObjectIDsHelper
from utils.average_meter import AverageMeter
from utils.drawing.image_helper import ImageHelper


class ReconstructedCameraManipulationDatasetCreator:
    '''
    Helper class for the creation of reconstruction quality evaluation datasets
    '''

    def __init__(self, config, dataset: MulticameraVideoDataset, logger, name="test"):
        '''

        :param config: Configuration file
        :param dataset: The dataset to reconstruct
        :param logger:
        :param name: prefix for the logger and name of the directory in the results folder where to save the reconstruction results
        '''

        self.config = config
        self.logger = logger
        self.name = name
        self.dataset = dataset

        self.dataloader = DataLoader(dataset, batch_size=self.config["evaluation"]["reconstructed_camera_manipulation_dataset_batching"]["batch_size"], shuffle=False, collate_fn=single_batch_elements_collate_fn, num_workers=self.config["evaluation"]["reconstructed_camera_manipulation_dataset_batching"]["num_workers"], pin_memory=True)

        # Directory which will serve as the root for the output
        self.output_root = os.path.join(self.config["logging"]["reconstructed_camera_manipulation_dataset_directory"], name)
        Path(self.output_root).mkdir(exist_ok=True)

        # Helper for handling the relationships between object ids and their models
        self.object_id_helper = ObjectIDsHelper(self.config)

        # Helper for loggin the images
        self.image_helper = ImageHelper(self.config, logger, name)

    def output_paths_from_observations_paths(self, observations_paths: np.ndarray):
        '''
        Gets the paths where to save reconstructed images

        :param observations_paths: (batch_size, observations_count, cameras_count) string array with location on disk of the observations. None if the observation is not stored on disk
        :return:
        '''

        # Copies to avoid modifying the original array
        observations_paths = observations_paths.copy()

        # Iterates over all paths with a writable iterator
        with np.nditer(observations_paths, flags=["refs_ok"], op_flags=['readwrite']) as iterator:
            for current_path in iterator:

                # Splits the path .../sequence_name/camera_name/file_name
                path = os.path.normpath(current_path.item()).split(os.sep)[-3:]
                # Concatenates the path with the new output root
                # output_root/sequence_name/camera_name/file_name
                translated_path = os.path.join(self.output_root, os.path.join(*path))

                current_path[...] = translated_path

        return observations_paths

    def make_folders_for_output(self, paths: np.ndarray):
        '''
        Creates a folder corresponding to each of the paths

        :param paths: (...) string array with paths to files
        :return:
        '''

        # Iterates over all directories
        with np.nditer(paths, flags=["refs_ok"]) as iterator:
            for current_path in iterator:

                directory_path = current_path.item()

                # Strips the file name from the path if it is not a directory path
                if not os.path.isdir(directory_path):
                    directory_path = os.path.normpath(current_path.item()).split(os.sep)[:-1]
                    directory_path = os.path.join(*directory_path)

                # Creates the directory
                Path(directory_path).mkdir(exist_ok=True, parents=True)

    def use_first_observation(self, tensor: torch.Tensor) -> torch.Tensor:
        '''
        Creates a tensor where the first observation is used in all observation steps

        :param object_style: (bs, observations_count, ...)
        :return: (bs, observations_count, ...) tensor with the first observation repeated in place of all observations
        '''

        observations_count = tensor.size(1)
        tensor = tensor[:, :1] # Selects the first observation

        # Repeats the first observation
        repeats = [1] * len(tensor.size())
        repeats[1] = observations_count
        tensor = tensor.repeat(repeats)

        return tensor

    def reconstruct_dataset(self, model):
        '''
        Evaluates the performances of the given model

        :param model: The model to use for dataset reconstruction
        :return:
        '''

        loss_averager = AverageMeter()
        self.logger.print(f"- Reconstructing dataset '{self.name}'")

        batches_count = len(self.dataloader)

        # Saves sample images
        with torch.no_grad():
            for batch_idx, batch in enumerate(self.dataloader):

                self.logger.print(f"-- [{batch_idx:04d}/{batches_count:04d}] [{datetime.now()}] Reconstructing batch")

                # Performs inference
                batch_tuple = batch.to_tuple()
                observations, actions, rewards, dones, camera_rotations, camera_translations, focals, bounding_boxes, bounding_boxes_validity, global_frame_indexes, video_frame_indexes, video_indexes = batch_tuple
                observations_paths = batch.observations_paths  # Paths where the current observations are stored on disk

                scene_encoding = model(observations, camera_rotations, camera_translations, focals, bounding_boxes, bounding_boxes_validity, global_frame_indexes, video_frame_indexes, video_indexes, shuffle_style=False, mode="observations_scene_encoding_only")

                # Keys in the scene encoding for which the values in the first frame should be used
                repeat_keys = ["object_rotation_parameters", "object_translation_parameters", "object_style", "object_deformation"]
                # Makes use of the first observation values
                for key in repeat_keys:
                    scene_encoding[key] = self.use_first_observation(scene_encoding[key])

                height = observations.size(-2)
                width = observations.size(-1)
                image_size = (height, width)

                object_rotation_parameters = scene_encoding["object_rotation_parameters"]
                object_translation_parameters = scene_encoding["object_translation_parameters"]
                object_style = scene_encoding["object_style"]
                object_deformation = scene_encoding["object_deformation"]
                object_in_scene = scene_encoding["object_in_scene"]

                render_results = model.module.render_full_frame_from_scene_encoding(camera_rotations, camera_translations, focals, image_size, object_rotation_parameters, object_translation_parameters, object_style, object_deformation, object_in_scene, perturb=False)

                # Gets output filenames and creates output directories for the current batch
                output_paths = self.output_paths_from_observations_paths(observations_paths)
                self.make_folders_for_output(output_paths)

                self.image_helper.save_reconstructed_images_to_paths(render_results, output_paths)

        self.logger.print(f"- Syncing metadata '{self.name}'")

        # Uses rsync to sync the dataset metadata
        original_dataset_directory = os.path.join(self.config["evaluation"]["reconstructed_camera_manipulation_dataset_path"], self.name) + "/"
        rsync_args = ["rsync", "-a", "--ignore-times", "--exclude", "*.png", original_dataset_directory, self.output_root]  # Forces to overwrite files independently from time
        subprocess.run(rsync_args)

        self.logger.print(f"- Done reconstructing dataset '{self.name}'")

        return


def dataset_creator(config, dataset: MulticameraVideoDataset, logger, name="test"):
    return ReconstructedCameraManipulationDatasetCreator(config, dataset, logger, name)
