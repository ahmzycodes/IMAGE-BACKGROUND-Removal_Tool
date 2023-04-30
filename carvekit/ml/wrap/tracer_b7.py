"""
Source url: https://github.com/OPHoperHPO/image-background-remove-tool
Author: Nikita Selin (OPHoperHPO)[https://github.com/OPHoperHPO].
License: Apache License 2.0
"""
import pathlib
import warnings
from typing import List, Union
import PIL.Image
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image

from carvekit.ml.arch.tracerb7.tracer import TracerDecoder
from carvekit.ml.arch.tracerb7.efficientnet import EfficientEncoderB7
from carvekit.ml.files.models_loc import tracer_b7_pretrained, tracer_hair_pretrained
from carvekit.utils.models_utils import get_precision_autocast, cast_network
from carvekit.utils.image_utils import load_image, convert_image
from carvekit.utils.pool_utils import thread_pool_processing, batch_generator

__all__ = ["TracerUniversalB7"]


class TracerUniversalB7(TracerDecoder):
    """TRACER B7 model interface"""

    def __init__(
        self,
        device="cpu",
        input_image_size: Union[List[int], int] = 640,
        batch_size: int = 4,
        load_pretrained: bool = True,
        fp16: bool = False,
        model_path: Union[str, pathlib.Path] = None,
    ):
        """
        Initialize the U2NET model

        Args:
            layers_cfg: neural network layers configuration
            device: processing device
            input_image_size: input image size
            batch_size: the number of images that the neural network processes in one run
            load_pretrained: loading pretrained model
            fp16: use fp16 precision

        """
        if model_path is None:
            model_path = tracer_b7_pretrained()
        super(TracerUniversalB7, self).__init__(
            encoder=EfficientEncoderB7(),
            rfb_channel=[32, 64, 128],
            features_channels=[48, 80, 224, 640],
        )

        self.fp16 = fp16
        self.device = device
        self.batch_size = batch_size
        if isinstance(input_image_size, list):
            self.input_image_size = input_image_size[:2]
        else:
            self.input_image_size = (input_image_size, input_image_size)

        self.transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Resize(self.input_image_size),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        self.to(device)
        if load_pretrained:
            # TODO remove edge detector from weights. It doesn't work well with this model!
            self.load_state_dict(
                torch.load(model_path, map_location=self.device), strict=False
            )
        self.eval()

    def data_preprocessing(self, data: PIL.Image.Image) -> torch.FloatTensor:
        """
        Transform input image to suitable data format for neural network

        Args:
            data: input image

        Returns:
            input for neural network

        """

        return torch.unsqueeze(self.transform(data), 0).type(torch.FloatTensor)

    @staticmethod
    def data_postprocessing(
        data: torch.tensor, original_image: PIL.Image.Image
    ) -> PIL.Image.Image:
        """
        Transforms output data from neural network to suitable data
        format for using with other components of this framework.

        Args:
            data: output data from neural network
            original_image: input image which was used for predicted data

        Returns:
            Segmentation mask as PIL Image instance

        """
        output = (data.type(torch.FloatTensor).detach().cpu().numpy() * 255.0).astype(
            np.uint8
        )
        output = output.squeeze(0)
        mask = Image.fromarray(output).convert("L")
        mask = mask.resize(original_image.size, resample=Image.BILINEAR)
        return mask

    def __call__(
        self, images: List[Union[str, pathlib.Path, PIL.Image.Image]]
    ) -> List[PIL.Image.Image]:
        """
        Passes input images though neural network and returns segmentation masks as PIL.Image.Image instances

        Args:
            images: input images

        Returns:
            segmentation masks as for input images, as PIL.Image.Image instances

        """
        collect_masks = []
        autocast, dtype = get_precision_autocast(device=self.device, fp16=self.fp16)
        with autocast:
            cast_network(self, dtype)
            for image_batch in batch_generator(images, self.batch_size):
                images = thread_pool_processing(
                    lambda x: convert_image(load_image(x)), image_batch
                )
                batches = torch.vstack(
                    thread_pool_processing(self.data_preprocessing, images)
                )
                with torch.no_grad():
                    batches = batches.to(self.device)
                    masks = super(TracerDecoder, self).__call__(batches)
                    masks_cpu = masks.cpu()
                    del batches, masks
                masks = thread_pool_processing(
                    lambda x: self.data_postprocessing(masks_cpu[x], images[x]),
                    range(len(images)),
                )
                collect_masks += masks

        return collect_masks


class TracerHair(TracerUniversalB7):
    """TRACER HAIR model interface"""

    def __init__(
        self,
        device="cpu",
        input_image_size: Union[List[int], int] = 640,
        batch_size: int = 4,
        load_pretrained: bool = True,
        fp16: bool = False,
        model_path: Union[str, pathlib.Path] = None,
    ):
        if model_path is None:
            model_path = tracer_hair_pretrained()
        warnings.warn("TracerHair has not public model yet. Don't use it!", UserWarning)
        super(TracerHair, self).__init__(
            device=device,
            input_image_size=input_image_size,
            batch_size=batch_size,
            load_pretrained=load_pretrained,
            fp16=fp16,
            model_path=model_path,
        )
