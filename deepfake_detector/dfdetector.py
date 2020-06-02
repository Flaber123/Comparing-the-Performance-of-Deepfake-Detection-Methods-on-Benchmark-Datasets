import argparse
import copy
import os
import shutil
import test
import time
import zipfile
import timm
import numpy as np
import pandas as pd
import torch
import torch.backends.cudnn as cudnn
import torch.nn as nn
import metrics
import cv2
import datasets
import torchvision
import torchvision.models as models
import train

from albumentations import (
    Compose, FancyPCA, GaussianBlur, GaussNoise, HorizontalFlip,
    HueSaturationValue, ImageCompression, OneOf, PadIfNeeded,
    RandomBrightnessContrast, Resize, ShiftScaleRotate, ToGray)
from pretrained_mods import xception
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.model_selection import ShuffleSplit
from sklearn.metrics import confusion_matrix
from tqdm import tqdm
from facedetector.retinaface import df_retinaface
from pretrained_mods import efficientnetb1lstm


class DFDetector():
    """
    The Deepfake Detector. 
    It can detect on a single video, 
    benchmark several methods on benchmark datasets
    and train detectors on several datasets.
    """

    def __init__(self, facedetector="retinaface_resnet"):
        self.facedetector = facedetector

    @classmethod
    def detect_single(cls, video=None,  method="xception"):
        """Perform deepfake detection on a single video with a chosen method."""
        return result

    @classmethod
    def benchmark(cls, dataset=None, data_path=None, method="xception", seed=24):
        """Benchmark deepfake detection methods against popular deepfake datasets.
           The methods are already pretrained on the datasets. 
           Methods get benchmarked against a test set that is distinct from the training data.
        # Arguments:
            dataset: The dataset that the method is tested against.
            data_path: The path to the test videos.
            method: The deepfake detection method that is used.
        # Implementation: Christopher Otto
        """
        # seed numpy and pytorch for reproducibility
        reproducibility_seed(seed)
        if method not in ['xception', 'efficientnetb7', 'mesonet', 'resnetlstm', 'efficientnetb1_lstm', 'dfdcrank90', 'five_methods_ensemble']:
            raise ValueError("Method is not available for benchmarking.")
        else:
            # method exists
            cls.dataset = dataset
            cls.data_path = data_path
            cls.method = method
        if cls.dataset == 'uadfv':
            # setup the dataset folders
            setup_uadfv_benchmark(cls.data_path, cls.method)
        elif cls.dataset == 'celebdf':
            setup_celebdf_benchmark(cls.data_path, cls.method)
        else:
            raise ValueError(f"{cls.dataset} does not exist.")
        # get test labels for metric evaluation
        df = label_data(dataset_path=cls.data_path,
                        dataset=cls.dataset, test_data=True)
        # prepare the method of choice
        if cls.method == "xception":
            model, img_size, normalization = prepare_method(
                method=cls.method, dataset=cls.dataset, mode='test')
        elif cls.method == "efficientnetb7":
            model, img_size, normalization = prepare_method(
                method=cls.method, dataset=cls.dataset, mode='test')
        elif cls.method == 'mesonet':
            pass
        elif cls.method == 'resnetlstm':
            pass
        elif cls.method == 'efficientnetb1_lstm':
            pass
        elif cls.method == 'dfdcrank90':
            # evaluate dfdcrank90 ensemble
            auc, ap, loss, acc = prepare_dfdc_rank90(method, cls.dataset, df)
            return [auc, ap, loss, acc]
        elif cls.method == 'five_methods_ensemble':
            pass

        print(f"Detecting deepfakes with \033[1m{cls.method}\033[0m ...")
        # benchmarking
        auc, ap, loss, acc = test.inference(
            model, df, img_size, normalization, dataset=cls.dataset, method=cls.method)

        return [auc, ap, loss, acc]

    @classmethod
    def train_method(cls, dataset=None, data_path=None, method="xception", img_save_path=None, epochs=1, batch_size=32,
                     lr=0.001, folds=1, augmentation_strength='weak', fulltrain=False, faces_available=False, face_margin=0, seed=24):
        """Train a deepfake detection method on a dataset."""
        if img_save_path is None:
            raise ValueError(
                "Need a path to save extracted images for training.")
        cls.dataset = dataset
        print(f"Training on {cls.dataset} dataset.")
        cls.data_path = data_path
        cls.method = method
        cls.epochs = epochs
        cls.batch_size = batch_size
        cls.lr = lr
        cls.augmentations = augmentation_strength
        # no k-fold cross val if folds == 1
        cls.folds = folds
        # whether to train on the entire training data (without val sets)
        cls.fulltrain = fulltrain
        cls.faces_available = faces_available
        cls.face_margin = face_margin
        print(f"Training on {cls.dataset} dataset with {cls.method}.")
        # seed numpy and pytorch for reproducibility
        reproducibility_seed(seed)
        _, img_size, normalization = prepare_method(
            cls.method, dataset=cls.dataset, mode='train')
        # # get video train data and labels 
        df = label_data(dataset_path=cls.data_path,
                        dataset=cls.dataset, test_data=False)
        # detect and extract faces if they are not available already
        if not cls.faces_available:
            if cls.dataset == 'uadfv':
                addon_path = '/train_imgs/'
                if not os.path.exists(img_save_path + '/train_imgs/'):
                    # create directory in save path for images
                    os.mkdir(img_save_path + addon_path)
                    os.mkdir(img_save_path + '/train_imgs/real/')
                    os.mkdir(img_save_path + '/train_imgs/fake/')
            elif cls.dataset == 'celebdf':
                addon_path = '/facecrops/'
                # check if all folders are available
                if not os.path.exists(img_save_path + '/Celeb-real/'):
                    raise ValueError(
                        "Please unpack the dataset again. The \"Celeb-real\" folder is missing.")
                if not os.path.exists(img_save_path + '/Celeb-synthesis/'):
                    raise ValueError(
                        "Please unpack the dataset again. The \"Celeb-synthesis\" folder is missing.")
                if not os.path.exists(img_save_path + '/YouTube-real/'):
                    raise ValueError(
                        "Please unpack the dataset again. The \"YouTube-real\" folder is missing.")
                if not os.path.exists(img_save_path + '/List_of_testing_videos.txt'):
                    raise ValueError(
                        "Please unpack the dataset again. The \"List_of_testing_videos.txt\" file is missing.")
                if not os.path.exists(img_save_path + '/facecrops/'):
                    # create directory in save path for face crops
                    os.mkdir(img_save_path + addon_path)
                    os.mkdir(img_save_path + '/facecrops/real/')
                    os.mkdir(img_save_path + '/facecrops/fake/')
                else:
                    # delete create again if it already exists with old files
                    shutil.rmtree(img_save_path + '/facecrops/')
                    os.mkdir(img_save_path + addon_path)
                    os.mkdir(img_save_path + '/facecrops/real/')
                    os.mkdir(img_save_path + '/facecrops/fake/')

            print("Detect and save 20 faces from each video for training.")
            if cls.face_margin > 0.0:
                print(f"Apply {cls.face_margin*100}% margin to each side of the face crop.")
            else:
                print("Apply no margin to the face crop.")
            # load retinaface face detector
            net, cfg = df_retinaface.detect()
            for idx, row in tqdm(df.iterrows(), total=df.shape[0]):
                video = row.loc['video']
                label = row.loc['label']
                vid = os.path.join(video)
                if cls.dataset == 'uadfv':
                    if label == 1:
                        video = video[-14:]
                        save_dir = os.path.join(
                            img_save_path + '/train_imgs/fake/')
                    else:
                        video = video[-9:]
                        save_dir = os.path.join(
                            img_save_path + '/train_imgs/real/')
                elif cls.dataset == 'celebdf':
                    vid_name = row.loc['video_name']
                    if label == 1:
                        video = vid_name
                        save_dir = os.path.join(
                            img_save_path + '/facecrops/fake/')
                    else:
                        video = vid_name
                        save_dir = os.path.join(
                            img_save_path + '/facecrops/real/')
                    # detect faces, add margin, crop, upsample to same size, save to images
                faces = df_retinaface.detect_faces(
                    net, vid, cfg, num_frames=20)
                # save frames to directory
                vid_frames = df_retinaface.extract_frames(
                    faces, video, save_to=save_dir, face_margin=cls.face_margin, num_frames=20, test=False)
                
        # put all face images in dataframe
        df_faces = label_data(dataset_path=cls.data_path,
                              dataset=cls.dataset, method=cls.method, face_crops=True, test_data=False)
        # choose augmentation strength
        augs = df_augmentations(img_size, strength=cls.augmentations)
        # start method training
    
        model, average_auc, average_ap, average_acc, average_loss = train.train(dataset=cls.dataset, data=df_faces,
                                                                                method=cls.method, img_size=img_size, normalization=normalization, augmentations=augs,
                                                                                folds=cls.folds, epochs=cls.epochs, batch_size=cls.batch_size, lr=cls.lr, fulltrain=cls.fulltrain
                                                                                )
        return model, average_auc, average_ap, average_acc, average_loss


def prepare_method(method, dataset, mode='train'):
    """Prepares the method that will be used."""
    if method == 'xception':
        img_size = 299
        normalization = 'xception'
        if mode == 'test':
            model = xception.imagenet_pretrained_xception()
            # load the xception model that was pretrained on the uadfv training data
            model_params = torch.load(
                os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/{method}_best_fulltrain_{dataset}.pth')
            print(os.getcwd(
            ) + f'/deepfake_detector/pretrained_mods/weights/{method}_best_fulltrain_{dataset}.pth')
            model.load_state_dict(model_params)
            return model, img_size, normalization
        elif mode == 'train':
            # model is loaded in the train loop, because easier in case of k-fold cross val
            model = None
            return model, img_size, normalization
    elif method == 'efficientnetb7':
        # 380 image size as introduced here https://www.kaggle.com/c/deepfake-detection-challenge/discussion/145721
        img_size = 380
        normalization = 'imagenet'
        if mode == 'test':
            # successfully used by https://www.kaggle.com/c/deepfake-detection-challenge/discussion/145721 (noisy student weights)
            model = timm.create_model('tf_efficientnet_b7_ns', pretrained=True)
            model.classifier = nn.Linear(2560, 1)
            # load the efficientnet model that was pretrained on the uadfv training data
            model_params = torch.load(
                os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/efficientnetb7_best_fulltrain_{dataset}.pth')
            model.load_state_dict(model_params)
            return model, img_size, normalization
        elif mode == 'train':
            # model is loaded in the train loop, because easier in case of k-fold cross val
            model = None
            return model, img_size, normalization
    elif method == 'mesonet':
        # 256 image size as proposed in the MesoNet paper (https://arxiv.org/abs/1809.00888)
        img_size = 256
        # use [0.5,0.5,0.5] normalization scheme, because no imagenet pretraining
        normalization = 'xception'
        if mode == 'test':
            # load the mesonet model that was pretrained on the uadfv training data
            model_params = torch.load(
                os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/{method}_best_fulltrain_{dataset}.pth')
            print(os.getcwd(
            ) + f'/deepfake_detector/pretrained_mods/weights/{method}_best_fulltrain_{dataset}.pth')
            model.load_state_dict(model_params)
            return model, img_size, normalization
        elif mode == 'train':
            # model is loaded in the train loop, because easier in case of k-fold cross val
            model = None
            return model, img_size, normalization
    elif method == 'resnetlstm':
        img_size = 224
        normalization = 'imagenet'
        if mode == 'test':
            pass
        elif mode == 'train':
            # model is loaded in the train loop, because easier in case of k-fold cross val
            model = None
            return model, img_size, normalization
    elif method == 'efficientnetb1_lstm':
        img_size = 240
        normalization = 'imagenet'
        if mode == 'test':
            pass
        elif mode == 'train':
            # model is loaded in the train loop, because easier in case of k-fold cross val
            model = None
            return model, img_size, normalization

    else:
        raise ValueError(
            f"{method} is not available. Please use one of the available methods.")


def prepare_dfdc_rank90(method, dataset, df):
    """Prepares the DFDC rank 90 ensemble."""
    img_size_xception = 299
    img_size_b1 = 240
    normalization_xception = 'xception'
    normalization_b1 = 'imagenet'
    inference_time = time.time()
    model3 = efficientnetb1lstm.EfficientNetB1LSTM()
    # load the xception model that was pretrained on the uadfv training data
    # model_params3 = torch.load(
    #     os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/xception_best_fulltrain_uadfv.pth')
    # model3.load_state_dict(model_params)
    print("Inference EfficientNetB1 + LSTM")
    df3 = test.inference(
        model3, df, img_size_b1, normalization_b1, dataset=dataset, method=method, sequence_model=True, ensemble=True)

    model1 = xception.imagenet_pretrained_xception()
    # load the xception model that was pretrained on the uadfv training data
    model_params1 = torch.load(
        os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/xception_best_fulltrain_uadfv.pth')
    model1.load_state_dict(model_params1)

    print("Inference Xception One")
    df1 = test.inference(
        model1, df, img_size_xception, normalization_xception, dataset=dataset, method=method, ensemble=True)

    model2 = xception.imagenet_pretrained_xception()
    # load the xception model that was pretrained on the uadfv training data
    model_params2 = torch.load(
        os.getcwd() + f'/deepfake_detector/pretrained_mods/weights/xception_best_fulltrain_uadfv.pth')
    model2.load_state_dict(model_params2)

    print("Inference Xception Two")
    df2 = test.inference(
        model2, df, img_size_xception, normalization_xception, dataset=dataset, method=method, ensemble=True)

    # average predictions of all three models
    df1['Prediction'] = (df1['Prediction'] +
                         df2['Prediction'] + df3['Prediction'])/3

    labs = list(df1['Label'])
    prds = list(df1['Prediction'])

    running_corrects = 0
    running_false = 0
    running_corrects += np.sum(np.round(prds) == labs)
    running_false += np.sum(np.round(prds) != labs)

    loss_func = nn.BCEWithLogitsLoss()
    loss = loss_func(torch.Tensor(prds), torch.Tensor(labs))

    # calculate metrics
    one_rec, five_rec, nine_rec = metrics.prec_rec(
        labs, prds, method, alpha=100, plot=False)
    auc = round(roc_auc_score(labs, prds), 5)
    ap = round(average_precision_score(labs, prds), 5)
    loss = round(loss.numpy().tolist(), 5)
    acc = round(running_corrects / len(labs), 5)
    print("Benchmark results:")
    print("Confusion matrix:")
    print(confusion_matrix(labs, np.round(prds)))
    tn, fp, fn, tp = confusion_matrix(labs, np.round(prds)).ravel()
    print(f"Loss: {loss}")
    print(f"Acc: {acc}")
    print(f"AUC: {auc}")
    print(f"AP: {auc}")
    print()
    print("Cost (best possible cost is 0.0):")
    print(f"{one_rec} cost for 0.1 recall.")
    print(f"{five_rec} cost for 0.5 recall.")
    print(f"{nine_rec} cost for 0.9 recall.")
    print(
        f"Duration: {(time.time() - inference_time) // 60} min and {(time.time() - inference_time) % 60} sec.")
    print()
    print(
        f"Detected \033[1m {tp}\033[0m true deepfake videos and correctly classified \033[1m {tn}\033[0m real videos.")
    print(
        f"Mistook \033[1m {fp}\033[0m real videos for deepfakes and \033[1m {fn}\033[0m deepfakes went by undetected by the method.")
    if fn == 0 and fp == 0:
        print("Wow! A perfect classifier!")

    return auc, ap, loss, acc


def label_data(dataset_path=None, dataset='uadfv', method='xception', face_crops=False, test_data=False):
    """
    Label the data.
    # Arguments:
        dataset_path: path to data
        test_data: binary choice that indicates whether data is for testing or not.
    # Implementation: Christopher Otto
    """
    # structure data from folder in data frame for loading
    if dataset_path is None:
        # TEST
        raise ValueError("Please specify a dataset path.")
    # TEST
    if not test_data:
        if dataset == 'uadfv':
            # prepare training data
            video_path_real = os.path.join(dataset_path + "/real/")
            video_path_fake = os.path.join(dataset_path + "/fake/")
            # if no face crops available yet, read csv for videos
            if not face_crops:
                # read csv for videos
                test_dat = pd.read_csv(os.getcwd(
                ) + "/deepfake_detector/data/uadfv_test.csv", names=['video'], header=None)
                test_list = test_dat['video'].tolist()

                full_list = []
                for _, _, videos in os.walk(video_path_real):
                    for video in videos:
                        # label 0 for real video
                        full_list.append(video)

                for _, _, videos in os.walk(video_path_fake):
                    for video in videos:
                        # label 1 for deepfake video
                        full_list.append(video)

                # training data (not used for testing)
                new_list = [
                    entry for entry in full_list if entry not in test_list]

                # add labels to videos
                data_list = []
                for _, _, videos in os.walk(video_path_real):
                    for video in tqdm(videos):
                        # append if video in training data
                        if video in new_list:
                            # label 0 for real video
                            data_list.append(
                                {'label': 0, 'video': video_path_real + video})

                for _, _, videos in os.walk(video_path_fake):
                    for video in tqdm(videos):
                        # append if video in training data
                        if video in new_list:
                            # label 1 for deepfake video
                            data_list.append(
                                {'label': 1, 'video': video_path_fake + video})

                # put data into dataframe
                df = pd.DataFrame(data=data_list)

            else:
                # if sequence, prepare sequence dataframe
                if method == 'resnetlstm' or method == 'efficientnetb1_lstm':
                    # prepare dataframe for sequence model
                    video_path_real = os.path.join(
                        dataset_path + "/train_imgs/real/")
                    video_path_fake = os.path.join(
                        dataset_path + "/train_imgs/fake/")

                    data_list = []
                    for _, _, videos in os.walk(video_path_real):
                        for video in tqdm(videos):
                            # label 0 for real video
                            data_list.append(
                                {'label': 0, 'video': video})

                    for _, _, videos in os.walk(video_path_fake):
                        for video in tqdm(videos):
                            # label 1 for deepfake video
                            data_list.append(
                                {'label': 1, 'video': video})

                    # put data into dataframe
                    df = pd.DataFrame(data=data_list)
                    df = prepare_sequence_data(dataset, df)
                    # add path to data
                    for idx, row in df.iterrows():
                        if row['label'] == 0:
                            df.loc[idx, 'original'] = str(
                                video_path_real) + str(row['original'])
                        elif row['label'] == 1:
                            df.loc[idx, 'original'] = str(
                                video_path_fake) + str(row['original'])

                else:
                    # if face crops available go to path with face crops
                    # add labels to videos

                    video_path_real = os.path.join(
                        dataset_path + "/train_imgs/real/")
                    video_path_fake = os.path.join(
                        dataset_path + "/train_imgs/fake/")

                    data_list = []
                    for _, _, videos in os.walk(video_path_real):
                        for video in tqdm(videos):
                            # label 0 for real video
                            data_list.append(
                                {'label': 0, 'video': video_path_real + video})

                    for _, _, videos in os.walk(video_path_fake):
                        for video in tqdm(videos):
                            # label 1 for deepfake video
                            data_list.append(
                                {'label': 1, 'video': video_path_fake + video})

                    # put data into dataframe
                    df = pd.DataFrame(data=data_list)

        elif dataset == 'celebdf':
            # prepare celebdf training data by
            # reading in the testing data first
            df_test = pd.read_csv(
                dataset_path + '/List_of_testing_videos.txt', sep=" ", header=None)
            df_test.columns = ["label", "video"]
            # switch labels so that fake label is 1
            df_test['label'] = df_test['label'].apply(switch_one_zero)
            df_test['video'] = dataset_path + '/' + df_test['video']
            # structure data from folder in data frame for loading
            if not face_crops:
                video_path_real = os.path.join(dataset_path + "/Celeb-real/")
                video_path_fake = os.path.join(
                    dataset_path + "/Celeb-synthesis/")
                real_list = []
                for _, _, videos in os.walk(video_path_real):
                    for video in tqdm(videos):
                        # label 0 for real image
                        real_list.append({'label': 0, 'video': video})

                fake_list = []
                for _, _, videos in os.walk(video_path_fake):
                    for video in tqdm(videos):
                        # label 1 for deepfake image
                        fake_list.append({'label': 1, 'video': video})

                # put data into dataframe
                df_real = pd.DataFrame(data=real_list)
                df_fake = pd.DataFrame(data=fake_list)
                # add real and fake path to video file name
                df_real['video_name'] = df_real['video']
                df_fake['video_name'] = df_fake['video']
                df_real['video'] = video_path_real + df_real['video']
                df_fake['video'] = video_path_fake + df_fake['video']
                # put testing vids in list
                testing_vids = list(df_test['video'])
                # remove testing videos from training videos
                df_real = df_real[~df_real['video'].isin(testing_vids)]
                df_fake = df_fake[~df_fake['video'].isin(testing_vids)]
                # undersampling strategy to ensure class balance of 50/50
                df_fake_sample = df_fake.sample(
                    n=len(df_real), random_state=24).reset_index(drop=True)
                # concatenate both dataframes to get full training data (964 training videos with 50/50 class balance)
                df = pd.concat([df_real, df_fake_sample], ignore_index=True)
            else:
                # if face crops available go to path with face crops
                video_path_crops_real = os.path.join(
                    dataset_path + "/facecrops/real/")
                video_path_crops_fake = os.path.join(
                    dataset_path + "/facecrops/fake/")
                # add labels to videos
                data_list = []
                for _, _, videos in os.walk(video_path_crops_real):
                    for video in tqdm(videos):
                        # label 0 for real video
                        data_list.append(
                            {'label': 0, 'video': video_path_crops_real + video})

                for _, _, videos in os.walk(video_path_crops_fake):
                    for video in tqdm(videos):
                        # label 1 for deepfake video
                        data_list.append(
                            {'label': 1, 'video': video_path_crops_fake + video})
                # put data into dataframe
                df = pd.DataFrame(data=data_list)
                if len(df) == 0:
                    raise ValueError(
                        "No faces available. Please set faces_available=False.")

    else:
        # prepare test data
        if dataset == 'uadfv':
            video_path_test_real = os.path.join(dataset_path + "/test/real/")
            video_path_test_fake = os.path.join(dataset_path + "/test/fake/")
            data_list = []
            for _, _, videos in os.walk(video_path_test_real):
                for video in tqdm(videos):
                    # append test video
                    data_list.append(
                        {'label': 0, 'video': video_path_test_real + video})

            for _, _, videos in os.walk(video_path_test_fake):
                for video in tqdm(videos):
                    # label 1 for deepfake image
                    data_list.append(
                        {'label': 1, 'video': video_path_test_fake + video})
        elif dataset == 'celebdf':
            # reading in the celebdf testing data 
            df_test = pd.read_csv(
                dataset_path + '/List_of_testing_videos.txt', sep=" ", header=None)
            df_test.columns = ["label", "video"]
            # switch labels so that fake label is 1
            df_test['label'] = df_test['label'].apply(switch_one_zero)
            df_test['video'] = dataset_path + '/' + df_test['video']
            print(f"{len(df_test)} test videos.")
            return df_test

        # put data into dataframe
        df = pd.DataFrame(data=data_list)

    if test_data:
        print(f"{len(df)} test videos.")
    else:
        if face_crops:
            print(f"Lead to: {len(df)} face crops.")
        else:
            print(f"{len(df)} train videos.")
    print()
    return df


def df_augmentations(img_size, strength="weak"):
    """
    Augmentations with the albumentations package.
    # Arguments:
        strength: strong or weak augmentations

    # Implementation: Christopher Otto
    """
    if strength == "weak":
        print("Weak augmentations.")
        augs = Compose([
            # hflip with prob 0.5
            HorizontalFlip(p=0.5),
            # adjust image to DNN input size
            Resize(width=img_size, height=img_size)
        ])
        return augs
    elif strength == "strong":
        print("Strong augmentations.")
        # augmentations via albumentations package
        # augmentations adapted from Selim Seferbekov's 3rd place private leaderboard solution from
        # https://www.kaggle.com/c/deepfake-detection-challenge/discussion/145721
        augs = Compose([
            # hflip with prob 0.5
            HorizontalFlip(p=0.5),
            ImageCompression(quality_lower=60, quality_upper=100, p=0.5),
            GaussNoise(p=0.1),
            GaussianBlur(blur_limit=3, p=0.05),
            PadIfNeeded(min_height=img_size, min_width=img_size,
                        border_mode=cv2.BORDER_CONSTANT),
            OneOf([RandomBrightnessContrast(), FancyPCA(),
                   HueSaturationValue()], p=0.7),
            ToGray(p=0.2),
            ShiftScaleRotate(shift_limit=0.1, scale_limit=0.2,
                             rotate_limit=10, border_mode=cv2.BORDER_CONSTANT, p=0.5),
            # adjust image to DNN input size
            Resize(width=img_size, height=img_size)
        ])
        return augs
    else:
        raise ValueError(
            "This augmentation option does not exist. Choose \"weak\" or \"strong\".")


def structure_uadfv_files(path_to_data):
    """Creates test folders and moves test videos there."""
    os.mkdir(path_to_data + '/test/')
    os.mkdir(path_to_data + '/test/fake/')
    os.mkdir(path_to_data + '/test/real/')
    test_data = pd.read_csv(
        os.getcwd() + "/deepfake_detector/data/uadfv_test.csv", names=['video'], header=None)
    for idx, row in test_data.iterrows():
        if len(str(row.loc['video'])) > 8:
            # video is fake, therefore copy it into fake test folder
            shutil.copy(path_to_data + '/fake/' +
                        row['video'], path_to_data + '/test/fake/')
        else:
            # video is real, therefore move it into real test folder
            shutil.copy(path_to_data + '/real/' +
                        row['video'], path_to_data + '/test/real/')


def reproducibility_seed(seed):
    print(f"The random seed is set to {seed}.")
    # set numpy random seed
    np.random.seed(seed)
    # set pytorch random seed for cpu and gpu
    torch.manual_seed(seed)
    # get deterministic behavior
    torch.backends.cudnn.deterministic = True


def switch_one_zero(num):
    """Switch label 1 to 0 and 0 to 1
        so that fake videos have label 1.
    """
    if num == 1:
        num = 0
    else:
        num = 1
    return num


def prepare_sequence_data(dataset, df):
    """
    Prepares the dataframe for sequence models.
    """
    df = df.sort_values(by=['video']).reset_index(drop=True)
    # add original column
    df['original'] = ""
    if dataset == 'uadfv':
        # label data
        for idx, row in df.iterrows():
            if row.loc['label'] == 0:
                df.loc[idx, 'original'] = row.loc['video'][:4]
            elif row.loc['label'] == 1:
                df.loc[idx, 'original'] = row.loc['video'][:9]
    # count frames per video
    df1 = df.groupby(['original']).size().reset_index(name='count')
    df = pd.merge(df, df1, on='original')
    # remove videos that don't where less than 20 frames
    # were detected to ensure equal frame size of 20 for sequence
    df = df[df['count'] == 20]
    df = df[['label', 'original']]
    # ensure that dataframe includes each video with 20 frames once
    df = df.groupby(['label', 'original']).size().reset_index(name='count')
    df = df[['label', 'original']]
    return df


def setup_uadfv_benchmark(data_path, method):
    """
    Setup the folder structure of the UADFV Dataset.
    """
    if data_path is None:
        raise ValueError("""Please go to https://github.com/danmohaha/WIFS2018_In_Ictu_Oculi
                                and scroll down to the UADFV section.
                                Click on the link \"here\" and download the dataset. 
                                Extract the files and organize the folders follwing this folder structure:
                                ./fake_videos/
                                            fake/
                                            real/
                                """)
    if data_path.endswith("fake_videos.zip"):
        raise ValueError("Please make sure to extract the zipfile.")
    if data_path.endswith("fake_videos"):
        print(
            f"Benchmarking \033[1m{method}\033[0m on the UADFV dataset with ...")
        # create test directories if they don't exist
        if not os.path.exists(data_path + '/test/'):
            structure_uadfv_files(path_to_data=data_path)
        else:
            # check if path exists but files are not complete (from https://stackoverflow.com/a/2632251)
            num_files = len([f for f in os.listdir(
                data_path + '/test/') if os.path.isfile(os.path.join(data_path + '/test/real/', f))])
            num_files += len([f for f in os.listdir(data_path + '/test/')
                              if os.path.isfile(os.path.join(data_path + '/test/fake/', f))])
            # check whether all 28 test videos are in directories
            if num_files != 28:
                # recreate all 28 files
                shutil.rmtree(data_path + '/test/')
                structure_uadfv_files(path_to_data=data_path)
    else:
        raise ValueError("""Please organize the dataset directory in this way:
                            ./fake_videos/
                                        fake/
                                        real/
                        """)


def setup_celebdf_benchmark(data_path, method):
    """
    Setup the folder structure of the Celeb-DF Dataset.
    """
    if data_path is None:
        raise ValueError("""Please go to https://github.com/danmohaha/celeb-deepfakeforensics
                                and scroll down to the dataset section.
                                Click on the link \"this form\" and download the dataset. 
                                Extract the files and organize the folders follwing this folder structure:
                                ./celebdf/
                                        Celeb-real/
                                        Celeb-synthesis/
                                        YouTube-real/
                                        List_of_testing_videos.txt
                                """)
    if data_path.endswith("celebdf"):
        print(
            f"Benchmarking \033[1m{method}\033[0m on the \033[1m{Celeb-DF}\033[0m dataset with ...")
    else:
        raise ValueError("""Please organize the dataset directory in this way:
                            ./celebdf/
                                    Celeb-real/
                                    Celeb-synthesis/
                                    YouTube-real/
                                    List_of_testing_videos.txt
                        """)