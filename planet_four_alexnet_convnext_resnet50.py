# -*- coding: utf-8 -*-
"""Planet Four-AlexNet-ConvNext-ResNet50

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1SCpgm_hNNraJu816FnfiTk-sWQ7CFj0C
"""

#@title Execution parameters
#@markdown Forms support many types of fields.

dataset_url = 'https://www.eeng.dcu.ie/~mcguinne/data/ee514/planetfour/planetfour.tar'  #@param {type: "string"}

"""## Planet four image classification"""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

import torch
import torch.nn.functional as F
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
import torchvision.models as models
import sklearn.metrics as metrics
import tqdm

from torch.utils.data import DataLoader
from torchvision.datasets.folder import pil_loader
from pathlib import Path
from PIL import Image

"""Change the device to "cpu" if you want to train on a CPU instead of a GPU."""

device = 'cuda'

"""## Dataset

Here we define a custom Dataset object for the Planet Four data. You can read more about this in the PyTorch documentation: https://pytorch.org/tutorials/beginner/basics/data_tutorial.html
"""

data_dir = Path('data')
!mkdir -p $data_dir
!curl -k $dataset_url > $data_dir/dataset.tar
!tar -C $data_dir/ -xvf $data_dir/dataset.tar
!rm $data_dir/dataset.tar
!mkdir -p checkpoints

class PlanetFourDataset(object):
    def __init__(self, split='train', transform=None, loader=pil_loader):
        super().__init__()
        self.split = split
        self.base_dir = Path('data/planetfour')
        self.image_dir = self.base_dir / split
        self.labels_file = self.base_dir / (split + '.csv')
        self.labels_df = pd.read_csv(self.labels_file)
        self.transform = transform
        self.loader = loader
        
    def __getitem__(self, index):
        row = self.labels_df.iloc[index]
        filename = self.image_dir / (row.tile_id + '.jpg')
        fans = int(row.fans)
        blotches = int(row.blotches)
        image = self.loader(str(filename))
        if self.transform is not None:
            image = self.transform(image)
        return image, torch.tensor([fans, blotches], dtype=torch.float32)
    
    def __len__(self):
        return len(self.labels_df)

"""## Data augmentation

It is standard practice in deep learning to augment the training examples to prevent the network from overfitting. Here I use some standard augmentations such as randomly mirroring the images.
"""

train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010))                  
])

valid_transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)) 
])

"""## Data loaders

In PyTorch, the data loaders take care of spinning up threads to load batches of data into memory from the dataset object.
"""

train_set = PlanetFourDataset('train', transform=train_transform)
valid_set = PlanetFourDataset('valid', transform=train_transform)

train_loader = DataLoader(train_set, batch_size=64, shuffle=True)
valid_loader = DataLoader(valid_set, batch_size=64, shuffle=False)

"""## Load a pretrained model

Here we'll use ResNet50 model that has been pretrained on ImageNet and replace the final layer with a new one suited to our problem.
"""

model = models.resnet50(weights='ResNet50_Weights.DEFAULT')
model.fc = nn.Linear(2048, 2)
model.to(device);

"""## Loss

Images can contain fans, blotches, both, or neither. You could treat this as a four class softmax problem, or two binary classification problems. Here I take the latter approach and use a binary cross entropy loss. 
"""

criterion = nn.BCEWithLogitsLoss()

"""## Optimizer

Stochastic gradient descent with momentum
"""

optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9, weight_decay=1e-4)

"""## Training and validation functions"""

avg_train_losses = []
avg_valid_losses = []
valid_accuracies = []


def train_for_epoch(optimizer):
    model.train()

    train_losses = []

    for batch, target in tqdm.tqdm(train_loader):

        # data to GPU
        batch = batch.to(device)
        target = target.to(device)

        # reset optimizer
        optimizer.zero_grad()

        # forward pass
        predictions = model(batch)
        #breakpoint()

        # calculate loss
        loss = criterion(predictions, target)

        # backward pass
        loss.backward()

        # parameter update
        optimizer.step()

        # track loss
        train_losses.append(float(loss.item()))

    train_losses = np.array(train_losses)
    return train_losses


def validate():
    model.eval()

    valid_losses = []
    y_true, y_prob = [], []

    with torch.no_grad():
        for batch, target in valid_loader:

            # move data to the device
            batch = batch.to(device)
            target = target.to(device)

            # make predictions
            predictions = model(batch)

            # calculate loss
            loss = criterion(predictions, target)
            
            # logits -> probabilities
            torch.sigmoid_(predictions)

            # track losses and predictions
            valid_losses.append(float(loss.item()))
            y_true.extend(target.cpu().numpy())
            y_prob.extend(predictions.cpu().numpy())
            
    y_true = np.array(y_true)
    y_prob = np.array(y_prob)
    y_pred = y_prob > 0.5
    valid_losses = np.array(valid_losses)

    # calculate validation accuracy from y_true and y_pred
    fan_accuracy = metrics.accuracy_score(y_true[:,0], y_pred[:,0])
    blotch_accuracy = metrics.accuracy_score(y_true[:,1], y_pred[:,1])
    exact_accuracy = np.all(y_true == y_pred, axis=1).mean()

    # calculate the mean validation loss
    valid_loss = valid_losses.mean()

    return valid_loss, fan_accuracy, blotch_accuracy, exact_accuracy


def train(epochs, first_epoch=1, model_name=''):
    for epoch in range(first_epoch, epochs+first_epoch):

        # train
        train_loss = train_for_epoch(optimizer)

        # validation
        valid_loss, fan_accuracy, blotch_accuracy, both_accuracy = validate()
        print(f'[{epoch:02d}] train loss: {train_loss.mean():0.04f}  '
              f'valid loss: {valid_loss:0.04f}  ',
              f'fan acc: {fan_accuracy:0.04f}  ',
              f'blotch acc: {blotch_accuracy:0.04f}  ',
              f'both acc: {both_accuracy:0.04f}'
        )
        
        # update learning curves
        avg_train_losses.append(train_loss.mean())
        avg_valid_losses.append(valid_loss)
        valid_accuracies.append((fan_accuracy, blotch_accuracy, both_accuracy))
        
        # save checkpoint
        torch.save(model, f'checkpoints/baseline_{model_name}_{epoch:03d}.pkl')

"""## Constant classifier accuracy

Evaluate how accurate would a $f(x) = \text{"most common class"}$ classifier be? 
"""

def constant_clf_accuracy():
    y_true, y_pred = [], []
    with torch.no_grad():
        for _, target in valid_loader:
            y_true.extend(target.cpu().numpy())
            y_pred.extend(np.ones((target.shape[0], 2), dtype=np.float32))
            
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
        
    # calculate validation accuracy from y_true and y_pred
    f = metrics.accuracy_score(y_true[:,0], y_pred[:,0])
    b = metrics.accuracy_score(y_true[:,1], y_pred[:,1])
    t = np.all(y_true == y_pred, axis=1).mean()
    print(f'fan: {f}  blotch: {b}  both: {t}')

constant_clf_accuracy()

"""## Train the model
Call the ``train(n)`` function to train for ``n`` epochs.
"""

n = 5
train(n, model_name='resnet50')

"""Let's train the model for more epochs"""

train(20, first_epoch=6, model_name='resnet50')

"""Let's plot the training and testing losses"""

def plot_losses(classifier):
  plt.plot(avg_train_losses, label='Average training losses')
  plt.plot(avg_valid_losses, label='Average valid losses')

  plt.legend()
  plt.title(f'Losses for {classifier}')
  plt.show()

def plot_accuracies(classifier):
  plt.plot([v[0] for v in valid_accuracies], label='Fan accuracies')
  plt.plot([v[1] for v in valid_accuracies], label='Bloth accuracies')
  plt.plot([v[2] for v in valid_accuracies], label='Both accuracies')

  plt.legend()
  plt.title(f'Accuracies for {classifier}')
  plt.show()

plot_losses('ResNet50')



plot_accuracies('ResNet50')

"""# Experiments"""

resnet = model
resnet_avg_train_losses = avg_train_losses
resnet_avg_valid_losses = avg_valid_losses
resnet_valid_accuracies = valid_accuracies

"""Let's test with ConvNeXt"""

avg_train_losses = []
avg_valid_losses = []
valid_accuracies = []

model = models.convnext_base(num_classes=2)
model.to(device);

optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9, weight_decay=1e-4)

train(20, model_name='convnext_base')

plot_losses('ConvNeXt')

plot_accuracies('ConvNeXt')

"""Let's see if AlexNet does any better"""

convnext = model
convnext_avg_train_losses = avg_train_losses
convnext_avg_valid_losses = avg_valid_losses
convnext_valid_accuracies = valid_accuracies

avg_train_losses = []
avg_valid_losses = []
valid_accuracies = []

model = models.alexnet(num_classes=2)
model.to(device);

optimizer = optim.SGD(model.parameters(), lr=0.001, momentum=0.9, weight_decay=1e-4)

train(20, model_name='alexnet')

plot_losses('AlexNet')

plot_accuracies('AlexNet')

"""We can see that amongst these 3 models, resnet50 is the one with better performance."""