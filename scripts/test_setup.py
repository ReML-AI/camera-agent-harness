#!/usr/bin/env python3
"""
Test script to verify installation and GPU access
"""

import sys

def test_imports():
    """Test if all required packages can be imported"""
    print("Testing package imports...")

    tests = {
        "torch": lambda: __import__("torch"),
        "cv2": lambda: __import__("cv2"),
        "easyocr": lambda: __import__("easyocr"),
        "transformers": lambda: __import__("transformers"),
        "numpy": lambda: __import__("numpy"),
        "tqdm": lambda: __import__("tqdm"),
    }

    failed = []
    for name, import_fn in tests.items():
        try:
            import_fn()
            print(f"  ✓ {name}")
        except ImportError as e:
            print(f"  ✗ {name}: {e}")
            failed.append(name)

    # Try WhisperX (optional)
    try:
        __import__("whisperx")
        print("  ✓ whisperx")
    except ImportError:
        print("  ⚠ whisperx (not installed - needed for transcription)")
        failed.append("whisperx")

    return len(failed) == 0

def test_gpu():
    """Test GPU availability"""
    print("\nTesting GPU access...")

    try:
        import torch

        print(f"  PyTorch version: {torch.__version__}")
        print(f"  CUDA available: {torch.cuda.is_available()}")

        if torch.cuda.is_available():
            print(f"  CUDA version: {torch.version.cuda}")
            print(f"  GPU count: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")

            # Test memory
            try:
                torch.zeros(1000, 1000).cuda()
                print("  ✓ GPU memory test passed")
                torch.cuda.empty_cache()
            except Exception as e:
                print(f"  ✗ GPU memory test failed: {e}")
                return False
        else:
            print("  ⚠ No GPU available (will use CPU - much slower)")

        return True
    except Exception as e:
        print(f"  ✗ GPU test failed: {e}")
        return False

def test_video_files():
    """Check if video files exist"""
    print("\nChecking video files...")

    import os

    files = [
        "data/videos/cam1.mp4",
        "data/videos/cam2.mp4",
        "data/videos/cam3.mp4",
        "data/videos/monitor.mp4",
    ]

    all_exist = True
    for f in files:
        if os.path.exists(f):
            size_mb = os.path.getsize(f) / (1024 * 1024)
            print(f"  ✓ {f} ({size_mb:.1f} MB)")
        else:
            print(f"  ✗ {f} (not found)")
            all_exist = False

    return all_exist

def test_directories():
    """Check if required directories exist"""
    print("\nChecking directories...")

    import os

    dirs = [
        "data/videos",
        "data/transcript",
        "data/processed",
        "data/output",
        "scripts",
    ]

    for d in dirs:
        if os.path.exists(d):
            print(f"  ✓ {d}/")
        else:
            print(f"  ✗ {d}/ (creating...)")
            os.makedirs(d, exist_ok=True)

    return True

def main():
    print("=" * 80)
    print("SETUP VERIFICATION TEST")
    print("=" * 80)
    print()

    results = {}

    results["imports"] = test_imports()
    results["gpu"] = test_gpu()
    results["directories"] = test_directories()
    results["videos"] = test_video_files()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name.capitalize()}: {status}")

    if all(results.values()):
        print("\n✓ All tests passed! Ready to run pipeline.")
        return 0
    else:
        print("\n⚠ Some tests failed. Check errors above.")
        if not results["imports"]:
            print("\n  To install missing packages:")
            print("    pip install -r requirements.txt")
        if not results["videos"]:
            print("\n  Make sure video files are in data/videos/")
        return 1

if __name__ == "__main__":
    sys.exit(main())
