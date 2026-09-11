import os
import sys
import asyncio
import shutil
import glob
import edge_tts
import librosa
import soundfile as sf
import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from skl2onnx import to_onnx

import openwakeword
from openwakeword.custom_verifier_model import get_reference_clip_features

VOICES = [
    "en-US-GuyNeural",
    "en-US-ChristopherNeural",
    "en-GB-RyanNeural",
    "en-US-JennyNeural",
    "en-AU-WilliamNeural"
]

DATA_DIR = "data/synthetic_jarvis"
OUTPUT_MODEL = "models/jarvis.onnx"

async def generate_synthetic_audio():
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"Generating 50 synthetic 'Jarvis' audio samples in {DATA_DIR}...")
    
    count = 0
    # Generate 10 variations per voice
    for i in range(10):
        for voice in VOICES:
            if count >= 50:
                break
            
            # Vary pitch and rate for diversity
            rate_val = 5 * (i - 5)
            pitch_val = 5 * (i - 5)
            rate = f"{rate_val:+d}%" if rate_val != 0 else "+0%"
            pitch = f"{pitch_val:+d}Hz" if pitch_val != 0 else "+0Hz"
            
            communicate = edge_tts.Communicate("Jarvis", voice, rate=rate, pitch=pitch)
            mp3_path = os.path.join(DATA_DIR, f"jarvis_{count}.mp3")
            wav_path = os.path.join(DATA_DIR, f"jarvis_{count}.wav")
            
            await communicate.save(mp3_path)
            
            # Load with librosa, resample to 16000Hz mono
            y, sr = librosa.load(mp3_path, sr=16000, mono=True)
            
            # Convert float32 to int16 PCM
            y_int16 = (y * 32767).astype(np.int16)
            
            # Save as 16-bit WAV using soundfile
            sf.write(wav_path, y_int16, 16000, subtype='PCM_16')
            
            # Remove temporary mp3
            os.remove(mp3_path)
            count += 1
            print(f"Generated {count}/50: {wav_path} (Voice: {voice}, Rate: {rate}, Pitch: {pitch})")

def train_model():
    print("\nTraining custom openWakeWord ONNX model via scikit-learn...")
    os.makedirs("models", exist_ok=True)
    
    positive_clips = glob.glob(os.path.join(DATA_DIR, "*.wav"))
    if not positive_clips:
        print("[Error] No synthetic audio found.")
        return

    # Use AudioFeatures directly to bypass openwakeword.Model() speex_vad issues
    from openwakeword.utils import AudioFeatures
    preprocessor = AudioFeatures(inference_framework="onnx")
    
    print("Extracting embedding vectors from positive clips...")
    X_pos = []
    
    for clip in positive_clips:
        try:
            y, sr = sf.read(clip)
            if y.ndim > 1:
                y = y.mean(axis=1)
            # Scale float to int16 range as expected by openwakeword embeddings
            y_int16 = (y * 32767).astype(np.int16)
            
            # Embed clip
            x = y_int16.reshape(1, -1)
            emb = preprocessor.embed_clips(x)
            
            # Extract last 5 frames and flatten (matching standard verifier logic)
            if emb.shape[1] >= 5:
                feat = emb[0, -5:, :].flatten()
                X_pos.append(feat)
        except Exception as e:
            print(f"Failed to extract features for {clip}: {e}")
            
    if not X_pos:
        print("[Error] Failed to extract any positive features.")
        return
        
    X_pos = np.vstack(X_pos)
    y_pos = np.ones(X_pos.shape[0])

    # Generate dummy negative embeddings
    print("Generating negative dummy embeddings...")
    neg_dir = "data/synthetic_jarvis_negative"
    os.makedirs(neg_dir, exist_ok=True)
    silence = np.zeros(16000 * 2, dtype=np.int16)
    silence_path = os.path.join(neg_dir, "silence.wav")
    sf.write(silence_path, silence, 16000, subtype='PCM_16')
    
    try:
        y, sr = sf.read(silence_path)
        y_int16 = (y * 32767).astype(np.int16)
        x = y_int16.reshape(1, -1)
        emb = preprocessor.embed_clips(x)
        feat_neg = emb[0, -5:, :].flatten()
        
        # Duplicate negative samples to balance the dataset
        X_neg = np.tile(feat_neg, (len(X_pos), 1))
        y_neg = np.zeros(X_neg.shape[0])
    except Exception as e:
        print(f"Failed to extract negative features: {e}")
        return

    # Combine data
    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([y_pos, y_neg])

    print("Training LogisticRegression classifier...")
    # Create and train classifier
    clf = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(C=1.0, class_weight='balanced'))
    ])
    clf.fit(X, y)
    
    print("Exporting classifier to ONNX...")
    # Convert to ONNX
    onx = to_onnx(clf, X[:1].astype(np.float32), target_opset=12)
    
    with open(OUTPUT_MODEL, "wb") as f:
        f.write(onx.SerializeToString())

    if os.path.exists(OUTPUT_MODEL):
        print(f"\n[Success] Custom single-word model generated at {OUTPUT_MODEL}")
    else:
        print("\n[Error] Model generation may have failed; output model not found.")

def cleanup():
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
        print("Cleaned up temporary synthetic audio files.")
    if os.path.exists("data/synthetic_jarvis_negative"):
        shutil.rmtree("data/synthetic_jarvis_negative")

async def main():
    existing_files = glob.glob(os.path.join(DATA_DIR, "*.wav"))
    if len(existing_files) < 50:
        await generate_synthetic_audio()
    else:
        print("Using existing synthetic audio clips...")
    
    train_model()
    cleanup()

if __name__ == "__main__":
    asyncio.run(main())
