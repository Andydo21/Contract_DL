import os
from datasets import load_dataset

print("🚀 Bắt đầu tải dữ liệu MVTec AD...")
# Download MVTec AD dataset from Hugging Face
mvtec_ds = load_dataset("Voxel51/mvtec-ad")
print("✅ Tải xong MVTec AD dataset!")

print("🚀 Bắt đầu tải dữ liệu VisA...")
# Download VisA dataset from Hugging Face
visa_ds = load_dataset("BrachioLab/visa")
print("✅ Tải xong VisA dataset!")
