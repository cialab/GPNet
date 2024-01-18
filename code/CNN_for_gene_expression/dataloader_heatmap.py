#%%
import pandas as pd
import numpy as np
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from collections import Counter
from torch.utils.data.distributed import DistributedSampler
from sklearn.decomposition import PCA
import seaborn as sns
import matplotlib.pyplot as plt
import cv2

def load_data(file_path, batch_size=8, Multi_gpu_flag=False):
    # 1. Read the CSV file with MultiIndex
    print("Loading data...")
    data_dir = file_path
    df = pd.read_csv(data_dir, header=[0, 1], index_col=0)
    df.columns = pd.MultiIndex.from_tuples(df.columns)

    gene_names = df.index.values
    gene_name_number_mapping = {gene_names[i]: i for i in range(len(gene_names))}
    gene_number_name_mapping = {i: gene_names[i] for i in range(len(gene_names))}
    gene_numbers = np.arange(len(gene_names))

    # 2. Reshape and Preprocess the Data
    # Flatten the DataFrame
    print("Preprocessing data...")
    data = []
    feature_num = {}
    for col in df.columns:
        label = col[0]  # First level of the MultiIndex is the class name
        features = df[col].values
        data.append((features, label))
        if label not in feature_num:
            feature_num[label] = 0
        else:
            feature_num[label] += 1
    # Separate features and labels
    features, labels = zip(*data)
    features = np.array(features)
    # Find NaN values
    nan_mask = np.isnan(features)
    # Replace NaN values with 0
    features[nan_mask] = 0
    # Create a set of unique labels and sort it to maintain consistency
    unique_labels = sorted(set(labels))

    # Create a mapping dictionary from label to number
    label_to_number = {label: num for num, label in enumerate(unique_labels)}

    # Map your labels to numbers
    numerical_labels = [label_to_number[label] for label in labels]

    # To get the reverse mapping (from number to label), you can use:
    number_to_label = {num: label for label, num in label_to_number.items()}

    labels = numerical_labels
    feature_num = {label_to_number[key]: value for key, value in feature_num.items() if key in label_to_number}

    gene_numbers_len = len(gene_numbers)
    gene_numbers_len = np.round(np.sqrt(gene_numbers_len)) + 1
    # print(gene_numbers_len)
    gene_num_2d = np.zeros((len(gene_numbers), 2))
    for i in range(len(gene_numbers)):
        gene_num_2d[i, 0] = i // gene_numbers_len
        gene_num_2d[i, 1] = i % gene_numbers_len
    # print(gene_num_2d)

    features_mean = np.mean(features)
    features_std = np.std(features)
    features_normalized = (features - features_mean) / features_std

    gene_numbers_mean = np.mean(gene_numbers)
    gene_numbers_std = np.std(gene_numbers)
    gene_numbers_normalized = (gene_numbers - gene_numbers_mean) / gene_numbers_std 

    gene_num_2d_mean = np.mean(gene_num_2d)
    gene_num_2d_std = np.std(gene_num_2d)
    gene_num_2d_normalized = (gene_num_2d - gene_num_2d_mean) / gene_num_2d_std

    # 3. Create a Custom Dataset
    print("Creating dataset...")
    class TumorDataset(Dataset):
        def __init__(self, features_count, labels):
            self.features_count = features_count
            self.labels = labels

        def __len__(self):
            return len(self.labels)

        def __getitem__(self, idx):
            sample_feature1 = self.features_count[idx]
            label = self.labels[idx]
            return sample_feature1, label

    # 4. Split Dataset
    print("Splitting dataset...")
    X_train, X_temp, y_train, y_temp = train_test_split(features_normalized, labels, test_size=0.3, random_state=42, stratify=labels)  # feature normalization
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp)

    # Ensuring the test set has equal number of samples for each class
    class_counts = Counter(y_test)
    min_class_count = min(class_counts.values())
    indices = {label: np.where(y_test == label)[0][:min_class_count] for label in class_counts}
    balanced_indices = np.concatenate(list(indices.values()))
    X_test_balanced = [X_test[i] for i in balanced_indices]
    y_test_balanced = [y_test[i] for i in balanced_indices]

    gene_numbers_norm_tile_train = np.tile(gene_numbers_normalized, (X_train.shape[0], 1))
    gene_numbers_norm_tile_val = np.tile(gene_numbers_normalized, (X_val.shape[0], 1))
    gene_numbers_norm_tile_test = np.tile(gene_numbers_normalized, (len(X_test), 1))

    gene_num_2d_norm_tile_train = np.tile(gene_num_2d_normalized, (X_train.shape[0], 1, 1))
    gene_num_2d_norm_tile_val = np.tile(gene_num_2d_normalized, (X_val.shape[0], 1, 1))
    gene_num_2d_norm_tile_test = np.tile(gene_num_2d_normalized, (len(X_test), 1, 1))


    pca = PCA(n_components=320)
    pca.fit(X_train)
    X_train = pca.transform(X_train).reshape(-1, 16, 20)
    X_val = pca.transform(X_val).reshape(-1, 16, 20)
    X_test = pca.transform(X_test).reshape(-1, 16, 20)
    print(X_train.shape)
    
    # Initialize an empty array for the heatmaps
    heatmaps_train = np.zeros((X_train.shape[0], 3, 64, 80), dtype=np.float32)

    # Generate and resize heatmap for each sample
    for i, sample in enumerate(X_train):
        # Create a heatmap using seaborn
        plt.figure(figsize=(1.6, 2))  # Temporary figure size, will be resized later
        sns.heatmap(sample, cmap='viridis', cbar=False)
        
        # Save the heatmap to a buffer
        plt.savefig('heatmap.png', bbox_inches='tight', pad_inches=0)
        plt.close()  # Close the figure to free memory
        
        # Read the saved heatmap and resize
        heatmap_img = cv2.imread('heatmap.png')
        heatmap_img_resized = cv2.resize(heatmap_img, (80, 64), interpolation=cv2.INTER_LINEAR)
        
        # Normalize the image to have values between 0 and 1
        heatmap_img_normalized = cv2.normalize(heatmap_img_resized, None, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
        
        # Rearrange the dimensions from (H, W, C) to (C, H, W) to fit PyTorch's convention
        heatmap_img_normalized = np.transpose(heatmap_img_normalized, (2, 0, 1))
        
        # Store the resized heatmap
        heatmaps_train[i] = heatmap_img_normalized

    print(heatmaps_train.shape)

        # Initialize an empty array for the heatmaps
    heatmaps_val = np.zeros((X_val.shape[0], 3, 64, 80), dtype=np.float32)

    # Generate and resize heatmap for each sample
    for i, sample in enumerate(X_val):
        # Create a heatmap using seaborn
        plt.figure(figsize=(1.6, 2))  # Temporary figure size, will be resized later
        sns.heatmap(sample, cmap='viridis', cbar=False)
        
        # Save the heatmap to a buffer
        plt.savefig('heatmap.png', bbox_inches='tight', pad_inches=0)
        plt.close()  # Close the figure to free memory
        
        # Read the saved heatmap and resize
        heatmap_img = cv2.imread('heatmap.png')
        heatmap_img_resized = cv2.resize(heatmap_img, (80, 64), interpolation=cv2.INTER_LINEAR)
        
        # Normalize the image to have values between 0 and 1
        heatmap_img_normalized = cv2.normalize(heatmap_img_resized, None, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
        
        # Rearrange the dimensions from (H, W, C) to (C, H, W) to fit PyTorch's convention
        heatmap_img_normalized = np.transpose(heatmap_img_normalized, (2, 0, 1))
        
        # Store the resized heatmap
        heatmaps_val[i] = heatmap_img_normalized

        # Initialize an empty array for the heatmaps
    heatmaps_test = np.zeros((X_test.shape[0], 3, 64, 80), dtype=np.float32)

    # Generate and resize heatmap for each sample
    for i, sample in enumerate(X_test):
        # Create a heatmap using seaborn
        plt.figure(figsize=(1.6, 2))  # Temporary figure size, will be resized later
        sns.heatmap(sample, cmap='viridis', cbar=False)
        
        # Save the heatmap to a buffer
        plt.savefig('heatmap.png', bbox_inches='tight', pad_inches=0)
        plt.close()  # Close the figure to free memory
        
        # Read the saved heatmap and resize
        heatmap_img = cv2.imread('heatmap.png')
        heatmap_img_resized = cv2.resize(heatmap_img, (80, 64), interpolation=cv2.INTER_LINEAR)
        
        # Normalize the image to have values between 0 and 1
        heatmap_img_normalized = cv2.normalize(heatmap_img_resized, None, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
        
        # Rearrange the dimensions from (H, W, C) to (C, H, W) to fit PyTorch's convention
        heatmap_img_normalized = np.transpose(heatmap_img_normalized, (2, 0, 1))
        
        # Store the resized heatmap
        heatmaps_test[i] = heatmap_img_normalized

    # Create PyTorch Datasets
    train_dataset = TumorDataset(heatmaps_train, y_train)
    val_dataset = TumorDataset(heatmaps_val, y_val)
    test_dataset = TumorDataset(heatmaps_test, y_test)

    # 5. Create DataLoaders
    print("Creating dataloaders...")
    if Multi_gpu_flag:
        train_sampler = DistributedSampler(dataset = train_dataset, shuffle=True)
        val_sampler = DistributedSampler(dataset = val_dataset, shuffle=True)
        test_sampler = DistributedSampler(dataset = test_dataset, shuffle=True)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False, sampler=train_sampler, num_workers=32, pin_memory=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, sampler=None, num_workers=32, pin_memory=True)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, sampler=None, num_workers=32, pin_memory=True)
    else:
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    return gene_number_name_mapping, number_to_label,feature_num, train_loader, val_loader, test_loader
#%%
if __name__ == '__main__':
    # Check the data loader.
    data_dir = f"/isilon/datalake/cialab/original/cialab/image_database/d00154/Tumor_gene_counts/training_data_6_tumors.csv"
    gene_number_name_mapping, number_to_label,feature_num, train_loader, val_loader, test_loader= load_data(file_path=data_dir, batch_size=8)
    for data_check in train_loader:
        # Unpack the data
        features1_check, labels_check = data_check

        # Print the first element of the batch
        print("First feature batch:", features1_check[0])
        print("First label batch:", labels_check[0])

        # Break the loop after the first batch
        break
# %%
