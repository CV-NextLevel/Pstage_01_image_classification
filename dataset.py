import os
import random
from collections import defaultdict
from enum import Enum
from typing import Tuple, List
import numpy as np
import torch
from PIL import Image
from PIL import ImageEnhance
from torch.utils.data import Dataset, Subset, random_split
from torchvision.transforms import *
from torch.optim.lr_scheduler import StepLR
from PIL import ImageEnhance

IMG_EXTENSIONS = [
    ".jpg", ".JPG", ".jpeg", ".JPEG", ".png",
    ".PNG", ".ppm", ".PPM", ".bmp", ".BMP",
]


def is_image_file(filename):
    '''
    IMG_EXTENSIONS에 있는 확장자 중 하나라도 파일명에 있다면 반환
        endswith : 문자열이 지정 문자열로 끝나는지 체크
    '''
    return any(filename.endswith(extension) for extension in IMG_EXTENSIONS)


class BaseAugmentation:
    def __init__(self, resize, mean, std, **args):
        self.transform = Compose([
            Resize(resize, Image.BILINEAR),
            ToTensor(),
            Normalize(mean=mean, std=std),
        ])

    def __call__(self, image):
        return self.transform(image)


class AddGaussianNoise(object):
    """
        transform 에 없는 기능들은 이런식으로 __init__, __call__, __repr__ 부분을
        직접 구현하여 사용할 수 있습니다.
    """

    def __init__(self, mean=0., std=1.):
        self.std = std
        self.mean = mean

    def __call__(self, tensor):
        return tensor + torch.randn(tensor.size()) * self.std + self.mean

    def __repr__(self):
        return self.__class__.__name__ + '(mean={0}, std={1})'.format(self.mean, self.std)

class CustomAugmentation:
    def __init__(self, resize, mean, std, **args):
        self.transform = Compose([
            CenterCrop((320, 256)),
            Resize(resize, Image.BILINEAR),
            ColorJitter(0.1, 0.1, 0.1, 0.1),
            ToTensor(),
            Normalize(mean=mean, std=std),
            AddGaussianNoise() #이거 넣으면 별로임
        ])

    def __call__(self, image):
        return self.transform(image)

class bestAugmentation:
    def __init__(self, resize, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), **args):
        self.transform = Compose([
            CenterCrop((380,380)),
            RandomApply([transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.2)], p=1),
            RandomApply([transforms.RandomHorizontalFlip(p=0.5)], p=1),
            ToTensor(),
            Normalize(mean=mean, std=std)
        ])

    def __call__(self, image):
        return self.transform(image)


class MaskLabels(int, Enum):
    MASK = 0
    INCORRECT = 1
    NORMAL = 2


class GenderLabels(int, Enum):
    MALE = 0
    FEMALE = 1

    @classmethod
    def from_str(cls, value: str) -> int:
        value = value.lower()
        if value == "male":
            return cls.MALE
        elif value == "female":
            return cls.FEMALE
        else:
            raise ValueError(f"Gender value should be either 'male' or 'female', {value}")


class AgeLabels(int, Enum):
    YOUNG = 0
    MIDDLE = 1
    OLD = 2

    @classmethod
    def from_number(cls, value: str) -> int:
        try:
            value = int(value)
        except Exception:
            raise ValueError(f"Age value should be numeric, {value}")

        if value < 30:
            return cls.YOUNG
        elif value < 60:
            return cls.MIDDLE
        else:
            return cls.OLD


class MaskBaseDataset(Dataset):
    num_classes = 3 * 2 * 3

    _file_names = {
        "mask1": MaskLabels.MASK,
        "mask2": MaskLabels.MASK,
        "mask3": MaskLabels.MASK,
        "mask4": MaskLabels.MASK,
        "mask5": MaskLabels.MASK,
        "incorrect_mask": MaskLabels.INCORRECT,
        "normal": MaskLabels.NORMAL
    }

    image_paths = []
    mask_labels = []
    gender_labels = []
    age_labels = []

    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.data_dir = data_dir
        self.mean = mean
        self.std = std
        self.val_ratio = val_ratio

        self.transform = None
        self.outlier_remove = outlier_remove
        self.setup()
        self.calc_statistics()

    def setup(self):
        profiles = os.listdir(self.data_dir)
        for profile in profiles:
            if profile.startswith("."):  # "." 로 시작하는 파일은 무시합니다
                continue

            img_folder = os.path.join(self.data_dir, profile)
            for file_name in os.listdir(img_folder):
                _file_name, ext = os.path.splitext(file_name)
                if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                    continue

                img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                mask_label = self._file_names[_file_name]

                id, gender, race, age = profile.split("_")
                if self.outlier_remove:
                    sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
                    if id in sex_mislabeled_profiles:
                        if gender == 'male':
                            gender == 'female'
                        else:
                            gender == 'male'
                gender_label = GenderLabels.from_str(gender)
                age_label = AgeLabels.from_number(age)

                self.image_paths.append(img_path)
                self.mask_labels.append(mask_label)
                self.gender_labels.append(gender_label)
                self.age_labels.append(age_label)

    def calc_statistics(self):
        has_statistics = self.mean is not None and self.std is not None
        if not has_statistics:
            print("[Warning] Calculating statistics... It can take a long time depending on your CPU machine")
            sums = []
            squared = []
            for image_path in self.image_paths[:3000]:
                image = np.array(Image.open(image_path)).astype(np.int32)
                sums.append(image.mean(axis=(0, 1)))
                squared.append((image ** 2).mean(axis=(0, 1)))

            self.mean = np.mean(sums, axis=0) / 255
            self.std = (np.mean(squared, axis=0) - self.mean ** 2) ** 0.5 / 255

    def set_transform(self, transform):
        self.transform = transform

    def __getitem__(self, index):
        assert self.transform is not None, ".set_tranform 메소드를 이용하여 transform 을 주입해주세요"

        image = self.read_image(index)
        mask_label = self.get_mask_label(index)
        gender_label = self.get_gender_label(index)
        age_label = self.get_age_label(index)
        multi_class_label = self.encode_multi_class(mask_label, gender_label, age_label)

        image_transform = self.transform(image)
        return image_transform, multi_class_label

    def __len__(self):
        return len(self.image_paths)

    def get_mask_label(self, index) -> MaskLabels:
        '''
        지정된 인덱스의 마스크 라벨을 반환합니다.
        '''
        return self.mask_labels[index]

    def get_gender_label(self, index) -> GenderLabels:
        '''
        지정된 인덱스의 성별 라벨을 반환합니다.
        '''
        return self.gender_labels[index]

    def get_age_label(self, index) -> AgeLabels:
        '''
        지정된 인덱스의 나이 라벨을 반환합니다.
        '''
        return self.age_labels[index]

    def read_image(self, index):
        '''
        지정된 인덱스의 이미지 데이터를 읽어들입니다.
        '''
        image_path = self.image_paths[index]
        return Image.open(image_path)

    @staticmethod
    def encode_multi_class(mask_label, gender_label, age_label) -> int:
        '''
        다중 클래스 분류를 위해 세 개의 라벨을 하나의 숫자로 인코딩
        '''
        return mask_label * 6 + gender_label * 3 + age_label

    @staticmethod
    def decode_multi_class(multi_class_label) -> Tuple[MaskLabels, GenderLabels, AgeLabels]:
        '''
        인코딩된 숫자를 세 개의 라벨로 디코딩
        '''
        mask_label = (multi_class_label // 6) % 3
        gender_label = (multi_class_label // 3) % 2
        age_label = multi_class_label % 3
        return mask_label, gender_label, age_label

    @staticmethod
    def denormalize_image(image, mean, std):
        '''
        이미지의 정규화된 값을 원래 픽셀 값으로 변환합니다.
        '''
        img_cp = image.copy()
        img_cp *= std
        img_cp += mean
        img_cp *= 255.0
        img_cp = np.clip(img_cp, 0, 255).astype(np.uint8)
        return img_cp

    def split_dataset(self) -> Tuple[Subset, Subset]:
        """
        데이터셋을 train 과 val 로 나눕니다,
        pytorch 내부의 torch.utils.data.random_split 함수를 사용하여
        torch.utils.data.Subset 클래스 둘로 나눕니다.
        구현이 어렵지 않으니 구글링 혹은 IDE (e.g. pycharm) 의 navigation 기능을 통해 코드를 한 번 읽어보는 것을 추천드립니다^^
        """
        n_val = int(len(self) * self.val_ratio)
        n_train = len(self) - n_val
        train_set, val_set = random_split(self, [n_train, n_val])
        return train_set, val_set
    

class MaskDataset(Dataset):
    num_classes = 3

    _file_names = {
        "mask1": MaskLabels.MASK,
        "mask2": MaskLabels.MASK,
        "mask3": MaskLabels.MASK,
        "mask4": MaskLabels.MASK,
        "mask5": MaskLabels.MASK,
        "incorrect_mask": MaskLabels.INCORRECT,
        "normal": MaskLabels.NORMAL
    }

    
    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.data_dir = data_dir
        self.mean = mean
        self.std = std
        self.val_ratio = val_ratio
        self.image_paths = []
        self.mask_labels = []
        
#         self.gender_labels = []
#         self.age_labels = []
        self.outlier_remove = outlier_remove
        
        self.label_paths = {i:[] for i in range(3)} # MASK = 0, INCORRECT = 1, NORMAL = 2
        
        self.transform = None
        self.setup()
        self.calc_statistics()
        

    def setup(self):
        profiles = os.listdir(self.data_dir)
        for profile in profiles:
            if profile.startswith("."):  # "." 로 시작하는 파일은 무시합니다
                continue

            img_folder = os.path.join(self.data_dir, profile)
            for file_name in os.listdir(img_folder):
                _file_name, ext = os.path.splitext(file_name)
                if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                    continue

                img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                
                mask_label = self._file_names[_file_name]

                id, gender, race, age = profile.split("_")
                if self.outlier_remove:
                    sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
                    if id in sex_mislabeled_profiles:
                        if gender == 'male':
                            gender == 'female'
                        else:
                            gender == 'male'
#                 gender_label = GenderLabels.from_str(gender)
#                 age_label = AgeLabels.from_number(age)

                self.image_paths.append(img_path)
                self.mask_labels.append(mask_label)
#                 self.gender_labels.append(gender_label)
#                 self.age_labels.append(age_label)
#                 idx = MaskBaseDataset.encode_multi_class(mask_label, gender_label, age_label) 
                self.label_paths[mask_label].append(img_path)

    def calc_statistics(self):
        has_statistics = self.mean is not None and self.std is not None
        if not has_statistics:
            print("[Warning] Calculating statistics... It can take a long time depending on your CPU machine")
            sums = []
            squared = []
            for image_path in self.image_paths[:3000]:
                image = np.array(Image.open(image_path)).astype(np.int32)
                sums.append(image.mean(axis=(0, 1)))
                squared.append((image ** 2).mean(axis=(0, 1)))

            self.mean = np.mean(sums, axis=0) / 255
            self.std = (np.mean(squared, axis=0) - self.mean ** 2) ** 0.5 / 255

    def set_transform(self, transform):
        self.transform = transform

    def __getitem__(self, index):
        assert self.transform is not None, ".set_tranform 메소드를 이용하여 transform 을 주입해주세요"

        image = self.read_image(index)
        mask_label = self.get_mask_label(index)
#         gender_label = self.get_gender_label(index)
#         age_label = self.get_age_label(index)
#         multi_class_label = self.encode_multi_class(mask_label, gender_label, age_label)

        image_transform = self.transform(image)
        return image_transform, mask_label

    def __len__(self):
        return len(self.image_paths)

    def get_mask_label(self, index) -> MaskLabels:
        '''
        지정된 인덱스의 마스크 라벨을 반환합니다.
        '''
        return self.mask_labels[index]

#     def get_gender_label(self, index) -> GenderLabels:
#         '''
#         지정된 인덱스의 성별 라벨을 반환합니다.
#         '''
#         return self.gender_labels[index]

#     def get_age_label(self, index) -> AgeLabels:
#         '''
#         지정된 인덱스의 나이 라벨을 반환합니다.
#         '''
#         return self.age_labels[index]

    def read_image(self, index):
        '''
        지정된 인덱스의 이미지 데이터를 읽어들입니다.
        '''
        image_path = self.image_paths[index]
        return Image.open(image_path)

#     @staticmethod
#     def encode_multi_class(mask_label, gender_label, age_label) -> int:
#         '''
#         다중 클래스 분류를 위해 세 개의 라벨을 하나의 숫자로 인코딩
#         '''
#         return mask_label * 6 + gender_label * 3 + age_label

#     @staticmethod
#     def decode_multi_class(multi_class_label) -> Tuple[MaskLabels, GenderLabels, AgeLabels]:
#         '''
#         인코딩된 숫자를 세 개의 라벨로 디코딩
#         '''
#         mask_label = (multi_class_label // 6) % 3
#         gender_label = (multi_class_label // 3) % 2
#         age_label = multi_class_label % 3
#         return mask_label, gender_label, age_label

    @staticmethod
    def denormalize_image(image, mean, std):
        '''
        이미지의 정규화된 값을 원래 픽셀 값으로 변환합니다.
        '''
        img_cp = image.copy()
        img_cp *= std
        img_cp += mean
        img_cp *= 255.0
        img_cp = np.clip(img_cp, 0, 255).astype(np.uint8)
        return img_cp

    def split_dataset(self) -> Tuple[Subset, Subset]:
        """
        데이터셋을 train 과 val 로 나눕니다,
        pytorch 내부의 torch.utils.data.random_split 함수를 사용하여
        torch.utils.data.Subset 클래스 둘로 나눕니다.
        구현이 어렵지 않으니 구글링 혹은 IDE (e.g. pycharm) 의 navigation 기능을 통해 코드를 한 번 읽어보는 것을 추천드립니다^^
        """
        n_val = int(len(self) * self.val_ratio)
        n_train = len(self) - n_val
        train_set, val_set = random_split(self, [n_train, n_val])
        return train_set, val_set
    

class GenderDataset(Dataset):
    num_classes = 2
    
    _file_names = {
        "mask1": MaskLabels.MASK,
        "mask2": MaskLabels.MASK,
        "mask3": MaskLabels.MASK,
        "mask4": MaskLabels.MASK,
        "mask5": MaskLabels.MASK,
        "incorrect_mask": MaskLabels.INCORRECT,
        "normal": MaskLabels.NORMAL
    }
    
    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.data_dir = data_dir
        self.mean = mean
        self.std = std
        self.val_ratio = val_ratio
        self.image_paths = []
#         self.mask_labels = []
        self.gender_labels = []
#         self.age_labels = []
        self.outlier_remove = outlier_remove
        
        self.label_paths = {i:[] for i in range(2)} # male 0, female 1
        
        self.transform = None
        self.setup()
        self.calc_statistics()
        

    def setup(self):
        profiles = os.listdir(self.data_dir)
        for profile in profiles:
            if profile.startswith("."):  # "." 로 시작하는 파일은 무시합니다
                continue

            img_folder = os.path.join(self.data_dir, profile)
            for file_name in os.listdir(img_folder):
                _file_name, ext = os.path.splitext(file_name)
                if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                    continue

                img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                
#                 mask_label = self._file_names[_file_name]

                id, gender, race, age = profile.split("_")
                if self.outlier_remove:
                    sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
                    if id in sex_mislabeled_profiles:
                        if gender == 'male':
                            gender == 'female'
                        else:
                            gender == 'male'
                gender_label = GenderLabels.from_str(gender)
#                 age_label = AgeLabels.from_number(age)

                self.image_paths.append(img_path)
#                 self.mask_labels.append(mask_label)
                self.gender_labels.append(gender_label)
#                 self.age_labels.append(age_label)
#                 idx = MaskBaseDataset.encode_multi_class(mask_label, gender_label, age_label) 
                self.label_paths[gender_label].append(img_path)

    def calc_statistics(self):
        has_statistics = self.mean is not None and self.std is not None
        if not has_statistics:
            print("[Warning] Calculating statistics... It can take a long time depending on your CPU machine")
            sums = []
            squared = []
            for image_path in self.image_paths[:3000]:
                image = np.array(Image.open(image_path)).astype(np.int32)
                sums.append(image.mean(axis=(0, 1)))
                squared.append((image ** 2).mean(axis=(0, 1)))

            self.mean = np.mean(sums, axis=0) / 255
            self.std = (np.mean(squared, axis=0) - self.mean ** 2) ** 0.5 / 255

    def set_transform(self, transform):
        self.transform = transform

    def __getitem__(self, index):
        assert self.transform is not None, ".set_tranform 메소드를 이용하여 transform 을 주입해주세요"

        image = self.read_image(index)
#         mask_label = self.get_mask_label(index)
        gender_label = self.get_gender_label(index)
#         age_label = self.get_age_label(index)
#         multi_class_label = self.encode_multi_class(mask_label, gender_label, age_label)

        image_transform = self.transform(image)
        return image_transform, gender_label

    def __len__(self):
        return len(self.image_paths)

#     def get_mask_label(self, index) -> MaskLabels:
#         '''
#         지정된 인덱스의 마스크 라벨을 반환합니다.
#         '''
#         return self.mask_labels[index]

    def get_gender_label(self, index) -> GenderLabels:
        '''
        지정된 인덱스의 성별 라벨을 반환합니다.
        '''
        return self.gender_labels[index]

#     def get_age_label(self, index) -> AgeLabels:
#         '''
#         지정된 인덱스의 나이 라벨을 반환합니다.
#         '''
#         return self.age_labels[index]

    def read_image(self, index):
        '''
        지정된 인덱스의 이미지 데이터를 읽어들입니다.
        '''
        image_path = self.image_paths[index]
        return Image.open(image_path)

#     @staticmethod
#     def encode_multi_class(mask_label, gender_label, age_label) -> int:
#         '''
#         다중 클래스 분류를 위해 세 개의 라벨을 하나의 숫자로 인코딩
#         '''
#         return mask_label * 6 + gender_label * 3 + age_label

#     @staticmethod
#     def decode_multi_class(multi_class_label) -> Tuple[MaskLabels, GenderLabels, AgeLabels]:
#         '''
#         인코딩된 숫자를 세 개의 라벨로 디코딩
#         '''
#         mask_label = (multi_class_label // 6) % 3
#         gender_label = (multi_class_label // 3) % 2
#         age_label = multi_class_label % 3
#         return mask_label, gender_label, age_label

    @staticmethod
    def denormalize_image(image, mean, std):
        '''
        이미지의 정규화된 값을 원래 픽셀 값으로 변환합니다.
        '''
        img_cp = image.copy()
        img_cp *= std
        img_cp += mean
        img_cp *= 255.0
        img_cp = np.clip(img_cp, 0, 255).astype(np.uint8)
        return img_cp

    def split_dataset(self) -> Tuple[Subset, Subset]:
        """
        데이터셋을 train 과 val 로 나눕니다,
        pytorch 내부의 torch.utils.data.random_split 함수를 사용하여
        torch.utils.data.Subset 클래스 둘로 나눕니다.
        구현이 어렵지 않으니 구글링 혹은 IDE (e.g. pycharm) 의 navigation 기능을 통해 코드를 한 번 읽어보는 것을 추천드립니다^^
        """
        n_val = int(len(self) * self.val_ratio)
        n_train = len(self) - n_val
        train_set, val_set = random_split(self, [n_train, n_val])
        return train_set, val_set
    
class AgeDataset(Dataset):
    num_classes = 3
    
    _file_names = {
        "mask1": MaskLabels.MASK,
        "mask2": MaskLabels.MASK,
        "mask3": MaskLabels.MASK,
        "mask4": MaskLabels.MASK,
        "mask5": MaskLabels.MASK,
        "incorrect_mask": MaskLabels.INCORRECT,
        "normal": MaskLabels.NORMAL
    }
    
    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.data_dir = data_dir
        self.mean = mean
        self.std = std
        self.val_ratio = val_ratio
        self.image_paths = []
#         self.mask_labels = []
#         self.gender_labels = []
        self.age_labels = []
        self.outlier_remove = outlier_remove
        
        self.label_paths = {i:[] for i in range(3)} # 0~30 : 0, 31~58 : 1, 59~ : 2
        
        self.transform = None
        self.setup()
        self.calc_statistics()
        

    def setup(self):
        profiles = os.listdir(self.data_dir)
        for profile in profiles:
            if profile.startswith("."):  # "." 로 시작하는 파일은 무시합니다
                continue

            img_folder = os.path.join(self.data_dir, profile)
            for file_name in os.listdir(img_folder):
                _file_name, ext = os.path.splitext(file_name)
                if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                    continue

                img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                
#                 mask_label = self._file_names[_file_name]

                id, gender, race, age = profile.split("_")
#                 if self.outlier_remove:
#                     sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
#                     if id in sex_mislabeled_profiles:
#                         if gender == 'male':
#                             gender == 'female'
#                         else:
#                             gender == 'male'
#                 gender_label = GenderLabels.from_str(gender)
                age_label = AgeLabels.from_number(age)

                self.image_paths.append(img_path)
#                 self.mask_labels.append(mask_label)
#                 self.gender_labels.append(gender_label)
                self.age_labels.append(age_label)
#                 idx = MaskBaseDataset.encode_multi_class(mask_label, gender_label, age_label) 
                self.label_paths[age_label].append(img_path)

    def calc_statistics(self):
        has_statistics = self.mean is not None and self.std is not None
        if not has_statistics:
            print("[Warning] Calculating statistics... It can take a long time depending on your CPU machine")
            sums = []
            squared = []
            for image_path in self.image_paths[:3000]:
                image = np.array(Image.open(image_path)).astype(np.int32)
                sums.append(image.mean(axis=(0, 1)))
                squared.append((image ** 2).mean(axis=(0, 1)))

            self.mean = np.mean(sums, axis=0) / 255
            self.std = (np.mean(squared, axis=0) - self.mean ** 2) ** 0.5 / 255

    def set_transform(self, transform):
        self.transform = transform

    def __getitem__(self, index):
        assert self.transform is not None, ".set_tranform 메소드를 이용하여 transform 을 주입해주세요"

        image = self.read_image(index)
#         mask_label = self.get_mask_label(index)
#         gender_label = self.get_gender_label(index)
        age_label = self.get_age_label(index)
#         multi_class_label = self.encode_multi_class(mask_label, gender_label, age_label)

        image_transform = self.transform(image)
        return image_transform, age_label

    def __len__(self):
        return len(self.image_paths)

#     def get_mask_label(self, index) -> MaskLabels:
#         '''
#         지정된 인덱스의 마스크 라벨을 반환합니다.
#         '''
#         return self.mask_labels[index]

#     def get_gender_label(self, index) -> GenderLabels:
#         '''
#         지정된 인덱스의 성별 라벨을 반환합니다.
#         '''
#         return self.gender_labels[index]

    def get_age_label(self, index) -> AgeLabels:
        '''
        지정된 인덱스의 나이 라벨을 반환합니다.
        '''
        return self.age_labels[index]

    def read_image(self, index):
        '''
        지정된 인덱스의 이미지 데이터를 읽어들입니다.
        '''
        image_path = self.image_paths[index]
        return Image.open(image_path)

#     @staticmethod
#     def encode_multi_class(mask_label, gender_label, age_label) -> int:
#         '''
#         다중 클래스 분류를 위해 세 개의 라벨을 하나의 숫자로 인코딩
#         '''
#         return mask_label * 6 + gender_label * 3 + age_label

#     @staticmethod
#     def decode_multi_class(multi_class_label) -> Tuple[MaskLabels, GenderLabels, AgeLabels]:
#         '''
#         인코딩된 숫자를 세 개의 라벨로 디코딩
#         '''
#         mask_label = (multi_class_label // 6) % 3
#         gender_label = (multi_class_label // 3) % 2
#         age_label = multi_class_label % 3
#         return mask_label, gender_label, age_label

    @staticmethod
    def denormalize_image(image, mean, std):
        '''
        이미지의 정규화된 값을 원래 픽셀 값으로 변환합니다.
        '''
        img_cp = image.copy()
        img_cp *= std
        img_cp += mean
        img_cp *= 255.0
        img_cp = np.clip(img_cp, 0, 255).astype(np.uint8)
        return img_cp

    def split_dataset(self) -> Tuple[Subset, Subset]:
        """
        데이터셋을 train 과 val 로 나눕니다,
        pytorch 내부의 torch.utils.data.random_split 함수를 사용하여
        torch.utils.data.Subset 클래스 둘로 나눕니다.
        구현이 어렵지 않으니 구글링 혹은 IDE (e.g. pycharm) 의 navigation 기능을 통해 코드를 한 번 읽어보는 것을 추천드립니다^^
        """
        n_val = int(len(self) * self.val_ratio)
        n_train = len(self) - n_val
        train_set, val_set = random_split(self, [n_train, n_val])
        return train_set, val_set
    
class MaskBaseDataset(Dataset):
    num_classes = 3 * 2

    _file_names = {
        "mask1": MaskLabels.MASK,
        "mask2": MaskLabels.MASK,
        "mask3": MaskLabels.MASK,
        "mask4": MaskLabels.MASK,
        "mask5": MaskLabels.MASK,
        "incorrect_mask": MaskLabels.INCORRECT,
        "normal": MaskLabels.NORMAL
    }

#     image_paths = []
#     mask_labels = []
#     gender_labels = []
#     age_labels = []

    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.data_dir = data_dir
        self.mean = mean
        self.std = std
        self.val_ratio = val_ratio

        self.transform = None
        self.image_paths = []
        self.mask_labels = []
        self.gender_labels = []
#         self.age_labels = []
        self.outlier_remove = outlier_remove
        self.setup()
        self.calc_statistics()

    def setup(self):
        profiles = os.listdir(self.data_dir)
        for profile in profiles:
            if profile.startswith("."):  # "." 로 시작하는 파일은 무시합니다
                continue

            img_folder = os.path.join(self.data_dir, profile)
            for file_name in os.listdir(img_folder):
                _file_name, ext = os.path.splitext(file_name)
                if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                    continue

                img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                mask_label = self._file_names[_file_name]

                id, gender, race, age = profile.split("_")
                if self.outlier_remove:
                    sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
                    if id in sex_mislabeled_profiles:
                        if gender == 'male':
                            gender == 'female'
                        else:
                            gender == 'male'
                gender_label = GenderLabels.from_str(gender)
#                 age_label = AgeLabels.from_number(age)

                self.image_paths.append(img_path)
                self.mask_labels.append(mask_label)
                self.gender_labels.append(gender_label)
#                 self.age_labels.append(age_label)

    def calc_statistics(self):
        has_statistics = self.mean is not None and self.std is not None
        if not has_statistics:
            print("[Warning] Calculating statistics... It can take a long time depending on your CPU machine")
            sums = []
            squared = []
            for image_path in self.image_paths[:3000]:
                image = np.array(Image.open(image_path)).astype(np.int32)
                sums.append(image.mean(axis=(0, 1)))
                squared.append((image ** 2).mean(axis=(0, 1)))

            self.mean = np.mean(sums, axis=0) / 255
            self.std = (np.mean(squared, axis=0) - self.mean ** 2) ** 0.5 / 255

    def set_transform(self, transform):
        self.transform = transform

    def __getitem__(self, index):
        assert self.transform is not None, ".set_tranform 메소드를 이용하여 transform 을 주입해주세요"

        image = self.read_image(index)
        mask_label = self.get_mask_label(index)
        gender_label = self.get_gender_label(index)
#         age_label = self.get_age_label(index)
        multi_class_label = self.encode_multi_class(mask_label, gender_label)

        image_transform = self.transform(image)
        return image_transform, multi_class_label

    def __len__(self):
        return len(self.image_paths)

    def get_mask_label(self, index) -> MaskLabels:
        '''
        지정된 인덱스의 마스크 라벨을 반환합니다.
        '''
        return self.mask_labels[index]

    def get_gender_label(self, index) -> GenderLabels:
        '''
        지정된 인덱스의 성별 라벨을 반환합니다.
        '''
        return self.gender_labels[index]

#     def get_age_label(self, index) -> AgeLabels:
#         '''
#         지정된 인덱스의 나이 라벨을 반환합니다.
#         '''
#         return self.age_labels[index]

    def read_image(self, index):
        '''
        지정된 인덱스의 이미지 데이터를 읽어들입니다.
        '''
        image_path = self.image_paths[index]
        return Image.open(image_path)

    @staticmethod
    def encode_multi_class(mask_label, gender_label) -> int:
        '''
        다중 클래스 분류를 위해 세 개의 라벨을 하나의 숫자로 인코딩
        '''
        return mask_label * 6 + gender_label * 3# + age_label

    @staticmethod
    def decode_multi_class(multi_class_label) -> Tuple[MaskLabels, GenderLabels]:
        '''
        인코딩된 숫자를 세 개의 라벨로 디코딩
        '''
        mask_label = (multi_class_label // 6) % 3
        gender_label = (multi_class_label // 3) % 2
#         age_label = multi_class_label % 3
        return mask_label, gender_label#, age_label

    @staticmethod
    def denormalize_image(image, mean, std):
        '''
        이미지의 정규화된 값을 원래 픽셀 값으로 변환합니다.
        '''
        img_cp = image.copy()
        img_cp *= std
        img_cp += mean
        img_cp *= 255.0
        img_cp = np.clip(img_cp, 0, 255).astype(np.uint8)
        return img_cp

    def split_dataset(self) -> Tuple[Subset, Subset]:
        """
        데이터셋을 train 과 val 로 나눕니다,
        pytorch 내부의 torch.utils.data.random_split 함수를 사용하여
        torch.utils.data.Subset 클래스 둘로 나눕니다.
        구현이 어렵지 않으니 구글링 혹은 IDE (e.g. pycharm) 의 navigation 기능을 통해 코드를 한 번 읽어보는 것을 추천드립니다^^
        """
        n_val = int(len(self) * self.val_ratio)
        n_train = len(self) - n_val
        train_set, val_set = random_split(self, [n_train, n_val])
        return train_set, val_set
    


class MaskSplitByProfileDataset(MaskBaseDataset):
    """
        train / val 나누는 기준을 이미지에 대해서 random 이 아닌
        사람(profile)을 기준으로 나눕니다.
        구현은 val_ratio 에 맞게 train / val 나누는 것을 이미지 전체가 아닌 사람(profile)에 대해서 진행하여 indexing 을 합니다
        이후 `split_dataset` 에서 index 에 맞게 Subset 으로 dataset 을 분기합니다.
    """

    def __init__(self, data_dir, outlier_remove, mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246), val_ratio=0.2):
        self.indices = defaultdict(list)
        super().__init__(data_dir, outlier_remove, mean, std, val_ratio)
        self.outlier_remove = outlier_remove

    @staticmethod
    def _split_profile(profiles, val_ratio):
        length = len(profiles)
        n_val = int(length * val_ratio)

        val_indices = set(random.sample(range(length), k=n_val))
        train_indices = set(range(length)) - val_indices
        return {
            "train": train_indices,
            "val": val_indices
        }

    def setup(self):
        '''
        데이터셋을 설정하는 메서드
        profiles:  data_dir 디렉토리에 있는 모든 프로필 디렉토리 이름을 리스트로 저장
        val_ratio : 비율에 따라 train과 validation 데이터셋에 포함될 프로필을 나눔
        나누어진 train_indices와 val_indices를 사용하여 indices 딕셔너리에 train과 validation에 해당하는 인덱스를 저장함
        image_paths, mask_labels, gender_labels, age_labels 리스트에 각 이미지의 경로, 마스크, 성별, 연령 정보를 저장
        indices 딕셔너리에 저장한 인덱스를 사용하여 Subset으로 데이터셋을 나누어줍니다
        '''
        profiles = os.listdir(self.data_dir)
        profiles = [profile for profile in profiles if not profile.startswith(".")]
        split_profiles = self._split_profile(profiles, self.val_ratio)

        cnt = 0
        for phase, indices in split_profiles.items():
            for _idx in indices:
                profile = profiles[_idx]
                img_folder = os.path.join(self.data_dir, profile)
                for file_name in os.listdir(img_folder):
                    _file_name, ext = os.path.splitext(file_name)
                    if _file_name not in self._file_names:  # "." 로 시작하는 파일 및 invalid 한 파일들은 무시합니다
                        continue

                    img_path = os.path.join(self.data_dir, profile, file_name)  # (resized_data, 000004_male_Asian_54, mask1.jpg)
                    mask_label = self._file_names[_file_name]

                    id, gender, race, age = profile.split("_")
                    if self.outlier_remove:
                        sex_mislabeled_profiles = ['001498-1', '004432', '006359', '006360', '006361', '006362']
                        if id in sex_mislabeled_profiles:
                            if gender == 'male':
                                gender == 'female'
                            else:
                                gender == 'male'
                    gender_label = GenderLabels.from_str(gender)
                    age_label = AgeLabels.from_number(age)

                    self.image_paths.append(img_path)
                    self.mask_labels.append(mask_label)
                    self.gender_labels.append(gender_label)
                    self.age_labels.append(age_label)

                    self.indices[phase].append(cnt)
                    cnt += 1

    def split_dataset(self) -> List[Subset]:
        '''
        Subset의 리스트를 반환
        리스트의 각 요소는 indices 딕셔너리에 저장한 인덱스를 사용하여 MaskSplitByProfileDataset 클래스를 Subset으로 나눈 결과임

        '''
        return [Subset(self, indices) for phase, indices in self.indices.items()]

###### TestDataset ##########

# class TestDataset(Dataset):
#     def __init__(self, img_paths, resize=(512, 384), mean=(0.548, 0.504, 0.479), std=(0.237, 0.247, 0.246)):
#         self.img_paths = img_paths
#         self.transform = Compose([
#             Resize(resize, Image.BILINEAR),
#             ToTensor(),
#             Normalize(mean=mean, std=std),
#         ])

#     def __getitem__(self, index):
#         image = Image.open(self.img_paths[index])

#         if self.transform:
#             image = self.transform(image)
#         return image

#     def __len__(self):
#         return len(self.img_paths)

class TestDataset(Dataset):
    def __init__(self, img_paths, transform):
        self.img_paths = img_paths
        self.transform = Compose([
            Resize(resize, Image.BILINEAR),
            ToTensor(),
            Normalize(mean=mean, std=std),
        ])

    def __getitem__(self, index):
        image = Image.open(self.img_paths[index])

        if self.transform:
            image = self.transform(image)
        return image

    def __len__(self):
        return len(self.img_paths)
