import torch
import torch.nn as nn
import torch.nn.functional as F

class FootballPredictor(nn.Module):
    def __init__(self, input_size=11, hidden1=64, hidden2=32, hidden3=16, output_size=3):
        super(FootballPredictor, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden1)
        self.dropout1 = nn.Dropout(0.3)
        self.fc2 = nn.Linear(hidden1, hidden2)
        self.dropout2 = nn.Dropout(0.2)
        self.fc3 = nn.Linear(hidden2, hidden3)
        self.fc4 = nn.Linear(hidden3, output_size)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        x = F.relu(self.fc3(x))
        x = self.fc4(x)
        return x  # Raw logits
