import cv2
import torch
import numpy as np
import torchvision
from PIL import Image
import torch.nn as nn
from torchinfo import summary
import matplotlib.pyplot as plt
from torch.utils.data import DataLoader


class ImageProcessing:
    """
    Processes images for proper training specifications
    Prevents issues with size and shape of all images in a dataset
    Normalizes values in images to prevent training issues
    Parameters
    ----------
    image_list : list
        holds the list of images to transform with following methods
    """

    def __init__(self, image_list):
        self.image_list = image_list

    def smallest_image_size(self):
        min_height = 10e4
        min_length = 10e4

        for s in self.image_list:
            shape = s.shape
            height = shape[0]
            length = shape[1]
            if height < min_height:
                min_height = height
            if length < min_length:
                min_length = length
        return min_height, min_length

    def resize(self, image, height, length):
        res = cv2.resize(
            image, dsize=(length - 1, height - 1), interpolation=cv2.INTER_CUBIC
        )
        return res

    def normalize_image(self, image):
        im_mean = np.mean(image)
        im_std = np.std(image)
        return (image - im_mean) / im_std

    def loss_crop(self, image):
        image = (image[0, 0, :, :]).numpy()
        cropped_image = []
        for row in image:
            crop = row[17:25]
            cropped_image.append(crop)
        cropped_image = np.asarray(cropped_image[55:80])
        cropped_image = torch.from_numpy(cropped_image.astype("f"))
        return cropped_image


class Block(nn.Module):
    """
    Create the basic block architecture with conv2d in and out and RELU activation
    Assumes kernel size is 3, stride is 1, and padding is 1
    Parameters
    ----------
    input_channels : int
        The number of channels in the input image
        Set to 1 if no channels necessary
    output_channels : int
        The number of channels in the output image
        Set to 1 if no channels necessary
    """

    def __init__(self, input_channels=1, output_channels=3):
        super().__init__()
        self.input_layer = nn.Conv2d(
            input_channels, output_channels, 3, stride=1, padding=1
        )
        self.relu = nn.ReLU()
        self.dropout = torch.nn.Dropout(0.5)
        self.output_layer = nn.Conv2d(
            output_channels, output_channels, 3, stride=1, padding=1
        )

    def forward(self, x):
        x = self.input_layer(x)
        x = self.dropout(x)
        x = self.relu(x)
        x = self.output_layer(x)
        return x


class Encoder(nn.Module):
    """
    Creates the Encoder block using the Block class that contracts images
    The encoder is similar to a standard (Convolutional Neural Network CNN)
    Assumes kernel size is 3, stride is 1, and padding is 1 from class Block
    Parameters
    ----------
    num_channels : list, tuple
        As the image trains the number of channels will be increased
        Later to be decreased by the conv transpose
    """

    def __init__(self, num_channels=(1, 64, 128, 256)):
        super().__init__()
        block_list = []
        for i in range(len(num_channels) - 1):
            block_list.append(Block(num_channels[i], num_channels[i + 1]))
        self.num_channels = num_channels
        self.encoder_blocks = nn.ModuleList(block_list)
        self.maxpool = nn.MaxPool2d(2)

    def forward(self, x):
        output = []
        for block in self.encoder_blocks:
            x = block(x)
            output.append(x)
            x = self.maxpool(x)
        return output

    def shape(self):
        return max(self.num_channels)


class Decoder(nn.Module):
    """
    Creates the Decoder block using the Block class to expand images
    Up samples image at each step to increase image from low to high resolution
    Assumes kernel size is 3, stride is 1, and padding is 1 from class Block
    Parameters
    ----------
    num_channels : list, tuple
        As the image trains the number of channels will be decreased from
        the maximum size from the encoder
    Methods
    -------
    crop - Downsizes x to ensure correct output shape
    """

    def __init__(self, num_channels=(256, 128, 64)):
        super().__init__()
        self.num_channels = num_channels
        # conv transpose for decreasing pairs of channels
        upconv_list = []
        decblock_list = []
        for i in range(len(num_channels) - 1):
            upconv_list.append(
                nn.ConvTranspose2d(num_channels[i], num_channels[i + 1], 2, 2)
            )
            decblock_list.append(Block(num_channels[i], num_channels[i + 1]))
        self.upconv_modules = nn.ModuleList(upconv_list)
        self.decoder_blocks = nn.ModuleList(decblock_list)

    def forward(self, x, encoder_features):
        for i in range(len(self.num_channels) - 1):
            x = self.upconv_modules[i](x)
            encoder_features = self.crop(encoder_features[i], x)
            x = torch.cat([x, encoder_features], dim=1)
            x = self.decoder_blocks[i](x)
        return x

    def crop(self, encoder_features, x):
        _, _, H, W = x.shape
        encoder_features = torchvision.transforms.CenterCrop([H, W])(encoder_features)
        return encoder_features

    def shape(self):
        return max(self.num_channels)


class UNet(nn.Module):
    """
    Creates a Unet model using the Block, Encoder, and Decoder classes
    Parameters
    ----------
    encoder_channels : list, tuple
        same channels as the encoder class
    decoder_channels : list, tuple
        same channels as the decoder class
    groups : int
        default is 1 so that all inputs are convolved to all outputs
    """

    def __init__(
        self,
        encoder_channels=(1, 64, 128),
        decoder_channels=(128, 64),
        groups=1,
    ):
        super().__init__()
        self.encoder = Encoder(encoder_channels)
        self.decoder = Decoder(decoder_channels)
        self.head = nn.Conv2d(decoder_channels[-1], groups, 1)

    def forward(self, x):
        encoder_features = self.encoder(x)
        #print(encoder_features[::-1][0])
        print(encoder_features[::-1][1:])
        out = self.decoder(encoder_features[::-1][0], encoder_features[::-1][1:])
        out = self.head(out)
        return out


class ParamUnet(nn.Module):
    """
    Creates a Unet model using the Block, Encoder, and Decoder classes
    Parameters
    ----------
    encoder_channels : list, tuple
        same channels as the encoder class
    decoder_channels : list, tuple
        same channels as the decoder class
    groups : int
        default is 1 so that all inputs are convolved to all outputs
    """

    def __init__(
        self,
        encoder_channels=(1, 64, 128),
        decoder_channels=(128, 64),
        groups=1,
    ):
        super().__init__()
        self.encoder = Encoder(encoder_channels)
        x = torch.mul(-1, torch.randn(41))
        self.m1 = torch.nn.Parameter(x)
        self.decoder = Decoder(decoder_channels)
        self.m2 = torch.nn.Parameter(torch.randn(40))
        self.head = nn.Conv2d(decoder_channels[-1], groups, 1)

    def forward(self, x):
        encoder_features = self.encoder(x)
        #encoder_features = torch.mul(self.m1, x)
        #print(encoder_features)
        out = self.decoder(encoder_features[::-1][0], encoder_features[::-1][1:])
        out = torch.mul(self.m2, out)
        out = self.head(out)
        return out
