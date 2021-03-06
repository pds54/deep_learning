import torch
import torch.nn.functional as F
import matplotlib as plt
from pylab import show, subplots
import numpy as np
import torchvision.transforms as T

def extract_peak(heatmap, max_pool_ks=7, min_score=-5, max_det=100):

    heatmap_pool = F.max_pool2d(
        heatmap[None, None], kernel_size=max_pool_ks, padding=max_pool_ks // 2, stride=1)
    h = heatmap_pool.size()[2]
    w = heatmap_pool.size()[3]
    heatmap_pool = heatmap_pool[0, 0, :, :]

    # get coordinates of actual max by comparing input
    cmp_result = torch.eq(heatmap, heatmap_pool).float()
    heatmap_pool = cmp_result * heatmap_pool
    heatmap_pool = torch.flatten(heatmap_pool)

    if max_det > heatmap_pool.size()[0]:
        max_det = heatmap_pool.size()[0]
    values, indices = torch.topk(heatmap_pool, max_det)
    peaks = []

    for i in range(values.size()[0]):
        val = values[i]
        if val > min_score:
            cx = indices[i] // w
            cy = indices[i] % w
            peaks.append((val, cy, cx))
    return peaks

class CNNClassifier(torch.nn.Module):
    class DownBlock(torch.nn.Module):
        def __init__(self, n_input, n_output, kernel_size=3, stride=2):
            super().__init__()
            self.c1 = torch.nn.Conv2d(n_input, n_output, kernel_size=kernel_size, padding=kernel_size // 2,
                                      stride=stride)
            self.c2 = torch.nn.Conv2d(
                n_output, n_output, kernel_size=kernel_size, padding=kernel_size // 2)
            self.c3 = torch.nn.Conv2d(
                n_output, n_output, kernel_size=kernel_size, padding=kernel_size // 2)
            self.skip = torch.nn.Conv2d(
                n_input, n_output, kernel_size=1, stride=stride)

        def forward(self, x):
            return F.relu(self.c3(F.relu(self.c2(F.relu(self.c1(x)))))) + self.skip(x)



# FCN Model from Homework 3
class Detector(torch.nn.Module):
    class UpBlock(torch.nn.Module):
        def __init__(self, n_input, n_output, kernel_size=3, stride=2):
            super().__init__()
            self.c1 = torch.nn.ConvTranspose2d(n_input, n_output, kernel_size=kernel_size, padding=kernel_size // 2,
                                               stride=stride, output_padding=1)

        def forward(self, x):
            return F.relu(self.c1(x))

    def __init__(self, layers=[16, 32, 64, 128], n_output_channels=3, kernel_size=3, use_skip=True):
        super().__init__()
        self.input_mean = torch.Tensor([0.3521554, 0.30068502, 0.28527516])
        self.input_std = torch.Tensor([0.18182722, 0.18656468, 0.15938024])

        c = 3
        self.use_skip = use_skip
        self.n_conv = len(layers)
        skip_layer_size = [3] + layers[:-1]
        for i, l in enumerate(layers):
            self.add_module('conv%d' %
                            i, CNNClassifier.DownBlock(c, l, kernel_size, 2))
            c = l
        for i, l in list(enumerate(layers))[::-1]:
            self.add_module('upconv%d' % i, self.UpBlock(c, l, kernel_size, 2))
            c = l
            if self.use_skip:
                c += skip_layer_size[i]
        self.classifier = torch.nn.Conv2d(c, n_output_channels, 1)

    def forward(self, x):
        z = (x - self.input_mean[None, :, None, None].to(x.device)
             ) / self.input_std[None, :, None, None].to(x.device)
        up_activation = []
        for i in range(self.n_conv):
            # Add all the information required for skip connections
            up_activation.append(z)
            z = self._modules['conv%d' % i](z)

        for i in reversed(range(self.n_conv)):
            z = self._modules['upconv%d' % i](z)
            # Fix the padding
            z = z[:, :, :up_activation[i].size(2), :up_activation[i].size(3)]
            # Add the skip connection
            if self.use_skip:
                z = torch.cat([z, up_activation[i]], dim=1)
        return self.classifier(z)


    def detect(self, image):
        heatmap = self.forward(image).data[0]
        global_peaks = []
        for i in range(3):
            # call peak detection on each class
            if i == 0:
                peaks = extract_peak(heatmap[i, :, :], min_score=0)
            elif i == 1:
                peaks = extract_peak(heatmap[i, :, :], min_score=0)

            else:
                peaks = extract_peak(heatmap[i, :, :], min_score=0)
            for score, cx, cy in peaks:
                # append class_id to each tuple to each class
                global_peaks.append((int(i), float(score), int(cx), int(cy)))
        global_peaks.sort(key=lambda tup: tup[1], reverse=True)
        if len(global_peaks) < 100:
            return global_peaks
        else:
            return global_peaks[:100]

    def detect_with_size(self, image):
        """
           Your code here. (extra credit)
           Implement object detection here.
           @image: 3 x H x W image
           @return: List of detections [(class_id, score cx, cy, w/2, h/2), ...],
                    return no more than 100 detections per image
           Hint: Use extract_peak here
        """
        raise NotImplementedError('Detector.detect_with_size')


def save_model(model):
    from torch import save
    from os import path
    return save(model.state_dict(), path.join(path.dirname(path.abspath(__file__)), 'det.th'))


def load_model():
    from torch import load
    from os import path
    r = Detector()
    r.load_state_dict(load(path.join(path.dirname(path.abspath(__file__)), 'det.th'), map_location='cpu'))
    return r


if __name__ == '__main__':
    """
    Shows detections of your detector
    """
    from .utils import DetectionSuperTuxDataset
    dataset = DetectionSuperTuxDataset('dense_data/valid', min_size=0)
    import torchvision.transforms.functional as TF
    from pylab import show, subplots
    import matplotlib.patches as patches

    fig, axs = subplots(3, 4)
    model = load_model()
    for i, ax in enumerate(axs.flat):
        im, kart, bomb, pickup = dataset[i]
        ax.imshow(TF.to_pil_image(im), interpolation=None)
        for k in kart:
            ax.add_patch(
                patches.Rectangle((k[0] - 0.5, k[1] - 0.5), k[2] - k[0], k[3] - k[1], facecolor='none', edgecolor='r'))
        for k in bomb:
            ax.add_patch(
                patches.Rectangle((k[0] - 0.5, k[1] - 0.5), k[2] - k[0], k[3] - k[1], facecolor='none', edgecolor='g'))
        for k in pickup:
            ax.add_patch(
                patches.Rectangle((k[0] - 0.5, k[1] - 0.5), k[2] - k[0], k[3] - k[1], facecolor='none', edgecolor='b'))
        for c, s, cx, cy in model.detect(im):
            ax.add_patch(patches.Circle((cx, cy), radius=max(2 + s / 2, 0.1), color='rgb'[c]))
        ax.axis('off')
    show()
