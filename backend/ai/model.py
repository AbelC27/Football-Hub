"""Match outcome predictor: feed-forward network for 1X2 probabilities.

Kept deliberately small. With the supported scope (~2k finished matches
across the top 5 + UCL), heavier nets overfit; widths of 64-32-16
trained for ~120 epochs have been the most stable in evaluation. The
input layer width is parametrised so the same class can host future
feature extensions without having to update the inference singleton.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class FootballPredictor(nn.Module):
    def __init__(
        self,
        input_size: int = 13,
        hidden1: int = 64,
        hidden2: int = 32,
        hidden3: int = 16,
        output_size: int = 3,
        dropout: float = 0.30,
    ):
        super().__init__()
        self.input_size = input_size
        self.fc1 = nn.Linear(input_size, hidden1)
        self.dropout1 = nn.Dropout(dropout)
        self.fc2 = nn.Linear(hidden1, hidden2)
        self.dropout2 = nn.Dropout(dropout * 0.66)
        self.fc3 = nn.Linear(hidden2, hidden3)
        self.fc4 = nn.Linear(hidden3, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.fc1(x))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        x = F.relu(self.fc3(x))
        x = self.fc4(x)
        return x  # raw logits
