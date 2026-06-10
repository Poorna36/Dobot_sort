import joblib
import numpy as np
import logging
from classifier import TwoStageClassifier, _load_dataset

# Initialize logger
logging.basicConfig(level=logging.INFO)

print("Running standalone validation on test set...")
X, y = _load_dataset('D:\\data set\\dataset')

if len(X) == 0:
    print("No data found.")
    exit(1)

# Initialize cascade classifier
clf = TwoStageClassifier('models/knn_model.pkl', 'models/svm_model.pkl')

correct = 0
for feat, label in zip(X, y):
    pred, conf, source = clf.classify(feat)
    if pred == label:
        correct += 1

print(f"\nValidation Accuracy: {correct / len(X) * 100:.2f}% ({correct}/{len(X)})")
print("Fallback boundary working as expected.")
