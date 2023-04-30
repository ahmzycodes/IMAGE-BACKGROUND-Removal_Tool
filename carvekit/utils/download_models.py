import hashlib
import os
import warnings
from abc import ABCMeta, abstractmethod, ABC
from pathlib import Path
from typing import Optional

import carvekit
from carvekit.ml.files import checkpoints_dir

import requests
import tqdm

requests = requests.Session()
requests.headers.update({"User-Agent": f"Carvekit/{carvekit.version}"})

MODELS_URLS = {
    "basnet.pth": {
        "repository": "Carve/basnet-universal",
        "revision": "870becbdb364fda6d8fdb2c10b072542f8d08701",
        "filename": "basnet.pth",
    },
    "deeplab.pth": {
        "repository": "Carve/deeplabv3-resnet101",
        "revision": "d504005392fc877565afdf58aad0cd524682d2b0",
        "filename": "deeplab.pth",
    },
    "fba_matting.pth": {
        "repository": "Carve/fba",
        "revision": "a5d3457df0fb9c88ea19ed700d409756ca2069d1",
        "filename": "fba_matting.pth",
    },
    "u2net.pth": {
        "repository": "Carve/u2net-universal",
        "revision": "10305d785481cf4b2eee1d447c39cd6e5f43d74b",
        "filename": "full_weights.pth",
    },
    "tracer_b7.pth": {
        "repository": "Carve/tracer_b7",
        "revision": "d8a8fd9e7b3fa0d2f1506fe7242966b34381e9c5",
        "filename": "tracer_b7.pth",
    },
    "tracer_hair.pth": {
        "repository": "Carve/tracer_b7",
        "revision": "d8a8fd9e7b3fa0d2f1506fe7242966b34381e9c5",
        "filename": "tracer_b7.pth",  # TODO don't forget change this link!!
    },
}

MODELS_CHECKSUMS = {
    "basnet.pth": "e409cb709f4abca87cb11bd44a9ad3f909044a917977ab65244b4c94dd33"
    "8b1a37755c4253d7cb54526b7763622a094d7b676d34b5e6886689256754e5a5e6ad",
    "deeplab.pth": "9c5a1795bc8baa267200a44b49ac544a1ba2687d210f63777e4bd715387324469a59b072f8a28"
    "9cc471c637b367932177e5b312e8ea6351c1763d9ff44b4857c",
    "fba_matting.pth": "890906ec94c1bfd2ad08707a63e4ccb0955d7f5d25e32853950c24c78"
    "4cbad2e59be277999defc3754905d0f15aa75702cdead3cfe669ff72f08811c52971613",
    "u2net.pth": "16f8125e2fedd8c85db0e001ee15338b4aa2fda77bab8ba70c25e"
    "bea1533fda5ee70a909b934a9bd495b432cef89d629f00a07858a517742476fa8b346de24f7",
    "tracer_b7.pth": "c439c5c12d4d43d5f9be9ec61e68b2e54658a541bccac2577ef5a54fb252b6e8415d41f7e"
    "c2487033d0c02b4dd08367958e4e62091318111c519f93e2632be7b",
    "tracer_hair.pth": "5c2fb9973fc42fa6208920ffa9ac233cc2ea9f770b24b4a96969d3449aed7ac89e6d37e"
    "e486a13e63be5499f2df6ccef1109e9e8797d1326207ac89b2f39a7cf",
}


def sha512_checksum_calc(file: Path) -> str:
    """
    Calculates the SHA512 hash digest of a file on fs

    Args:
        file: Path to the file

    Returns:
        SHA512 hash digest of a file.
    """
    dd = hashlib.sha512()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            dd.update(chunk)
    return dd.hexdigest()


class CachedDownloader:
    __metaclass__ = ABCMeta

    @property
    @abstractmethod
    def name(self) -> str:
        return self.__class__.__name__

    @property
    @abstractmethod
    def fallback_downloader(self) -> Optional["CachedDownloader"]:
        pass

    def download_model(self, file_name: str) -> Path:
        try:
            return self.download_model_base(file_name)
        except BaseException as e:
            if self.fallback_downloader is not None:
                warnings.warn(
                    f"Failed to download model from {self.name} downloader."
                    f" Trying to download from {self.fallback_downloader.name} downloader."
                )
                return self.fallback_downloader.download_model(file_name)
            else:
                warnings.warn(
                    f"Failed to download model from {self.name} downloader."
                    f" No fallback downloader available."
                )
                raise e

    @abstractmethod
    def download_model_base(self, file_name: str) -> Path:
        """Download model from any source if not cached. Returns path if cached"""

    def __call__(self, file_name: str):
        return self.download_model(file_name)


class HuggingFaceCompatibleDownloader(CachedDownloader, ABC):
    def __init__(
        self,
        name: str = "Huggingface.co",
        base_url: str = "https://huggingface.co",
        fb_downloader: Optional["CachedDownloader"] = None,
    ):
        self.cache_dir = checkpoints_dir
        self.base_url = base_url
        self._name = name
        self._fallback_downloader = fb_downloader

    @property
    def fallback_downloader(self) -> Optional["CachedDownloader"]:
        return self._fallback_downloader

    @property
    def name(self):
        return self._name

    def check_for_existence(self, file_name: str) -> Optional[Path]:
        if file_name not in MODELS_URLS.keys():
            raise FileNotFoundError("Unknown model!")
        path = (
            self.cache_dir
            / MODELS_URLS[file_name]["repository"].split("/")[1]
            / file_name
        )

        if not path.exists():
            return None

        if MODELS_CHECKSUMS[path.name] != sha512_checksum_calc(path):
            warnings.warn(
                f"Invalid checksum for model {path.name}. Downloading correct model!"
            )
            os.remove(path)
            return None
        return path

    def download_model_base(self, file_name: str) -> Path:
        cached_path = self.check_for_existence(file_name)
        if cached_path is not None:
            return cached_path
        else:
            cached_path = (
                self.cache_dir
                / MODELS_URLS[file_name]["repository"].split("/")[1]
                / file_name
            )
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            url = MODELS_URLS[file_name]
            hugging_face_url = f"{self.base_url}/{url['repository']}/resolve/{url['revision']}/{url['filename']}"

            try:
                r = requests.get(hugging_face_url, stream=True, timeout=10)
                if r.status_code < 400:
                    with open(cached_path, "wb") as f:
                        r.raw.decode_content = True
                        for chunk in tqdm.tqdm(
                            r,
                            desc="Downloading " + cached_path.name + " model",
                            colour="blue",
                        ):
                            f.write(chunk)
                else:
                    if r.status_code == 404:
                        raise FileNotFoundError(f"Model {file_name} not found!")
                    else:
                        raise ConnectionError(
                            f"Error {r.status_code} while downloading model {file_name}!"
                        )
            except BaseException as e:
                if cached_path.exists():
                    os.remove(cached_path)
                raise ConnectionError(
                    f"Exception caught when downloading model! "
                    f"Model name: {cached_path.name}. Exception: {str(e)}."
                )
            return cached_path


fallback_downloader: CachedDownloader = HuggingFaceCompatibleDownloader()
downloader: CachedDownloader = HuggingFaceCompatibleDownloader(
    base_url="https://cdn.carve.photos",
    fb_downloader=fallback_downloader,
    name="Carve CDN",
)
downloader._fallback_downloader = fallback_downloader
