import torch
import torch.nn as nn


class AffineTransformAdaIn(nn.Module):
    '''
    Adaptive instance normalization module with style affine transformation
    '''

    def __init__(self, in_features: int, style_features_count: int):
        super(AffineTransformAdaIn, self).__init__()

        self.style_features_count = style_features_count
        self.affine_transform = nn.Linear(self.style_features_count, 2 * in_features)
        self.ada_in = AdaIn(in_features)

        # Makes scale parameters biased 1 and bias parameters biased 0
        self.affine_transform.bias.data[:in_features] = 1
        self.affine_transform.bias.data[in_features:] = 0

    def forward(self, input: torch.Tensor, style: torch.Tensor):
        '''

        :param input: (batch_size, in_features)
        :param style: (batch_size, style_features_count)
        :return:
        '''

        # Applies affine transformation to produce the style
        encoded_style = self.affine_transform(style)
        # Separates scale from bias
        scale, bias = encoded_style.chunk(2, 1)
        # Performs adaptive instance normalization
        output = self.ada_in(input, scale, bias)

        return output


class AdaIn(nn.Module):
    '''
    Adaptive instance normalization module
    '''

    def __init__(self, in_features: int):
        super(AdaIn, self).__init__()

        self.normalization = nn.BatchNorm1d(in_features, affine=False)

    def forward(self, input, scale, bias):
        '''

        :param input: (batch_size, in_features)
        :param scale: (batch_size, in_features)
        :param bias: (batch_size, in_features)
        :return:
        '''

        result = self.normalization(input)
        result = result * scale + bias

        return result
