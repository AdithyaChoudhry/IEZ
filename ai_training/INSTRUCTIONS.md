# iEZ SDIE — AI Training Instructions

## What was built
- `prepare_dataset.py` — reads all 38 WABAG datasheets → generates 123 training examples
- `dataset.jsonl` / `dataset_val.jsonl` — the training data (generated, ready to upload)
- `kaggle_train.ipynb` — Kaggle notebook for LoRA fine-tuning Llama 3.1 8B (free T4 GPU)
- `hf_inference.py` — drop-in Python client to call your trained model from the app

---

## Step 1: Upload dataset to Kaggle

1. Go to kaggle.com → **Datasets** → **New Dataset**
2. Name it exactly: `iez-sdie-dataset`
3. Upload both files:
   - `ai_training/dataset.jsonl`
   - `ai_training/dataset_val.jsonl`
4. Set visibility to **Private** → Create

---

## Step 2: Add HF Token as Kaggle Secret

1. In Kaggle → top right → **Settings** → **Secrets**
2. Click **Add Secret**
3. Name: `HF_TOKEN`
4. Value: your `hf_...` token from Hugging Face

---

## Step 3: Create and run the training notebook

1. Go to kaggle.com → **Code** → **New Notebook**
2. Click **File** → **Import Notebook** → upload `ai_training/kaggle_train.ipynb`
3. On the right panel → **Data** → Add dataset → search `iez-sdie-dataset` → Add
4. On the right panel → **Settings** → **Accelerator** → select **GPU T4 x2**
5. Enable **Internet** (required to download model and push to HF)
6. Click **Run All**
7. Training takes ~2-3 hours on free T4

---

## Step 4: Verify model on Hugging Face

After training completes, go to:
`https://huggingface.co/AdithyaChoudhry/iez-sdie-llama3-lora`

You should see the model files uploaded.

---

## Step 5: Integrate into your app

Add to your `.env` file:
```
HF_TOKEN=hf_your_token_here
HF_MODEL=AdithyaChoudhry/iez-sdie-llama3-lora
```

Then in your code (e.g., in `utils/sdie_extractor.py`):
```python
from ai_training.hf_inference import extract_specifications

result = extract_specifications(
    tender_text=ocr_extracted_text,
    instrument_hint="Pressure Transmitter"
)
# result: {"Tag Number": {"value": "PT-201", "confidence": 98}, ...}
```

---

## Retrain with more data

When you get more datasheets:
1. Add them to `/Downloads/DataSheets/` in the correct folder
2. Run: `python ai_training/prepare_dataset.py`
3. Re-upload the new `.jsonl` files to Kaggle
4. Re-run the training notebook (each run improves the model)
