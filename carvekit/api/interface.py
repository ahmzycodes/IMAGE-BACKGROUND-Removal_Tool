from pathlib import Path
from typing import Union, List, Optional

from PIL import Image

from carvekit.ml.wrap.basnet import BASNET
from carvekit.ml.wrap.deeplab_v3 import DeepLabV3
from carvekit.ml.wrap.u2net import U2NET
from carvekit.ml.wrap.tracer_b7 import TracerUniversalB7
from carvekit.pipelines.preprocessing import PreprocessingStub
from carvekit.pipelines.postprocessing import MattingMethod
from carvekit.utils.image_utils import load_image
from carvekit.utils.mask_utils import apply_mask
from carvekit.utils.pool_utils import thread_pool_processing


class Interface:
    def __init__(
        self,
        seg_pipe: Union[U2NET, BASNET, DeepLabV3, TracerUniversalB7],
        pre_pipe: Optional[Union[PreprocessingStub]] = None,
        post_pipe: Optional[Union[MattingMethod]] = None,
        device="cpu",
    ):
        """
        Initializes an object for interacting with pipelines and other components of the CarveKit framework.

        Args:
            pre_pipe: Initialized pre-processing pipeline object
            seg_pipe: Initialized segmentation network object
            post_pipe: Initialized postprocessing pipeline object
            device: The processing device that will be used to apply the masks to the images.
        """
        self.device = device
        self.preprocessing_pipeline = pre_pipe
        self.segmentation_pipeline = seg_pipe
        self.postprocessing_pipeline = post_pipe

    def __call__(
        self, images: List[Union[str, Path, Image.Image]]
    ) -> List[Image.Image]:
        """
        Removes the background from the specified images.

        Args:
            images: list of input images

        Returns:
            List of images without background as PIL.Image.Image instances
        """
        images = thread_pool_processing(load_image, images)
        if self.preprocessing_pipeline is not None:
            masks: List[Image.Image] = self.preprocessing_pipeline(
                interface=self, images=images
            )
        else:
            masks: List[Image.Image] = self.segmentation_pipeline(images=images)

        if self.postprocessing_pipeline is not None:
            images: List[Image.Image] = self.postprocessing_pipeline(
                images=images, masks=masks
            )
        else:
            images = list(
                map(
                    lambda x: apply_mask(
                        image=images[x], mask=masks[x], device=self.device
                    ),
                    range(len(images)),
                )
            )
        return images
